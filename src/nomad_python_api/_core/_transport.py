"""Connection pools shared by clients in one process."""

from __future__ import annotations

import ssl
from os import PathLike
from types import TracebackType

import httpx

from .._network import ConnectionLimits


class NomadTransport:
    """Own a connection pool that several NOMAD clients can borrow."""

    def __init__(
        self,
        *,
        pool_limits: ConnectionLimits | None = None,
        ca_bundle: str | PathLike[str] | None = None,
    ) -> None:
        self._http = httpx.HTTPTransport(
            limits=_httpx_limits(pool_limits), verify=_tls(ca_bundle), trust_env=False,
        )
        self._closed = False

    @property
    def is_closed(self) -> bool:
        """Whether this pool has been closed."""
        return self._closed

    def close(self) -> None:
        """Close the pool after the clients using it have finished."""
        if not self._closed:
            self._closed = True
            self._http.close()

    def __enter__(self) -> NomadTransport:
        if self.is_closed:
            raise RuntimeError("The NOMAD transport is closed.")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class _BorrowedTransport(httpx.BaseTransport):
    def __init__(self, transport: NomadTransport) -> None:
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._transport.is_closed:
            raise RuntimeError("The NOMAD transport is closed.")
        return self._transport._http.handle_request(request)


def _httpx_limits(limits: ConnectionLimits | None) -> httpx.Limits:
    if limits is None:
        limits = ConnectionLimits()
    if not isinstance(limits, ConnectionLimits):
        raise TypeError("pool_limits must be a ConnectionLimits instance.")
    return httpx.Limits(
        max_connections=limits.max_connections,
        max_keepalive_connections=min(limits.max_keepalive_connections, limits.max_connections),
        keepalive_expiry=limits.keepalive_expiry,
    )


def _tls(ca_bundle: str | PathLike[str] | None) -> bool | ssl.SSLContext:
    return True if ca_bundle is None else ssl.create_default_context(cafile=str(ca_bundle))
