from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .._core._operation import Operation, OperationInfo
from .._core._pipeline import RequestPipeline
from .._scopes import Scope
from ..exceptions import (
    HttpResponseError,
    InvalidResponseError,
    OwnershipTransferNotFoundError,
    OwnershipTransferNotPendingError,
    OwnershipTransferOutcomeUnknownError,
    OwnershipTransferRequestError,
    PoolTimeoutError,
    TransportError,
)
from ..identity._credential import _require_endpoint
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

_BASE = "/ownership-transfers"
_TARGET = _BASE + "/{transfer_id}"
_READ = frozenset({Scope.UPLOADS_READ})
_WRITE = frozenset({Scope.UPLOADS_READ, Scope.UPLOADS_WRITE})
_OPERATIONS = {
    "list": Operation(OperationInfo("ownership_transfers.get", "List ownership transfers.", _READ), "GET", _BASE),
    "get": Operation(OperationInfo("ownership_transfers.get", "Get an ownership transfer.", _READ), "GET", _TARGET),
    "create": Operation(OperationInfo("ownership_transfers.create", "Create an ownership transfer.", _WRITE), "POST", _BASE),
    "accept": Operation(OperationInfo("ownership_transfers.accept", "Accept an ownership transfer.", _WRITE), "POST", _TARGET + "/respond"),
    "refuse": Operation(OperationInfo("ownership_transfers.refuse", "Refuse an ownership transfer.", _WRITE), "POST", _TARGET + "/respond"),
    "cancel": Operation(OperationInfo("ownership_transfers.cancel", "Cancel an ownership transfer.", _WRITE), "POST", _TARGET + "/cancel"),
}
_BUILT_INS = (OwnershipResourceType.PROJECT.value, OwnershipResourceType.GROUP.value)
_SAFE_VALUE = re.compile(r"[^\x00-\x1f\x7f]+")
_RESERVED_QUERY = {"direction", "resource_type", "resource_id", "state"}
_RESERVED_BODY = {
    "resource_type", "resource_id", "target_user", "target_user_type", "resource", "target",
}
_Model = TypeVar("_Model", bound=BaseModel)
_TransferTarget = OwnershipTransfer | Mapping[str, object] | str


class BoundOwnershipTransferOperations:
    """Ownership-transfer operations pre-bound to one resource."""

    def __init__(self, operations: OwnershipTransferOperations, resource: object) -> None:
        self._operations = operations
        self._resource = resource

    def create(self, *, target: object, extra_json: Mapping[str, object] | None = None) -> OwnershipTransfer:
        return self._operations.create(resource=self._resource, target=target, extra_json=extra_json)

    def get(self, target: _TransferTarget | None = None, **filters: object) -> OwnershipTransfer | list[OwnershipTransfer]:
        resource_type, resource_id = self._operations._resource_ref(self._resource)
        if target is not None:
            return self._operations.get(target, resource_type=resource_type)
        if "resource_type" in filters or "resource_id" in filters:
            raise ValueError("The bound resource already supplies resource_type and resource_id.")
        return self._operations.get(resource_type=resource_type, resource_id=resource_id, **filters)


