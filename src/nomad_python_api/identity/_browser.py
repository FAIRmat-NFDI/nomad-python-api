"""Interactive, deployment-bound OpenID Connect credentials."""

from __future__ import annotations

import re
from base64 import urlsafe_b64encode
from hashlib import sha256
from math import isfinite
from os import PathLike
from secrets import token_urlsafe
from urllib.parse import urlencode, urlsplit

import httpx

from .._core._endpoint import normalize_endpoint
from .._scopes import Scope
from ..exceptions import (
    BrowserAuthenticationError,
    ReauthenticationRequiredError,
)
from . import _loopback, _token
from ._credential import _is_token, _require_endpoint
from ._token import _TokenSession, _Tokens, _identity_tls, _read_tokens, _request_json

_SIGN_IN_AGAIN = "Start a fresh NOMAD browser sign-in with credential.authenticate()."


def _https_origin(url: object) -> tuple[str, int]:
    message = "Use a complete HTTPS identity URL without credentials, query, or fragment."
    if not isinstance(url, str) or any(
        not char.isprintable() or char.isspace() or char in "?#\\%" for char in url
    ):
        raise ValueError(message)
    try:
        parsed = urlsplit(url)
        port = parsed.port
        httpx.URL(url)
    except (ValueError, httpx.InvalidURL):
        raise ValueError(message) from None
    if (
        parsed.scheme != "https" or not parsed.hostname or "@" in parsed.netloc
        or port == 0 or {".", ".."}.intersection(parsed.path.split("/"))
    ):
        raise ValueError(message)
    return parsed.hostname, port or 443


def _identity_endpoints(issuer: str, authorization: object, token: object) -> tuple[str, str]:
    origin = _https_origin(issuer)
    if _https_origin(authorization) != origin or _https_origin(token) != origin:
        raise ValueError("Authorization and token endpoints must share the issuer's HTTPS origin.")
    assert isinstance(authorization, str) and isinstance(token, str)
    return authorization, token


