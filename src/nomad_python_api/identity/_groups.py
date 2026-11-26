from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx
from pydantic import ValidationError

from .._core._operation import Operation, OperationInfo
from .._core._pipeline import RequestPipeline
from .._scopes import Scope
from ..exceptions import GroupNotFoundError, HttpResponseError, InvalidResponseError
from ._account import Account
from ._credential import _require_endpoint
from ._directory_support import directory_id, json_extension, send_directory_write
from ._group_models import Group, GroupMember, GroupPage, GroupRole
from ._group_paging import GroupList
from ._user import User
from ._users import UserOperations, _exact_selector
from ..ownership._operations import OwnershipTransferOperations

_BASE = "/groups"
_TARGET = _BASE + "/{group_id}"
_READ = frozenset({Scope.GROUPS_READ})
_WRITE = frozenset({Scope.GROUPS_WRITE})
_OPERATIONS = {
    "list": Operation(OperationInfo("identity.groups.list", "List groups.", _READ), "GET", _BASE),
    "get": Operation(OperationInfo("identity.groups.get", "Get a group.", _READ), "GET", _TARGET),
    "create": Operation(OperationInfo("identity.groups.create", "Create a group.", _WRITE), "POST", _BASE, 201),
    "update": Operation(OperationInfo(
        "identity.groups.update", "Update group metadata or legacy membership.", _WRITE,
    ), "POST", _TARGET + "/edit"),
    "replace_members": Operation(OperationInfo(
        "identity.groups.replace_members", "Replace group membership.", _WRITE,
    ), "POST", _TARGET + "/edit"),
    "delete": Operation(OperationInfo(
        "identity.groups.delete", "Delete a group.", frozenset({Scope.GROUPS_DELETE}),
    ), "DELETE", _TARGET, 204),
}
_BODY_FIELDS = {
    "group_id", "group_name", "description", "owner", "owner_id", "member_ids",
    "members", "members_info", "name", "legacy_member_ids",
}
_UserRef = User | Account | str | Mapping[str, str]
_MemberRef = _UserRef | GroupMember


