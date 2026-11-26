from types import MappingProxyType

from pydantic import ValidationError

from .._core._operation import Operation, OperationInfo
from .._core._pipeline import RequestPipeline
from .._scopes import Scope
from ..exceptions import InvalidResponseError
from ._account import Account
from ._pats import PatOperations
from ._user import User

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
        self._pats = PatOperations(pipeline)

    @property
    def pats(self) -> PatOperations:
        """Manage the signed-in user's personal access tokens."""
        return self._pats

    def get_operation_info(self, name: str) -> OperationInfo:
        """Return local metadata for an identity method, without a request.

        Args:
            name: The name of the identity method, such as `me`.

        Raises:
            KeyError: If the method has no operation declaration.
        """
        if name.startswith("pats."):
            return self.pats.get_operation_info(name.removeprefix("pats."))
        if name not in _OPERATIONS:
            raise KeyError("Unknown identity operation.")
        return _OPERATIONS[name].info

    def me(self) -> Account:
        """Get the account associated with the client's credential."""
        data = self._pipeline.send(_OPERATIONS["me"])
        try:
            user = User.model_validate(data)
        except ValidationError:
            pass
        else:
            return Account._from_user(user, self.pats)
        raise InvalidResponseError("identity.me returned an invalid account response.")
