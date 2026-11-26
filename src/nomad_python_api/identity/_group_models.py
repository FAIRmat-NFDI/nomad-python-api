from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, StrictStr, model_validator

from ._paging import Pagination

if TYPE_CHECKING:
    from ..ownership._operations import BoundOwnershipTransferOperations


class GroupRole(str, Enum):
    """A user's role in a NOMAD group."""

    OWNER = "owner"
    MAINTAINER = "maintainer"
    MEMBER = "member"


class GroupMember(BaseModel):
    """A role-bearing user reference in a group."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    user_id: StrictStr = Field(min_length=1, repr=False)
    role: GroupRole = GroupRole.MEMBER


class Group(BaseModel):
    """A NOMAD user group and its available membership information."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    _endpoint: str | None = PrivateAttr(default=None)
    _ownership_transfers: BoundOwnershipTransferOperations | None = PrivateAttr(default=None)

    group_id: StrictStr = Field(min_length=1)
    name: StrictStr = "Default Group Name"
    description: StrictStr | None = None
    owner_id: StrictStr = Field(min_length=1, repr=False)
    member_ids: tuple[StrictStr, ...] | None = Field(default=None, repr=False)
    members: tuple[GroupMember, ...] | None = None

    @property
    def ownership_resource_type(self) -> str:
        """Return the REST resource type used for ownership transfer."""
        return "group"

    @property
    def ownership_resource_id(self) -> str:
        """Return this group's transferable resource identifier."""
        return self.group_id

    @property
    def ownership_transfers(self) -> BoundOwnershipTransferOperations:
        """Return transfer operations bound to this group and client."""
        if self._ownership_transfers is None:
            raise RuntimeError("The group is not bound to a NOMAD client.")
        return self._ownership_transfers

    @model_validator(mode="before")
    @classmethod
    def _from_wire(cls, value: object) -> object:
        if not isinstance(value, Mapping) or "owner" not in value:
            return value
        fields = dict(value)
        fields["owner_id"] = fields.pop("owner")
        if "group_name" in fields:
            fields["name"] = fields.pop("group_name")
        fields["member_ids"] = fields.pop("members", None)
        fields["members"] = fields.pop("members_info", None)
        return fields


class GroupPagination(Pagination):
    """Pagination metadata for a group listing."""


class GroupPage(BaseModel):
    """A group listing page and its optional pagination metadata."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    items: tuple[Group, ...] = Field(validation_alias="data")
    pagination: GroupPagination | None = None

    @property
    def next_cursor(self) -> str | None:
        return self.pagination.next_page_after_value if self.pagination is not None else None