class GroupOperations:
    """List and manage user groups on the client's deployment."""

    def __init__(
        self,
        pipeline: RequestPipeline,
        users: UserOperations,
        ownership_transfers: OwnershipTransferOperations,
    ) -> None:
        self._pipeline = pipeline
        self._users = users
        self._ownership_transfers = ownership_transfers

    def get_operation_info(self, name: str) -> OperationInfo:
        return _OPERATIONS[name].info

    def list(
        self, *, limit: int | None = None, extra_query: Mapping[str, object] | None = None,
        **filters: object,
    ) -> GroupList:
        """Return a lazy group listing."""
        if self._pipeline.is_closed:
            raise RuntimeError("The NOMAD client is closed.")
        return GroupList(self._page, filters, limit=limit, extra_query=extra_query)

    def get(self, target: Group | str) -> Group:
        """Get a group by its metadata ID."""
        operation = _OPERATIONS["get"]
        try:
            data = self._pipeline.send(operation, path_parameters={"group_id": self._group_id(target)})
        except HttpResponseError as error:
            if error.status_code == 404:
                raise GroupNotFoundError(error.operation, error.status_code) from None
            raise
        return self._group(data, operation)

    def create(
        self, *, name: str | None = None, description: str | None = None,
        members: Sequence[_MemberRef] | None = None,
        legacy_member_ids: Sequence[str] | None = None,
        extra_json: Mapping[str, object] | None = None,
    ) -> Group:
        """Create a group owned by the signed-in user."""
        operation = _OPERATIONS["create"]
        self._pipeline.check_operation(operation)
        body = self._edit_fields(name, description, legacy_member_ids, extra_json)
        if legacy_member_ids is not None and members is not None:
            raise ValueError("Choose role-bearing membership or legacy_member_ids.")
        if members is not None:
            records = self._members(None, members)
            if records:
                body["members_info"] = records
        result = self._write(operation, body=body)
        assert result is not None
        return result

    def update(
        self, target: Group | str, *, name: str | None = None, description: str | None = None,
        legacy_member_ids: Sequence[str] | None = None,
        extra_json: Mapping[str, object] | None = None,
    ) -> Group:
        """Update group metadata or submit an explicit legacy member list."""
        body = self._edit_fields(name, description, legacy_member_ids, extra_json)
        result = self._write(_OPERATIONS["update"], target=target, body=body)
        assert result is not None
        return result

    def replace_members(
        self, target: Group | str, *, members: Sequence[_MemberRef], owner: _UserRef | None = None,
        extra_json: Mapping[str, object] | None = None,
    ) -> Group:
        """Replace the role-bearing membership list, preserving the current owner."""
        operation = _OPERATIONS["replace_members"]
        self._pipeline.check_operation(operation)
        group_id = self._group_id(target)
        body = json_extension(extra_json, _BODY_FIELDS)
        existing_owner = target.owner_id if isinstance(target, Group) else None
        if owner is None:
            owner = existing_owner
        if owner is None:
            raise ValueError("Supply the current group owner when passing a group ID.")
        body["members_info"] = self._members(owner, members, expected_owner=existing_owner)
        result = self._write(operation, target=group_id, body=body)
        assert result is not None
        return result

    def delete(self, target: Group | str) -> None:
        """Delete a group."""
        self._write(_OPERATIONS["delete"], target=target)

    def _group_id(self, target: object) -> str:
        if isinstance(target, Group):
            self._check_endpoint(target._endpoint)
            target = target.group_id
        return directory_id(target)

    def _write(
        self, operation: Operation, *, target: Group | str | None = None,
        body: dict[str, object] | None = None,
    ) -> Group | None:
        path = {"group_id": self._group_id(target)} if operation is not _OPERATIONS["create"] else None
        try:
            group = send_directory_write(
                self._pipeline, operation, None if operation.success_status == 204 else Group,
                path=path, body=body,
            )
        except HttpResponseError as error:
            if error.status_code == 404 and path is not None:
                raise GroupNotFoundError(error.operation, error.status_code) from None
            raise
        if group is not None:
            self._ownership_transfers.bind_resource(group)
        return group

    def _page(self, query: httpx.QueryParams) -> GroupPage:
        data = self._pipeline.send(_OPERATIONS["list"], query=query)
        try:
            page = GroupPage.model_validate(data)
        except ValidationError:
            pass
        else:
            for group in page.items:
                self._ownership_transfers.bind_resource(group)
            return page
        raise InvalidResponseError("identity.groups.list returned an invalid group page.")

    def _group(self, data: object, operation: Operation) -> Group:
        try:
            group = Group.model_validate(data)
        except ValidationError:
            pass
        else:
            self._ownership_transfers.bind_resource(group)
            return group
        raise InvalidResponseError(f"{operation.info.name} returned an invalid group.")

    @staticmethod
    def _edit_fields(
        name: str | None, description: str | None, legacy_ids: Sequence[str] | None,
        extra_json: Mapping[str, object] | None,
    ) -> dict[str, object]:
        body = json_extension(extra_json, _BODY_FIELDS)
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Group name must be a nonempty string.")
            body["group_name"] = name
        if description is not None:
            if not isinstance(description, str):
                raise ValueError("Group description must be a string.")
            body["description"] = description
        if legacy_ids is not None:
            if not isinstance(legacy_ids, Sequence) or isinstance(legacy_ids, (str, bytes)):
                raise ValueError("Supply legacy_member_ids as a sequence of user IDs.")
            ids = [directory_id(value) for value in legacy_ids]
            if len(set(ids)) != len(ids):
                raise ValueError("Group member IDs must be unique.")
            body["members"] = ids
        return body

    def _members(
        self, owner: _UserRef | None, members: Sequence[_MemberRef], *, expected_owner: str | None = None,
    ) -> list[dict[str, str]]:
        if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
            raise ValueError("Supply members as a sequence of exact user references.")
        refs = [
            (self._user_ref(member.user_id), member.role) if isinstance(member, GroupMember)
            else (self._user_ref(member), GroupRole.MEMBER)
            for member in members
        ]
        if owner is None:
            if not refs:
                return []  # NOMAD supplies the owner when membership is omitted.
            if any(role is GroupRole.OWNER for _, role in refs):
                raise ValueError("NOMAD assigns the owner automatically. Supply only maintainers and members.")
            owner = self._users._get_me()
        owner_ref = self._user_ref(owner)
        lookups = [ref for ref in (owner_ref, *(ref for ref, _ in refs)) if isinstance(ref, tuple)]
        resolved = self._users.get_many([{key: value} for key, value in lookups])
        ids = {ref: directory_id(user.user_id) for ref, user in zip(lookups, resolved)}
        owner_id = ids[owner_ref] if isinstance(owner_ref, tuple) else owner_ref
        if expected_owner is not None and owner_id != expected_owner:
            raise ValueError("Membership replacement must preserve the current group owner.")
        seen: set[str] = set()
        records = [{"user_id": owner_id, "role": GroupRole.OWNER.value}]
        for ref, role in refs:
            user_id = ids[ref] if isinstance(ref, tuple) else ref
            if user_id in seen:
                raise ValueError("Group member IDs must be unique.")
            seen.add(user_id)
            if (user_id == owner_id) != (role == GroupRole.OWNER):
                raise ValueError("The group must have exactly one owner with the owner role.")
            if user_id != owner_id:
                records.append({"user_id": user_id, "role": role.value})
        return records

    def _user_ref(self, user: _UserRef) -> str | tuple[str, str]:
        if isinstance(user, Mapping):
            return _exact_selector(user)
        if isinstance(user, (User, Account)):
            self._check_endpoint(getattr(user, "_endpoint", None))
            user = user.user_id
        return directory_id(user)

    def _check_endpoint(self, endpoint: str | None) -> None:
        if endpoint is not None:
            _require_endpoint(endpoint, self._pipeline.endpoint)
