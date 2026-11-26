import json
from collections.abc import Iterable, Mapping
from contextlib import closing
from os import PathLike
from typing import Protocol
from urllib.parse import quote

import httpx
from httpx import Client as _HTTPClient

from .._network import ConnectionLimits, NetworkTimeouts
from .._scopes import Scope
from ..exceptions import (
    AuthorizationError,
    ClientAuthenticationError,
    HttpResponseError,
    InvalidResponseError,
    PoolTimeoutError,
    RateLimitError,
    ScopeNotAllowedError,
    TransportError,
)
from ._endpoint import normalize_endpoint
from ._operation import Operation
from ._transport import NomadTransport, _BorrowedTransport, _httpx_limits, _tls

_MAX_RESPONSE_BYTES = 256 * 1024
_HTTP_ERRORS = {401: ClientAuthenticationError, 403: AuthorizationError, 429: RateLimitError}


def _status_error(operation: str, status_code: int) -> HttpResponseError:
    return _HTTP_ERRORS.get(status_code, HttpResponseError)(operation, status_code)


def _confirmed_status(error: httpx.HTTPStatusError, request: httpx.Request) -> int | None:
    try:
        if error.request is request and error.response.request is request:
            return error.response.status_code
    except RuntimeError:
        # A hook can raise a status error without a request on its response.
        pass
    return None


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
        pool_limits: ConnectionLimits | None,
        timeouts: NetworkTimeouts | None,
        transport: NomadTransport | None,
        http_client: _HTTPClient | None,
    ) -> None:
        self._endpoint = normalize_endpoint(endpoint)
        self._credential = credential
        scopes = None if allowed_scopes is None else tuple(allowed_scopes)
        if scopes is not None and any(not isinstance(scope, Scope) for scope in scopes):
            raise TypeError("allowed_scopes must contain Scope members.")
        self.allowed_scopes = None if scopes is None else frozenset(scopes)
        self._closed = False
        self._transport = transport
        self._owns_http = http_client is None
        if http_client is not None:
            if not isinstance(http_client, _HTTPClient):
                raise TypeError("http_client must be a synchronous httpx.Client.")
            if any(option is not None for option in (transport, ca_bundle, pool_limits, timeouts)):
                raise ValueError("http_client supplies transport, CA trust, pool limits, and timeouts.")
            if http_client.is_closed:
                raise ValueError("http_client is closed.")
            self._http = http_client
            return

        if timeouts is not None and not isinstance(timeouts, NetworkTimeouts):
            raise TypeError("timeouts must be a NetworkTimeouts instance.")
        if transport is not None:
            if not isinstance(transport, NomadTransport):
                raise TypeError("transport must be a NomadTransport instance.")
            if ca_bundle is not None or pool_limits is not None:
                raise ValueError("Configure CA trust and pool limits on transport.")
            if transport.is_closed:
                raise ValueError("transport is closed.")
        timeouts = NetworkTimeouts() if timeouts is None else timeouts
        network = (
            {"transport": _BorrowedTransport(transport)}
            if transport is not None
            else {"verify": _tls(ca_bundle), "limits": _httpx_limits(pool_limits)}
        )
        self._http = httpx.Client(
            timeout=httpx.Timeout(
                connect=timeouts.connect, pool=timeouts.pool, read=timeouts.read, write=timeouts.write,
            ),
            follow_redirects=False,
            trust_env=False,
            **network,
        )

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def is_closed(self) -> bool:
        return self._closed or self._http.is_closed

    def send(
        self,
        operation: Operation,
        *,
        path_parameters: Mapping[str, str] | None = None,
        query: httpx.QueryParams | None = None,
        json_body: dict[str, object] | None = None,
    ) -> object:
        if self.is_closed:
            raise RuntimeError("The NOMAD client is closed.")
        if self._transport is not None and self._transport.is_closed:
            raise RuntimeError("The NOMAD transport is closed.")
        info = operation.info
        if self.allowed_scopes is not None:
            missing = info.required_scopes - self.allowed_scopes
            if missing:
                raise ScopeNotAllowedError(info.name, missing)
        token = self._credential._get_token(endpoint=self._endpoint, scopes=info.required_scopes)
        path = operation.path
        if path_parameters:
            path = path.format(**{key: quote(value, safe="") for key, value in path_parameters.items()})
        try:
            with closing(self._send_request(operation, token, path, query, json_body)) as response:
                if response.status_code != operation.success_status:
                    raise _status_error(info.name, response.status_code)
                if operation.success_status == 204:
                    return None
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise InvalidResponseError(f"{info.name} returned an unsupported content encoding.")
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    if len(content) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise InvalidResponseError(f"{info.name} response exceeded the size limit.")
                    content.extend(chunk)
        except httpx.TransportError as error:
            failure = TransportError(
                f"{info.name} could not reach NOMAD or exceeded a network timeout."
            )
            if self._owns_http and isinstance(error, httpx.PoolTimeout):
                failure = PoolTimeoutError(
                    f"{info.name} timed out waiting for a connection before sending the request."
                )
        else:
            try:
                return json.loads(content)
            except (ValueError, RecursionError):
                pass
            raise InvalidResponseError(f"{info.name} returned invalid JSON.")
        raise failure

    def _send_request(
        self,
        operation: Operation,
        token: str,
        path: str,
        query: httpx.QueryParams | None,
        json_body: dict[str, object] | None,
    ) -> httpx.Response:
        url = httpx.URL(self._endpoint + path)
        request = None
        status_code = None
        try:
            # Borrow the HTTP session without merging service-specific request defaults.
            build_request = self._http.build_request if self._owns_http else httpx.Request
            request = build_request(
                operation.method,
                url,
                params=query,
                json=json_body,
                headers={
                    "Host": url.netloc.decode("ascii"),
                    "Authorization": f"Bearer {token}",
                    "Accept-Encoding": "identity",
                },
            )
            return self._http.send(request, stream=True, auth=None, follow_redirects=False)
        except Exception as error:
            if self._owns_http:
                raise
            if request is not None and isinstance(error, httpx.HTTPStatusError):
                status_code = _confirmed_status(error, request)
        if status_code is not None and status_code != operation.success_status:
            raise _status_error(operation.info.name, status_code)
        # A borrowed hook can fail even after NOMAD accepted the request.
        raise TransportError(
            f"{operation.info.name} failed in the borrowed HTTP client. "
            "The request may have reached NOMAD."
        )

    def close(self) -> None:
        """Close the SDK session while leaving caller-owned resources open."""
        if not self._closed:
            self._closed = True
            if self._owns_http:
                self._http.close()
