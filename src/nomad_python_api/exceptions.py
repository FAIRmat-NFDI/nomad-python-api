"""Exceptions raised by the NOMAD SDK."""

from ._scopes import Scope

__all__ = [
    "AuthorizationError",
    "BrowserAuthenticationError",
    "ClientAuthenticationError",
    "CredentialEndpointMismatchError",
    "HttpResponseError",
    "InvalidResponseError",
    "NomadError",
    "PasswordAuthenticationError",
    "RateLimitError",
    "ReauthenticationRequiredError",
    "ScopeNotAllowedError",
    "TransportError",
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

    def __init__(self, operation: str, status_code: int) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"{operation} failed with HTTP {status_code}. {self._guidance}")

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


class InvalidResponseError(NomadError):
    """The response could not be safely interpreted as the expected account."""
