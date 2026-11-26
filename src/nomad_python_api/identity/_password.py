"""Password credentials for deployments that enable the NOMAD password grant."""

from __future__ import annotations

import os
from collections.abc import Iterable
from math import isfinite
from os import PathLike

from .._core._endpoint import normalize_endpoint
from .._scopes import Scope
from ..exceptions import PasswordAuthenticationError
from . import _token
from ._credential import _require_endpoint, _scope_names
from ._token import _TokenSession, _Tokens, _identity_tls, _read_tokens, _request_json


class PasswordCredential:
    """Exchange a NOMAD username and password for a deployment-bound token.

    Supply the credentials as a pair or set NOMAD_USERNAME and NOMAD_PASSWORD.
    Construction reads the pair once. The credential retains it in memory for
    on-demand renewal through the deployment's password grant.

    ``requested_scopes`` is sent as the OAuth ``scope`` form field. Standard
    NOMAD ignores it and issues the account's full permissions. Use
    ``NomadClient(enforced_scopes=...)`` for a reliable local restriction.
    """

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        endpoint: str = "prod",
        ca_bundle: str | PathLike[str] | None = None,
        refresh_margin: float = 30,
        requested_scopes: Iterable[Scope | str] | None = None,
    ) -> None:
        if username is None and password is None:
            username = os.environ.get("NOMAD_USERNAME")
            password = os.environ.get("NOMAD_PASSWORD")
        if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
            raise ValueError("Provide both username and password, or set both NOMAD_USERNAME and NOMAD_PASSWORD.")
        if not isfinite(refresh_margin) or refresh_margin < 0:
            raise ValueError("refresh_margin must be finite and nonnegative.")
        self._requested_scopes = _scope_names(requested_scopes)
        self._endpoint = normalize_endpoint(endpoint)
        self._username = username
        self._password = password
        self._verify = _identity_tls(ca_bundle)
        self._refresh_margin = refresh_margin
        self._session = _TokenSession(
            PasswordAuthenticationError,
            lambda: PasswordAuthenticationError(
                "NOMAD rejected password sign-in. Check the account and deployment settings, "
                "then call credential.authenticate() or create a new credential."
            ),
        )

    @property
    def requested_scopes(self) -> tuple[str, ...] | None:
        """Return the scope names sent at sign-in, or None when the field is omitted."""
        return self._requested_scopes

    @property
    def granted_scopes(self) -> None:
        """Return None because NOMAD does not report the token's grants."""
        return None

    def _sign_in(self) -> _Tokens:
        started = _token.monotonic()
        form = {"grant_type": "password", "username": self._username, "password": self._password}
        if self._requested_scopes is not None:
            form["scope"] = " ".join(self._requested_scopes)
        status, document = _request_json(
            "POST", self._endpoint + "/auth/token",
            verify=self._verify, error=PasswordAuthenticationError, form=form,
        )
        if status in (401, 403) or (status == 400 and document.get("error") == "invalid_grant"):
            self._session.require_sign_in()
        if status != 200:
            raise PasswordAuthenticationError(f"NOMAD password sign-in failed with HTTP {status}.")
        return _read_tokens(
            document, started=started, margin=self._refresh_margin,
            error=PasswordAuthenticationError, renew_with_login=True,
        )

    def _renew(self, _tokens: _Tokens) -> _Tokens:
        return self._sign_in()

    def authenticate(self) -> None:
        """Repeat the password exchange and cache the returned access token."""
        self._session.authenticate(self._sign_in)

    def _get_token(self, *, endpoint: str, scopes: frozenset[Scope]) -> str:
        _require_endpoint(self._endpoint, endpoint)
        return self._session.access_token(self._sign_in, self._renew)

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("Password credentials cannot be pickled. Construct one in the worker.")
