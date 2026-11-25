"""Shared transport and in-memory sessions for credentials that obtain tokens."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from threading import Lock
from time import monotonic
from typing import NoReturn

import httpx

from ..exceptions import NomadError
from ._credential import _is_token

_MAX_DOCUMENT = 64 * 1024


def _identity_tls(ca_bundle: str | PathLike[str] | None) -> bool | ssl.SSLContext:
    return True if ca_bundle is None else ssl.create_default_context(cafile=str(ca_bundle))


def _request_json(
    method: str,
    url: str,
    *,
    verify: bool | ssl.SSLContext,
    error: type[NomadError],
    form: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    failure = "The identity service returned invalid JSON."
    try:
        with httpx.Client(
            verify=verify, timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False, trust_env=False,
        ) as http, http.stream(method, url, data=form, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code not in (200, 400):
                return response.status_code, {}
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise error("The identity service returned an unsupported encoding.")
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=16 * 1024):
                if len(body) + len(chunk) > _MAX_DOCUMENT:
                    raise error("The identity service response exceeded the size limit.")
                body.extend(chunk)
            document = json.loads(body)
            if isinstance(document, dict):
                return response.status_code, document
    except (ValueError, RecursionError):
        pass
    except httpx.HTTPError:
        # Drop the HTTP exception because its request can contain credentials.
        failure = "Could not reach the identity service."
    raise error(failure)


@dataclass(frozen=True, repr=False)
class _Tokens:
    access: str
    refresh: str | None
    refresh_at: float


def _read_tokens(
    document: dict[str, object],
    *,
    started: float,
    margin: float,
    error: type[NomadError],
    previous_refresh: str | None = None,
    renew_with_login: bool = False,
) -> _Tokens:
    access = document.get("access_token")
    lifetime = document.get("expires_in")
    token_type = document.get("token_type")
    refresh = None if renew_with_login else document.get("refresh_token", previous_refresh)
    if (
        not isinstance(access, str) or not _is_token(access)
        or not isinstance(token_type, str) or token_type.lower() != "bearer"
        or type(lifetime) is not int or not 0 < lifetime <= 2**31 - 1
        or (refresh is not None and not _is_token(refresh))
    ):
        raise error("The identity service returned an invalid token response.")
    expires_at = started + lifetime
    if monotonic() >= expires_at:
        raise error("The identity service returned an expired access token.")
    lead = min(margin, lifetime / 2) if renew_with_login or refresh is not None else 0
    assert refresh is None or isinstance(refresh, str)
    return _Tokens(access, refresh, expires_at - lead)


class _TokenSession:
    """Serialize acquisition and renewal for one credential's token cache."""

    def __init__(
        self,
        error: type[NomadError],
        required: Callable[[], NomadError],
        *,
        block_failed_sign_in: bool = False,
    ) -> None:
        self._error = error
        self._required = required
        self._block_failed_sign_in = block_failed_sign_in
        self._tokens: _Tokens | None = None
        self._blocked = False
        self._failed_at = float("-inf")
        self._lock = Lock()

    def require_sign_in(self) -> NoReturn:
        """Clear the session during an exchange and require explicit authentication."""
        self._tokens = None
        self._blocked = True
        raise self._required()

    def _sign_in(self, sign_in: Callable[[], _Tokens]) -> _Tokens:
        try:
            return sign_in()
        except BaseException:
            if self._block_failed_sign_in and self._tokens is None:
                self._blocked = True
            raise

    def authenticate(self, sign_in: Callable[[], _Tokens]) -> None:
        with self._lock:
            self._tokens = self._sign_in(sign_in)
            self._blocked = False
            self._failed_at = float("-inf")

    def access_token(
        self,
        sign_in: Callable[[], _Tokens],
        renew: Callable[[_Tokens], _Tokens],
    ) -> str:
        requested_at = monotonic()
        with self._lock:
            if self._blocked:
                raise self._required()
            tokens = self._tokens
            if tokens is not None and monotonic() < tokens.refresh_at:
                return tokens.access
            if requested_at <= self._failed_at:
                raise self._error("NOMAD token refresh failed. Retry the operation.")
            try:
                self._tokens = self._sign_in(sign_in) if tokens is None else renew(tokens)
            except self._error:
                self._failed_at = monotonic()
                raise
            return self._tokens.access
