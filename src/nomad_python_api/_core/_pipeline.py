import json
import ssl
from collections.abc import Iterable
from os import PathLike
from typing import Protocol

import httpx

from .._scopes import Scope
from ..exceptions import (
    AuthorizationError,
    ClientAuthenticationError,
    HttpResponseError,
    InvalidResponseError,
    RateLimitError,
    ScopeNotAllowedError,
    TransportError,
)
from ._endpoint import normalize_endpoint
from ._operation import Operation

_MAX_RESPONSE_BYTES = 256 * 1024
_HTTP_ERRORS = {401: ClientAuthenticationError, 403: AuthorizationError, 429: RateLimitError}


class _Credential(Protocol):
    def _get_token(self, *, endpoint: str, scopes: frozenset[Scope]) -> str: ...


class RequestPipeline:
    """Apply shared scope, credential, and transport rules to an operation."""

    def __init__(
        self,
        *,
        endpoint: str,
        credential: _Credential,
        allowed_scopes: Iterable[Scope] | None,
        ca_bundle: str | PathLike[str] | None,
    ) -> None:
        self._endpoint = normalize_endpoint(endpoint)
        self._credential = credential
        scopes = None if allowed_scopes is None else tuple(allowed_scopes)
        if scopes is not None and any(not isinstance(scope, Scope) for scope in scopes):
            raise TypeError("allowed_scopes must contain Scope members.")
        self.allowed_scopes = None if scopes is None else frozenset(scopes)
        verify = True if ca_bundle is None else ssl.create_default_context(cafile=str(ca_bundle))
        self._http = httpx.Client(
            verify=verify,
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=False,
            trust_env=False,
        )

    def send(self, operation: Operation) -> object:
        if self._http.is_closed:
            raise RuntimeError("The NOMAD client is closed.")
        info = operation.info
        if self.allowed_scopes is not None:
            missing = info.required_scopes - self.allowed_scopes
            if missing:
                raise ScopeNotAllowedError(info.name, missing)
        token = self._credential._get_token(endpoint=self._endpoint, scopes=info.required_scopes)
        try:
            with self._http.stream(
                operation.method,
                self._endpoint + operation.path,
                headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code != 200:
                    error = _HTTP_ERRORS.get(response.status_code, HttpResponseError)
                    raise error(info.name, response.status_code)
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise InvalidResponseError(f"{info.name} returned an unsupported content encoding.")
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    if len(content) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise InvalidResponseError(f"{info.name} response exceeded the size limit.")
                    content.extend(chunk)
        except httpx.TransportError:
            pass
        else:
            try:
                return json.loads(content)
            except (ValueError, RecursionError):
                pass
            raise InvalidResponseError(f"{info.name} returned invalid JSON.")
        raise TransportError(f"{info.name} could not reach NOMAD or exceeded a network timeout.")

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()
