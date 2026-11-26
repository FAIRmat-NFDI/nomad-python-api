import re
from typing import TypeGuard

from .._core._endpoint import normalize_endpoint
from .._scopes import Scope
from ..exceptions import CredentialEndpointMismatchError
from ._pat_models import PatIssuedResult

_PAT_ID = re.compile(r"[0-9a-fA-F]{24}")


def _is_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.isascii()
        and value.isprintable()
        and not any(character.isspace() for character in value)
    )


def _require_endpoint(bound_endpoint: str, requested_endpoint: str) -> None:
    if requested_endpoint != bound_endpoint:
        raise CredentialEndpointMismatchError("The credential is bound to another NOMAD deployment.")


def _is_pat_id(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and _PAT_ID.fullmatch(value) is not None


def _validate_pat_id(pat_id: object) -> str:
    if not _is_pat_id(pat_id):
        raise ValueError("Supply the 24-character hexadecimal PAT metadata ID.")
    return pat_id


class BearerTokenCredential:
    """Supply an existing PAT or Keycloak access token for one deployment.

    Args:
        token: The original access token string without the Bearer prefix.
        endpoint: The deployment alias or complete API base URL. Defaults to Central.
        pat_id: Optional 24-character hexadecimal metadata ID for PAT management.
    """

    def __init__(self, token: str, *, endpoint: str = "prod", pat_id: str | None = None) -> None:
        if not _is_token(token):
            raise ValueError("Supply a nonempty bearer token without whitespace.")
        self._token = token
        self._endpoint = normalize_endpoint(endpoint)
        self._pat_id = _validate_pat_id(pat_id) if pat_id is not None else None

    @property
    def pat_id(self) -> str | None:
        """Return the optional PAT metadata ID."""
        return self._pat_id

    @classmethod
    def from_issued(cls, issued: PatIssuedResult) -> "BearerTokenCredential":
        """Use a PAT returned by create or rotate on its issuing deployment."""
        if not isinstance(issued, PatIssuedResult) or issued.pat._endpoint is None:
            raise ValueError("Supply a PAT result issued by the SDK.")
        return cls(
            issued.raw_token.get_secret_value(), endpoint=issued.pat._endpoint, pat_id=issued.pat.id
        )

    def _get_token(self, *, endpoint: str, scopes: frozenset[Scope]) -> str:
        """Supply the opaque token. NOMAD checks the requested permissions."""
        _require_endpoint(self._endpoint, endpoint)
        return self._token

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("Bearer credentials cannot be pickled. Construct one in the worker.")
