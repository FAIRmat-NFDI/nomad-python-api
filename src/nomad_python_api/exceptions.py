"""Exceptions raised by the NOMAD SDK."""

from ._scopes import Scope

__all__ = [
    "AmbiguousUserError",
    "AuthorizationError",
    "BrowserAuthenticationError",
    "ClientAuthenticationError",
    "CredentialEndpointMismatchError",
    "GroupNotFoundError",
    "HttpResponseError",
    "IdentityWriteOutcomeUnknownError",
    "InvalidResponseError",
    "NomadError",
    "PatNotFoundError",
    "PatRequestError",
    "PatWriteOutcomeUnknownError",
    "PasswordAuthenticationError",
    "PoolTimeoutError",
    "RateLimitError",
    "ReauthenticationRequiredError",
    "ScopeNotAllowedError",
    "TransportError",
    "UserNotFoundError",
]


class NomadError(Exception):
    """Base class for SDK request failures."""


class ScopeNotAllowedError(NomadError):
    """The client's local policy blocked the operation before HTTP."""

    def __init__(self, operation: str, missing_scopes: frozenset[Scope]) -> None:
        self.operation = operation
        self.missing_scopes = missing_scopes
        scope_names = ", ".join(sorted(scope.value for scope in missing_scopes))
        super().__init__(f"{operation} requires scopes outside this client's policy: {scope_names}.")


class CredentialEndpointMismatchError(NomadError):
    """The supplied credential is bound to a different deployment."""


class BrowserAuthenticationError(NomadError):
    """Interactive sign-in or communication with the identity service failed."""


class ReauthenticationRequiredError(BrowserAuthenticationError):
    """The caller must start a new interactive sign-in."""


class PasswordAuthenticationError(NomadError):
    """NOMAD password sign-in or token acquisition failed."""


class HttpResponseError(NomadError):
    """NOMAD returned an unsuccessful or unexpected status."""

    def __init__(self, operation: str, status_code: int, *, guidance: str | None = None) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"{operation} failed with HTTP {status_code}. {guidance or self._guidance}")

    _guidance = "Check the operation and deployment."


class ClientAuthenticationError(HttpResponseError):
    """NOMAD rejected authentication with HTTP 401."""

    _guidance = "Check the token and its issuing deployment."


class AuthorizationError(HttpResponseError):
    """NOMAD refused access with HTTP 403."""

    _guidance = "Check the token's scopes and the account's resource access."


class RateLimitError(HttpResponseError):
    """NOMAD throttled the request with HTTP 429."""

    _guidance = "Wait before issuing another request."


class TransportError(NomadError):
    """A connection, timeout, or other HTTP transport failure occurred."""


class PoolTimeoutError(TransportError):
    """An API request timed out waiting for a connection before it was sent."""


class InvalidResponseError(NomadError):
    """The response could not be safely interpreted as the expected model."""


class PatRequestError(HttpResponseError):
    """NOMAD rejected the PAT request or the state of its target."""


class PatNotFoundError(HttpResponseError):
    """NOMAD could not find a PAT accessible to the caller."""

    _guidance = "Check the PAT ID, account, and deployment."


class UserNotFoundError(NomadError):
    """The exact user lookup returned no accessible user."""


class AmbiguousUserError(NomadError):
    """The exact selector matched more than one user."""


class GroupNotFoundError(HttpResponseError):
    """NOMAD could not find an accessible group."""

    _guidance = "Check the group ID, account, and deployment."


class IdentityWriteOutcomeUnknownError(NomadError):
    """A user or group write may have taken effect."""

    def __init__(self, operation: str, status_code: int | None = None) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"The outcome of {operation} is unknown. Verify server state before another write.")


class PatWriteOutcomeUnknownError(NomadError):
    """A PAT write may have taken effect before its outcome could be confirmed."""

    def __init__(
        self, operation: str, status_code: int | None = None, *, guidance: str | None = None
    ) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(
            f"The outcome of {operation} is unknown. "
            f"{guidance or 'Check your PATs in NOMAD before retrying.'}"
        )
