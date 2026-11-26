"""Generic ownership-transfer operations and models."""

from ._models import (
    OwnershipResourceRef,
    OwnershipResourceType,
    OwnershipTransfer,
    OwnershipTransferActionResult,
    OwnershipTransferBatchResult,
    OwnershipTransferCreateRequest,
    OwnershipTransferDirection,
    OwnershipTransferFailure,
)
from ._operations import BoundOwnershipTransferOperations, OwnershipTransferOperations

__all__ = [
    "BoundOwnershipTransferOperations", "OwnershipResourceRef", "OwnershipResourceType",
    "OwnershipTransfer", "OwnershipTransferActionResult", "OwnershipTransferBatchResult",
    "OwnershipTransferCreateRequest", "OwnershipTransferDirection", "OwnershipTransferFailure",
    "OwnershipTransferOperations",
]
