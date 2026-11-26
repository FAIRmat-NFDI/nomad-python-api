from dataclasses import dataclass

from .._scopes import Scope


@dataclass(frozen=True)
class OperationInfo:
    """Description and required scopes of an SDK operation."""

    name: str
    description: str
    required_scopes: frozenset[Scope]


@dataclass(frozen=True)
class Operation:
    """The private REST contract behind an SDK operation."""

    info: OperationInfo
    method: str
    path: str
    success_status: int = 200
