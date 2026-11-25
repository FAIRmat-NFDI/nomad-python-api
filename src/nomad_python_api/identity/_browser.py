"""Interactive, deployment-bound OpenID Connect credentials."""

from __future__ import annotations

import json
import re
import ssl
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from os import PathLike
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from urllib.parse import urlencode, urlsplit

import httpx

from .._core._endpoint import normalize_endpoint
from .._scopes import Scope
from ..exceptions import (
    BrowserAuthenticationError,
    CredentialEndpointMismatchError,
    ReauthenticationRequiredError,
)
from . import _loopback
from ._credential import _is_token

_MAX_DOCUMENT = 64 * 1024
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


def _request_json(
    http: httpx.Client, method: str, url: str, form: dict[str, str] | None = None,
) -> tuple[int, dict]:
    failure = "The identity service returned invalid JSON."
    try:
        with http.stream(method, url, data=form, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code not in (200, 400):
                raise BrowserAuthenticationError("The identity service rejected the request.")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise BrowserAuthenticationError("The identity service returned an unsupported encoding.")
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=16 * 1024):
                if len(body) + len(chunk) > _MAX_DOCUMENT:
                    raise BrowserAuthenticationError("The identity service response exceeded the size limit.")
                body.extend(chunk)
            document = json.loads(body)
            if isinstance(document, dict):
                return response.status_code, document
    except (ValueError, RecursionError):
        pass
    except httpx.HTTPError:
        # The original exception retains the HTTP request, which may contain a token.
        failure = "Could not reach the identity service."
    raise BrowserAuthenticationError(failure)


@dataclass(frozen=True, repr=False)
class _Tokens:
    access: str
    refresh: str | None
    expires_at: float
    refresh_at: float


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
        self._verify = True if ca_bundle is None else ssl.create_default_context(cafile=str(ca_bundle))
        self._login_timeout = login_timeout
        self._refresh_margin = refresh_margin
        self._redirect_port = redirect_port
        self._redirect_path = redirect_path
        self._tokens: _Tokens | None = None
        self._reauthenticate = False
        self._refresh_failed_at = float("-inf")
        self._lock = Lock()

    def _http(self) -> httpx.Client:
        return httpx.Client(
            verify=self._verify, timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False, trust_env=False,
        )

    def _discover(self) -> tuple[str, str]:
        if self._endpoints is None:
            url = self._issuer.rstrip("/") + "/.well-known/openid-configuration"
            with self._http() as http:
                status, metadata = _request_json(http, "GET", url)
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
        started = monotonic()
        with self._http() as http:
            status, document = _request_json(http, "POST", url, {"client_id": self._client_id, **form})
        if status == 400 and document.get("error") == "invalid_grant" and previous_refresh is not None:
            self._tokens = None
            self._reauthenticate = True
            raise ReauthenticationRequiredError(_SIGN_IN_AGAIN)
        if status != 200:
            raise BrowserAuthenticationError("The identity service rejected the token request.")
        access = document.get("access_token")
        lifetime = document.get("expires_in")
        token_type = document.get("token_type")
        refresh = document.get("refresh_token", previous_refresh)
        if (not isinstance(access, str) or not _is_token(access)
                or not isinstance(token_type, str) or token_type.lower() != "bearer"
                or type(lifetime) is not int or lifetime <= 0 or lifetime > 2**31 - 1
                or (refresh is not None and not _is_token(refresh))):
            raise BrowserAuthenticationError("The identity service returned an invalid token response.")
        expires_at = started + lifetime
        if monotonic() >= expires_at:
            raise BrowserAuthenticationError("The identity service returned an expired access token.")
        return _Tokens(access, refresh, expires_at, expires_at - min(self._refresh_margin, lifetime / 2))

    def _sign_in(self) -> _Tokens:
        try:
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
        except BaseException:
            if self._tokens is None:
                self._reauthenticate = True
            raise

    def authenticate(self) -> None:
        """Open the browser and replace the cached session after successful sign-in."""
        with self._lock:
            self._tokens = self._sign_in()
            self._reauthenticate = False
            self._refresh_failed_at = float("-inf")

    def _get_token(self, *, endpoint: str, scopes: frozenset[Scope]) -> str:
        if endpoint != self._endpoint:
            raise CredentialEndpointMismatchError("The credential is bound to another NOMAD deployment.")
        requested_at = monotonic()
        with self._lock:
            if self._reauthenticate:
                raise ReauthenticationRequiredError(_SIGN_IN_AGAIN)
            tokens = self._tokens
            if tokens is None:
                tokens = self._tokens = self._sign_in()
            elif tokens.refresh is not None and monotonic() >= tokens.refresh_at:
                if requested_at <= self._refresh_failed_at:
                    raise BrowserAuthenticationError("NOMAD token refresh failed. Retry the operation.")
                _, token_endpoint = self._discover()
                try:
                    tokens = self._tokens = self._exchange(token_endpoint, {
                        "grant_type": "refresh_token", "refresh_token": tokens.refresh,
                    }, previous_refresh=tokens.refresh)
                except BrowserAuthenticationError:
                    self._refresh_failed_at = monotonic()
                    raise
            elif monotonic() >= tokens.expires_at:
                self._tokens = None
                self._reauthenticate = True
                raise ReauthenticationRequiredError(_SIGN_IN_AGAIN)
            return tokens.access

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("Browser credentials cannot be pickled. Construct one on the user's machine.")
