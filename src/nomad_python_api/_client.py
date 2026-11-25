from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from types import TracebackType

from ._core._pipeline import RequestPipeline
from ._network import ConnectionLimits, NetworkTimeouts
from ._scopes import Scope
from .identity import BearerTokenCredential, BrowserCredential, PasswordCredential
from .identity._operations import IdentityOperations


class NomadClient:
    """Use a bearer credential to call a NOMAD deployment.

    Args:
        credential: The credential whose bound API endpoint selects the deployment.
        allowed_scopes: Optional local limit on the operations the client attempts.
        ca_bundle: Optional PEM CA bundle for a deployment using a private CA.
        pool_limits: Optional limits for the client's API connection pool.
        timeouts: Optional per-phase timeouts for the client's API requests.
    """

    def __init__(
        self,
        *,
        credential: BearerTokenCredential | BrowserCredential | PasswordCredential,
        allowed_scopes: Iterable[Scope] | None = None,
        ca_bundle: str | PathLike[str] | None = None,
        pool_limits: ConnectionLimits | None = None,
        timeouts: NetworkTimeouts | None = None,
    ) -> None:
        self._pipeline = RequestPipeline(
            endpoint=credential._endpoint,
            credential=credential,
            allowed_scopes=allowed_scopes,
            ca_bundle=ca_bundle,
            pool_limits=pool_limits,
            timeouts=timeouts,
        )
        self._identity = IdentityOperations(self._pipeline)

    @property
    def identity(self) -> IdentityOperations:
        """Operations on the identity associated with this credential."""
        return self._identity

    @property
    def allowed_scopes(self) -> frozenset[Scope] | None:
        """Return the immutable local policy, or None for no local restriction."""
        return self._pipeline.allowed_scopes

    def close(self) -> None:
        """Close the client's HTTP connection pool."""
        self._pipeline.close()

    def __enter__(self) -> NomadClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("NOMAD clients cannot be pickled. Construct one in the worker.")
