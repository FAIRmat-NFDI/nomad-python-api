from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, StrictStr

if TYPE_CHECKING:
    from ._operations import OwnershipTransferOperations


class OwnershipResourceType(str, Enum):
    """Built-in NOMAD resource types that support ownership transfer."""

    PROJECT = "upload"
    GROUP = "group"


class OwnershipTransferDirection(str, Enum):
    """Relationship of a transfer to the authenticated user."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    ALL = "all"


class OwnershipResourceRef(BaseModel):
    """An explicit transferable resource type and identifier."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    resource_type: StrictStr = Field(min_length=1)
    resource_id: StrictStr = Field(min_length=1)

    @classmethod
    def group(cls, group_id: str) -> OwnershipResourceRef:
        return cls(resource_type=OwnershipResourceType.GROUP.value, resource_id=group_id)

    @classmethod
    def project(cls, upload_id: str) -> OwnershipResourceRef:
        return cls(resource_type=OwnershipResourceType.PROJECT.value, resource_id=upload_id)


class OwnershipTransferCreateRequest(BaseModel):
    """The standard NOMAD ownership-transfer creation body."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    resource_type: StrictStr = Field(min_length=1)
    resource_id: StrictStr = Field(min_length=1)
    target_user: StrictStr = Field(min_length=1, repr=False)
    target_user_type: StrictStr = Field(pattern="^(user_id|username|email)$")


class OwnershipTransfer(BaseModel):
    """A transfer request returned by NOMAD and bound to its originating client."""

    model_config = ConfigDict(extra="allow", frozen=True, hide_input_in_errors=True)
    _operations: OwnershipTransferOperations | None = PrivateAttr(default=None)

    transfer_id: StrictStr = Field(min_length=1)
    resource_type: StrictStr = Field(min_length=1)
    resource_id: StrictStr = Field(min_length=1)
    resource_name: StrictStr | None = None
    source_user_id: StrictStr = Field(min_length=1, repr=False)
    target_user_id: StrictStr = Field(min_length=1, repr=False)
    requested_at: datetime
    updated_at: datetime
    actor_user_id: StrictStr | None = Field(default=None, repr=False)

    def accept(self) -> OwnershipTransferActionResult:
        return self._bound().accept(self)

    def refuse(self) -> OwnershipTransferActionResult:
        return self._bound().refuse(self)

    def cancel(self) -> OwnershipTransferActionResult:
        return self._bound().cancel(self)

    def _bound(self) -> OwnershipTransferOperations:
        if self._operations is None:
            raise RuntimeError("The ownership transfer is not bound to a NOMAD client.")
        return self._operations


class OwnershipTransferActionResult(BaseModel):
    """The confirmed response from accepting, refusing, or cancelling a transfer."""

    model_config = ConfigDict(extra="allow", frozen=True, hide_input_in_errors=True)

    transfer_id: StrictStr = Field(min_length=1)
    resource_type: StrictStr = Field(min_length=1)
    resource_id: StrictStr | None = None
    result: Mapping[str, Any] | None = None
    resource: object | None = Field(default=None, exclude=True)


@dataclass(frozen=True)
class OwnershipTransferFailure:
    """One failed item in a sequential bulk ownership-transfer action."""

    target: object = field(repr=False)
    error: Exception


@dataclass(frozen=True)
class OwnershipTransferBatchResult:
    """Ordered successes and failures from a sequential bulk action."""

    succeeded: tuple[OwnershipTransferActionResult, ...]
    failed: tuple[OwnershipTransferFailure, ...]