class OwnershipTransferOperations:
    """Create, discover, and act on ownership transfers."""

    def __init__(self, pipeline: RequestPipeline) -> None:
        self._pipeline = pipeline

    def get_operation_info(self, name: str) -> OperationInfo:
        return _OPERATIONS[name].info

    def for_resource(self, resource: object) -> BoundOwnershipTransferOperations:
        return BoundOwnershipTransferOperations(self, resource)

    def create(
        self,
        request: OwnershipTransferCreateRequest | Mapping[str, object] | None = None,
        *,
        resource: object | None = None,
        target: object | None = None,
        extra_json: Mapping[str, object] | None = None,
    ) -> OwnershipTransfer:
        """Create a pending transfer from a complete request or resource and target."""
        if request is not None:
            if resource is not None or target is not None:
                raise ValueError("Choose a complete request or separate resource and target inputs.")
            options = self._create_request(request)
        else:
            if resource is None or target is None:
                raise ValueError("Supply both resource and target.")
            resource_type, resource_id = self._resource_ref(resource)
            target_user, target_user_type = self._target_ref(target)
            options = OwnershipTransferCreateRequest(
                resource_type=resource_type,
                resource_id=resource_id,
                target_user=target_user,
                target_user_type=target_user_type,
            )
        body = options.model_dump(mode="json")
        body.update(self._extra_json(extra_json))
        result = self._parse_write("create", OwnershipTransfer, self._send_write("create", body=body))
        return self._bind(result)

    def get(
        self,
        target: _TransferTarget | None = None,
        *,
        resource_type: OwnershipResourceType | str | None = None,
        direction: OwnershipTransferDirection | str = OwnershipTransferDirection.ALL,
        resource_id: str | None = None,
        state: str | None = None,
        extra_query: Mapping[str, object] | None = None,
    ) -> OwnershipTransfer | list[OwnershipTransfer]:
        """Get one transfer, or list matching transfers when target is omitted."""
        selected_type = None if resource_type is None else self._resource_type(resource_type)
        if target is not None:
            if resource_id is not None or state is not None or direction != OwnershipTransferDirection.ALL:
                raise ValueError("Listing filters cannot be combined with a transfer target.")
            transfer_id, target_type = self._transfer_ref(target)
            if selected_type is not None and target_type is not None and selected_type != target_type:
                raise ValueError("resource_type conflicts with the transfer target.")
            return self._get_one(transfer_id, selected_type or target_type, extra_query)

        query_types = _BUILT_INS if selected_type is None else (selected_type,)
        transfers: list[OwnershipTransfer] = []
        for query_type in query_types:
            query = self._list_query(direction, query_type, resource_id, state, extra_query)
            data = self._pipeline.send(_OPERATIONS["list"], query=query)
            try:
                raw_transfers = data["transfers"] if isinstance(data, Mapping) else None
                if not isinstance(raw_transfers, list):
                    raise TypeError
                transfers.extend(self._bind(OwnershipTransfer.model_validate(item)) for item in raw_transfers)
            except (KeyError, TypeError, ValidationError):
                raise InvalidResponseError("ownership_transfers.get returned an invalid transfer list.") from None
        return sorted(transfers, key=lambda item: item.updated_at, reverse=True)

    def accept(self, target: _TransferTarget | Sequence[_TransferTarget], *, resource_type: OwnershipResourceType | str | None = None) -> OwnershipTransferActionResult | OwnershipTransferBatchResult:
        return self._act("accept", target, resource_type)

    def refuse(self, target: _TransferTarget | Sequence[_TransferTarget], *, resource_type: OwnershipResourceType | str | None = None) -> OwnershipTransferActionResult | OwnershipTransferBatchResult:
        return self._act("refuse", target, resource_type)

    def cancel(self, target: _TransferTarget | Sequence[_TransferTarget], *, resource_type: OwnershipResourceType | str | None = None) -> OwnershipTransferActionResult | OwnershipTransferBatchResult:
        return self._act("cancel", target, resource_type)

    def _act(self, name: str, target: object, resource_type: OwnershipResourceType | str | None) -> OwnershipTransferActionResult | OwnershipTransferBatchResult:
        if isinstance(target, Sequence) and not isinstance(target, (str, bytes, Mapping)):
            targets = list(target)
            keys = [self._target_key(item) for item in targets]
            if len(set(keys)) != len(keys):
                raise ValueError("Bulk ownership-transfer targets must be unique.")
            succeeded: list[OwnershipTransferActionResult] = []
            failed: list[OwnershipTransferFailure] = []
            for item in targets:
                try:
                    succeeded.append(self._act_one(name, item, resource_type))
                except Exception as error:
                    failed.append(OwnershipTransferFailure(item, error))
            return OwnershipTransferBatchResult(tuple(succeeded), tuple(failed))
        return self._act_one(name, target, resource_type)

    def _act_one(self, name: str, target: object, resource_type: OwnershipResourceType | str | None) -> OwnershipTransferActionResult:
        transfer_id, target_type = self._transfer_ref(target)
        selected_type = None if resource_type is None else self._resource_type(resource_type)
        if selected_type is not None and target_type is not None and selected_type != target_type:
            raise ValueError("resource_type conflicts with the transfer target.")
        selected_type = selected_type or target_type
        if selected_type is None:
            transfer = self._get_one(transfer_id, None, None)
            selected_type = transfer.resource_type
        query = httpx.QueryParams({"resource_type": selected_type})
        body = {"action": name} if name in {"accept", "refuse"} else None
        data = self._send_write(name, transfer_id=transfer_id, query=query, body=body)
        result = self._parse_write(name, OwnershipTransferActionResult, data)
        if result.result is not None and result.resource_type == OwnershipResourceType.GROUP.value:
            raw_group = result.result.get("data")
            if isinstance(raw_group, Mapping):
                from ..identity._group_models import Group

                try:
                    group = Group.model_validate(raw_group)
                except ValidationError:
                    pass
                else:
                    self.bind_resource(group)
                    object.__setattr__(result, "resource", group)
        return result

    def _get_one(self, transfer_id: str, resource_type: str | None, extra_query: Mapping[str, object] | None) -> OwnershipTransfer:
        types = _BUILT_INS if resource_type is None else (resource_type,)
        for selected_type in types:
            query = httpx.QueryParams({"resource_type": selected_type}).merge(
                self._extra_query(extra_query)
            )
            try:
                data = self._pipeline.send(
                    _OPERATIONS["get"], path_parameters={"transfer_id": transfer_id}, query=query,
                )
            except HttpResponseError as error:
                if error.status_code == 404:
                    continue
                raise
            try:
                return self._bind(OwnershipTransfer.model_validate(data))
            except ValidationError:
                raise InvalidResponseError("ownership_transfers.get returned an invalid transfer.") from None
        raise OwnershipTransferNotFoundError("ownership_transfers.get", 404)

    def bind_resource(self, resource: object) -> object:
        if hasattr(resource, "_endpoint"):
            resource._endpoint = self._pipeline.endpoint
        if hasattr(resource, "_ownership_transfers"):
            resource._ownership_transfers = self.for_resource(resource)
        return resource

    def _bind(self, transfer: OwnershipTransfer) -> OwnershipTransfer:
        transfer._operations = self
        return transfer

    def _send_write(
        self, name: str, *, transfer_id: str | None = None,
        query: httpx.QueryParams | None = None, body: dict[str, object] | None = None,
    ) -> object:
        operation = _OPERATIONS[name]
        try:
            return self._pipeline.send(
                operation,
                path_parameters={"transfer_id": transfer_id} if transfer_id is not None else None,
                query=query,
                json_body=body,
            )
        except PoolTimeoutError:
            raise
        except HttpResponseError as error:
            if error.status_code == 404:
                raise OwnershipTransferNotFoundError(error.operation, error.status_code) from None
            if error.status_code == 400 and name != "create":
                raise OwnershipTransferNotPendingError(error.operation, error.status_code) from None
            if error.status_code in (400, 422):
                raise OwnershipTransferRequestError(error.operation, error.status_code) from None
            if 200 <= error.status_code < 300 or error.status_code >= 500:
                raise OwnershipTransferOutcomeUnknownError(error.operation, error.status_code) from None
            raise
        except (TransportError, InvalidResponseError):
            raise OwnershipTransferOutcomeUnknownError(operation.info.name) from None

    @staticmethod
    def _parse_write(name: str, model: type[_Model], data: object) -> _Model:
        try:
            return model.model_validate(data)
        except ValidationError:
            raise OwnershipTransferOutcomeUnknownError(
                _OPERATIONS[name].info.name, _OPERATIONS[name].success_status
            ) from None

    def _resource_ref(self, resource: object) -> tuple[str, str]:
        from ..identity._group_models import Group

        if isinstance(resource, Group):
            if resource._endpoint is not None:
                _require_endpoint(resource._endpoint, self._pipeline.endpoint)
            return OwnershipResourceType.GROUP.value, self._value(resource.group_id, "resource ID")
        if isinstance(resource, OwnershipResourceRef):
            return self._resource_type(resource.resource_type), self._value(resource.resource_id, "resource ID")
        if isinstance(resource, Mapping):
            type_id = resource.get("resource_type"), resource.get("resource_id")
            has_ref = any(value is not None for value in type_id)
            typed = [(OwnershipResourceType.GROUP.value, resource.get("group_id")), (OwnershipResourceType.PROJECT.value, resource.get("upload_id"))]
            typed = [(kind, value) for kind, value in typed if value is not None]
            if has_ref and typed or len(typed) > 1:
                raise ValueError("Resource mapping contains conflicting identifiers.")
            if has_ref:
                if None in type_id:
                    raise ValueError("Resource mapping requires resource_type and resource_id.")
                return self._resource_type(type_id[0]), self._value(type_id[1], "resource ID")
            if typed:
                return typed[0][0], self._value(typed[0][1], "resource ID")
        resource_type = getattr(resource, "ownership_resource_type", None)
        resource_id = getattr(resource, "ownership_resource_id", None)
        if resource_type is not None or resource_id is not None:
            if resource_type is None or resource_id is None:
                raise ValueError("Transferable resources require a type and ID.")
            return self._resource_type(resource_type), self._value(resource_id, "resource ID")
        raise ValueError("Supply a transferable SDK object or REST-shaped resource mapping.")

    def _target_ref(self, target: object) -> tuple[str, str]:
        from ..identity._account import Account
        from ..identity._user import User

        if isinstance(target, (User, Account)):
            if target._endpoint is not None:
                _require_endpoint(target._endpoint, self._pipeline.endpoint)
            return self._value(target.user_id, "target user"), "user_id"
        if isinstance(target, Mapping):
            if target.get("user_id") is not None:
                return self._value(target["user_id"], "target user"), "user_id"
            selectors = [(name, target.get(name)) for name in ("username", "email") if target.get(name) is not None]
            if len(selectors) == 1:
                name, value = selectors[0]
                return self._value(value, "target user"), name
            raise ValueError("Target mapping requires one user_id, username, or email selector.")
        raise ValueError("Supply a User, Account, or REST-shaped target mapping.")

    def _create_request(self, request: object) -> OwnershipTransferCreateRequest:
        if isinstance(request, OwnershipTransferCreateRequest):
            return request
        if not isinstance(request, Mapping):
            raise ValueError("Supply a complete transfer request mapping or typed request.")
        try:
            return OwnershipTransferCreateRequest.model_validate(dict(request))
        except ValidationError:
            raise ValueError("Invalid ownership-transfer request fields.") from None

    def _transfer_ref(self, target: object) -> tuple[str, str | None]:
        if isinstance(target, OwnershipTransfer):
            return self._value(target.transfer_id, "transfer ID"), self._resource_type(target.resource_type)
        if isinstance(target, Mapping):
            transfer_id = target.get("transfer_id")
            if transfer_id is None:
                raise ValueError("Transfer mapping requires transfer_id.")
            resource_type = target.get("resource_type")
            return self._value(transfer_id, "transfer ID"), (
                None if resource_type is None else self._resource_type(resource_type)
            )
        return self._value(target, "transfer ID"), None

    def _target_key(self, target: object) -> tuple[str, str]:
        transfer_id, resource_type = self._transfer_ref(target)
        return resource_type or "", transfer_id

    def _list_query(
        self, direction: OwnershipTransferDirection | str, resource_type: str,
        resource_id: str | None, state: str | None, extra_query: Mapping[str, object] | None,
    ) -> httpx.QueryParams:
        direction_value = direction.value if isinstance(direction, OwnershipTransferDirection) else direction
        if direction_value not in {item.value for item in OwnershipTransferDirection}:
            raise ValueError("direction must be incoming, outgoing, or all.")
        values: dict[str, str] = {"direction": direction_value, "resource_type": resource_type}
        if resource_id is not None:
            values["resource_id"] = self._value(resource_id, "resource ID")
        if state is not None:
            values["state"] = self._value(state, "transfer state")
        return httpx.QueryParams(values).merge(self._extra_query(extra_query))

    @staticmethod
    def _resource_type(value: object) -> str:
        if isinstance(value, OwnershipResourceType):
            return value.value
        return OwnershipTransferOperations._value(value, "resource type")

    @staticmethod
    def _value(value: object, label: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 512 or not _SAFE_VALUE.fullmatch(value):
            raise ValueError(f"Supply a valid {label} string.")
        return value

    @staticmethod
    def _extra_json(values: Mapping[str, object] | None) -> dict[str, object]:
        if values is None:
            return {}
        if not isinstance(values, Mapping) or any(
            not isinstance(key, str) or not key or key.lower() in _RESERVED_BODY for key in values
        ):
            raise ValueError("extra_json must contain only custom fields.")
        try:
            return json.loads(json.dumps(dict(values), allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            raise ValueError("extra_json must contain JSON-compatible values.") from None

    @staticmethod
    def _extra_query(values: Mapping[str, object] | None) -> httpx.QueryParams:
        if values is None:
            return httpx.QueryParams()
        if not isinstance(values, Mapping) or any(
            not isinstance(key, str) or not key or key.lower() in _RESERVED_QUERY for key in values
        ):
            raise ValueError("extra_query must contain only custom fields.")
        try:
            return httpx.QueryParams(values)
        except (TypeError, ValueError):
            raise ValueError("extra_query must contain serializable query values.") from None
