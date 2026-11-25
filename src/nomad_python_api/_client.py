from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from types import TracebackType

from ._core._pipeline import RequestPipeline
from ._scopes import Scope
from .identity import BearerTokenCredential, BrowserCredential
from .identity._operations import IdentityOperations


class NomadClient:
    """Use a bearer credential to call a NOMAD deployment.

    Args:
        endpoint: The deployment alias or complete HTTPS API base URL. Defaults to Central.
        credential: A bearer credential bound to that deployment.
        allowed_scopes: Optional local limit on the operations the client attempts.
        ca_bundle: Optional PEM CA bundle for a deployment using a private CA.
    """

    def __init__(
        self,
        *,
        endpoint: str = "prod",
        credential: BearerTokenCredential | BrowserCredential,
        allowed_scopes: Iterable[Scope] | None = None,
        ca_bundle: str | PathLike[str] | None = None,
    ) -> None:
        self._pipeline = RequestPipeline(
            endpoint=endpoint,
            credential=credential,
            allowed_scopes=allowed_scopes,
            ca_bundle=ca_bundle,
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
