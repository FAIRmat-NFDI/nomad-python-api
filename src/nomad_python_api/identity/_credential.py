from .._core._endpoint import normalize_endpoint
from .._scopes import Scope
from ..exceptions import CredentialEndpointMismatchError


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


class BearerTokenCredential:
    """Supply an existing PAT or Keycloak access token for one deployment.

    Args:
        token: The original access token string without the Bearer prefix.
        endpoint: The deployment alias or complete API base URL. Defaults to Central.
    """

    def __init__(self, token: str, *, endpoint: str = "prod") -> None:
        if not _is_token(token):
            raise ValueError("Supply a nonempty bearer token without whitespace.")
        self._token = token
        self._endpoint = normalize_endpoint(endpoint)

    def _get_token(self, *, endpoint: str, scopes: frozenset[Scope]) -> str:
        """Supply the opaque token. NOMAD checks the requested permissions."""
        _require_endpoint(self._endpoint, endpoint)
        return self._token

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("Bearer credentials cannot be pickled. Construct one in the worker.")
