from .._core._operation import OperationInfo
from .._core._pipeline import RequestPipeline
from ._account import Account
from ._groups import GroupOperations
from ._pats import PatOperations
from ._users import _ME, UserOperations
from ..ownership._operations import OwnershipTransferOperations


class IdentityOperations:
    """Operations on the identity associated with the client's credential."""

    def __init__(
        self, pipeline: RequestPipeline, ownership_transfers: OwnershipTransferOperations
    ) -> None:
        self._pats = PatOperations(pipeline)
        self._users = UserOperations(pipeline)
        self._groups = GroupOperations(pipeline, self._users, ownership_transfers)

    @property
    def pats(self) -> PatOperations:
        """Manage the signed-in user's personal access tokens."""
        return self._pats

    @property
    def users(self) -> UserOperations:
        """Find and invite users on this deployment."""
        return self._users

    @property
    def groups(self) -> GroupOperations:
        """List and manage groups on this deployment."""
        return self._groups

    def get_operation_info(self, name: str) -> OperationInfo:
        """Return local metadata for an identity method, without a request.

        Args:
            name: The name of the identity method, such as `me`.

        Raises:
            KeyError: If the method has no operation declaration.
        """
        group, separator, method = name.partition(".")
        if separator and group in {"pats", "users", "groups"}:
            return getattr(self, group).get_operation_info(method)
        if name != "me":
            raise KeyError("Unknown identity operation.")
        return _ME.info

    def me(self) -> Account:
        """Get the account associated with the client's credential."""
        return Account._from_user(self._users._get_me(), self.pats)
