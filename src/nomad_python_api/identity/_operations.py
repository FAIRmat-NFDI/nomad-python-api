from types import MappingProxyType

from .._core._operation import Operation, OperationInfo
from .._core._pipeline import RequestPipeline
from .._scopes import Scope
from ..exceptions import InvalidResponseError
from ._account import Account

_OPERATIONS = MappingProxyType({
    "me": Operation(
        OperationInfo(
            "identity.me", "Get the authenticated NOMAD account.", frozenset({Scope.USERS_READ})
        ),
        method="GET",
        path="/users/me",
    ),
})


class IdentityOperations:
    """Operations on the identity associated with the client's credential."""

    def __init__(self, pipeline: RequestPipeline) -> None:
        self._pipeline = pipeline

    def get_operation_info(self, name: str) -> OperationInfo:
        """Return local metadata for an identity method, without a request.

        Args:
            name: The name of the identity method, such as `me`.

        Raises:
            KeyError: If the method has no operation declaration.
        """
        if name not in _OPERATIONS:
            raise KeyError("Unknown identity operation.")
        return _OPERATIONS[name].info

    def me(self) -> Account:
        """Get the account associated with the client's credential."""
        data = self._pipeline.send(_OPERATIONS["me"])
        if isinstance(data, dict):
            user_id = data.get("user_id")
            username = data.get("username")
            if (
                isinstance(user_id, str)
                and user_id
                and (username is None or isinstance(username, str))
            ):
                return Account(user_id, username)
        raise InvalidResponseError("identity.me returned an invalid account response.")