class BrowserCredential:
    """Sign in through a deployment's configured OIDC public client.

    Supply an issuer and client ID, and choose explicit endpoints or discovery.
    A provider alias selects a Keycloak identity provider if the realm offers it.
    The callback uses an IPv4 loopback address and tokens are kept in memory.
    """

    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        endpoint: str = "prod",
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        discover: bool = False,
        identity_provider: str | None = None,
        ca_bundle: str | PathLike[str] | None = None,
        login_timeout: float = 180,
        refresh_margin: float = 30,
        redirect_port: int = 0,
        redirect_path: str = "/",
    ) -> None:
        _https_origin(issuer)
        if not _is_token(client_id) or (identity_provider is not None and not _is_token(identity_provider)):
            raise ValueError("Provide a nonempty client ID and, optionally, a provider alias.")
        if discover and authorization_endpoint is None and token_endpoint is None:
            self._endpoints = None
        elif not discover and authorization_endpoint is not None and token_endpoint is not None:
            self._endpoints = _identity_endpoints(issuer, authorization_endpoint, token_endpoint)
        else:
            raise ValueError("Supply both identity endpoints or set discover=True.")
        if not isfinite(login_timeout) or login_timeout <= 0:
            raise ValueError("login_timeout must be finite and positive.")
        if not isfinite(refresh_margin) or refresh_margin < 0:
            raise ValueError("refresh_margin must be finite and nonnegative.")
        if type(redirect_port) is not int or not 0 <= redirect_port <= 65535:
            raise ValueError("redirect_port must be 0 or a valid TCP port.")
        if (not re.fullmatch(r"/[A-Za-z0-9._~/-]*", redirect_path) or "//" in redirect_path
                or {".", ".."}.intersection(redirect_path.split("/"))):
            raise ValueError("Use an absolute loopback redirect path such as '/'.")
        self._endpoint = normalize_endpoint(endpoint)
        self._issuer = issuer
        self._client_id = client_id
        self._identity_provider = identity_provider
        self._verify = _identity_tls(ca_bundle)
        self._login_timeout = login_timeout
        self._refresh_margin = refresh_margin
        self._redirect_port = redirect_port
        self._redirect_path = redirect_path
        self._session = _TokenSession(
            BrowserAuthenticationError,
            lambda: ReauthenticationRequiredError(_SIGN_IN_AGAIN),
            block_failed_sign_in=True,
        )

    def _discover(self) -> tuple[str, str]:
        if self._endpoints is None:
            url = self._issuer.rstrip("/") + "/.well-known/openid-configuration"
            status, metadata = _request_json(
                "GET", url, verify=self._verify, error=BrowserAuthenticationError,
            )
            if status not in (200, 400):
                raise BrowserAuthenticationError("The identity service rejected the request.")
            if status != 200 or metadata.get("issuer") != self._issuer:
                raise BrowserAuthenticationError("OIDC discovery did not confirm the configured issuer.")
            methods = metadata.get("code_challenge_methods_supported")
            if methods is not None and (not isinstance(methods, list) or "S256" not in methods):
                raise BrowserAuthenticationError("The identity service does not advertise PKCE S256.")
            try:
                self._endpoints = _identity_endpoints(
                    self._issuer, metadata.get("authorization_endpoint"), metadata.get("token_endpoint"),
                )
            except ValueError:
                raise BrowserAuthenticationError("OIDC discovery returned invalid identity endpoints.") from None
        return self._endpoints

    def _exchange(self, url: str, form: dict[str, str], previous_refresh: str | None = None) -> _Tokens:
        started = _token.monotonic()
        status, document = _request_json(
            "POST", url, verify=self._verify, error=BrowserAuthenticationError,
            form={"client_id": self._client_id, **form},
        )
        if status == 400 and document.get("error") == "invalid_grant" and previous_refresh is not None:
            self._session.require_sign_in()
        if status not in (200, 400):
            raise BrowserAuthenticationError("The identity service rejected the request.")
        if status != 200:
            raise BrowserAuthenticationError("The identity service rejected the token request.")
        return _read_tokens(
            document, started=started, margin=self._refresh_margin,
            error=BrowserAuthenticationError, previous_refresh=previous_refresh,
        )

    def _sign_in(self) -> _Tokens:
        authorization, token = self._discover()
        state = token_urlsafe(32)
        verifier = token_urlsafe(48)
        challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("=")

        def make_url(redirect_uri: str) -> str:
            parameters = {
                "client_id": self._client_id, "response_type": "code", "response_mode": "query",
                "scope": "openid", "redirect_uri": redirect_uri, "state": state,
                "code_challenge": challenge, "code_challenge_method": "S256",
            }
            if self._identity_provider is not None:
                parameters["kc_idp_hint"] = self._identity_provider
            return authorization + "?" + urlencode(parameters)

        code, redirect_uri = _loopback.authorize(
            make_url, port=self._redirect_port, path=self._redirect_path,
            state=state, issuer=self._issuer, timeout=self._login_timeout,
        )
        return self._exchange(token, {
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri, "code_verifier": verifier,
        })

    def _renew(self, tokens: _Tokens) -> _Tokens:
        if tokens.refresh is None:
            self._session.require_sign_in()
        _, token_endpoint = self._discover()
        return self._exchange(token_endpoint, {
            "grant_type": "refresh_token", "refresh_token": tokens.refresh,
        }, previous_refresh=tokens.refresh)

    def authenticate(self) -> None:
        """Open the browser and replace the cached session after successful sign-in."""
        self._session.authenticate(self._sign_in)

    def _get_token(self, *, endpoint: str, scopes: frozenset[Scope]) -> str:
        _require_endpoint(self._endpoint, endpoint)
        return self._session.access_token(self._sign_in, self._renew)

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("Browser credentials cannot be pickled. Construct one on the user's machine.")
