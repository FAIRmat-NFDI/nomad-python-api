import json
from collections.abc import Mapping
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .._core._operation import Operation, OperationInfo
from .._core._pipeline import RequestPipeline
from .._scopes import Scope
from ..exceptions import (
    AuthorizationError,
    ClientAuthenticationError,
    HttpResponseError,
    InvalidResponseError,
    PatNotFoundError,
    PatRequestError,
    PatWriteOutcomeUnknownError,
    PoolTimeoutError,
    TransportError,
)
from ._credential import BearerTokenCredential, _require_endpoint, _validate_pat_id
from ._pat_models import PatCreateOptions, PatIssuedResult, PatMetadata
from ._pat_paging import PatList, PatPage


_BASE = "/auth/pats"
_TARGET = _BASE + "/{pat_id}"
_OPERATIONS = {
    "create": Operation(OperationInfo(
        "identity.pats.create", "Issue a new PAT.", frozenset({Scope.TOKENS_CREATE}),
    ), "POST", _BASE, 201),
    "list": Operation(OperationInfo(
        "identity.pats.list", "List the caller's PATs.", frozenset({Scope.TOKENS_READ}),
    ), "GET", _BASE),
    "get": Operation(OperationInfo(
        "identity.pats.get", "Read PAT metadata.", frozenset({Scope.TOKENS_READ}),
    ), "GET", _TARGET),
    "rotate": Operation(OperationInfo(
        "identity.pats.rotate", "Replace an active PAT.", frozenset({Scope.TOKENS_CREATE, Scope.TOKENS_DELETE}),
    ), "POST", _TARGET + "/rotate"),
    "revoke": Operation(OperationInfo(
        "identity.pats.revoke", "Revoke a PAT.", frozenset({Scope.TOKENS_DELETE}),
    ), "DELETE", _TARGET, 204),
}
_MANAGEMENT_GUIDANCE = (
    "Use a valid Keycloak access token from this deployment with the required PAT management scopes."
)
_CREATE_FIELDS = PatCreateOptions.model_fields.keys() | {
    "metadata", "extra_json", "authorization", "access_token", "token", "raw_token",
}
_REQUEST_GUIDANCE = {
    "create": "Check the token options, requested scopes, and the deployment's expiry policy.",
    "list": "Check the filters and pagination options.",
    "get": "Check the PAT metadata ID.",
    "rotate": "Check the PAT metadata ID and confirm the token is active.",
    "revoke": "Check the PAT metadata ID.",
}
_PatTarget = str | PatMetadata | BearerTokenCredential
_Model = TypeVar("_Model", bound=BaseModel)


class PatOperations:
    """Manage the personal access tokens of the calling NOMAD account."""

    def __init__(self, pipeline: RequestPipeline) -> None:
        self._pipeline = pipeline

    def get_operation_info(self, name: str) -> OperationInfo:
        """Read operation metadata locally."""
        return _OPERATIONS["revoke" if name == "delete" else name].info

    def create(
        self,
        options: PatCreateOptions | Mapping[str, object],
        *,
        extra_json: Mapping[str, object] | None = None,
    ) -> PatIssuedResult:
        """Issue a PAT from typed options or a JSON-style mapping."""
        if not isinstance(options, PatCreateOptions):
            if not isinstance(options, Mapping):
                raise ValueError("Supply PAT creation options as an object or mapping.")
            try:
                options = PatCreateOptions.model_validate(dict(options))
            except ValidationError:
                raise ValueError("Invalid PAT creation options. Check name, scopes, and expiry.") from None
        metadata = options.model_dump(mode="json", exclude_unset=True, exclude={"expires_in_days"})
        body: dict[str, object] = {"metadata": metadata}
        if "expires_in_days" in options.model_fields_set:
            body["expires_in_days"] = options.expires_in_days
        if extra_json is not None:
            if not isinstance(extra_json, Mapping) or any(
                not isinstance(key, str) or not key or key.lower() in _CREATE_FIELDS for key in extra_json
            ):
                raise ValueError("extra_json must contain only custom JSON fields.")
            try:
                body.update(json.loads(json.dumps(dict(extra_json), allow_nan=False)))
            except (TypeError, ValueError, RecursionError):
                raise ValueError("extra_json must contain JSON-compatible values.") from None
        return self._issued("create", json_body=body)

    def list(
        self,
        *,
        limit: int | None = None,
        extra_query: Mapping[str, object] | None = None,
        **filters: object,
    ) -> PatList:
        """Return a reusable lazy listing of PAT metadata."""
        if self._pipeline.is_closed:
            raise RuntimeError("The NOMAD client is closed.")
        return PatList(self._page, filters, limit=limit, extra_query=extra_query)

    def get(self, target: _PatTarget) -> PatMetadata:
        """Read metadata for a PAT."""
        data = self._send("get", pat_id=self._target_id(target))
        metadata = self._parse("get", PatMetadata, data)
        metadata._endpoint = self._pipeline.endpoint
        return metadata

    def rotate(self, target: _PatTarget) -> PatIssuedResult:
        """Replace an active PAT and return the new one-time secret."""
        return self._issued("rotate", pat_id=self._target_id(target))

    def revoke(self, target: _PatTarget) -> None:
        """Revoke a PAT."""
        self._send("revoke", pat_id=self._target_id(target))

    delete = revoke

    def _target_id(self, target: _PatTarget) -> str:
        if isinstance(target, (BearerTokenCredential, PatMetadata)):
            if target._endpoint is not None:
                _require_endpoint(target._endpoint, self._pipeline.endpoint)
            target = target.pat_id if isinstance(target, BearerTokenCredential) else target.id
        return _validate_pat_id(target)

    def _page(self, query: httpx.QueryParams) -> PatPage:
        page = self._parse("list", PatPage, self._send("list", query=query))
        for pat in page.items:
            pat._endpoint = self._pipeline.endpoint
        return page

    def _issued(
        self, name: str, *, pat_id: str | None = None, json_body: dict[str, object] | None = None
    ) -> PatIssuedResult:
        data = self._send(name, pat_id=pat_id, json_body=json_body)
        result = self._parse(name, PatIssuedResult, data)
        result.pat._endpoint = self._pipeline.endpoint
        return result

    @staticmethod
    def _parse(name: str, model: type[_Model], data: object) -> _Model:
        operation = _OPERATIONS[name]
        try:
            return model.model_validate(data)
        except ValidationError:
            pass
        if operation.method != "GET":
            raise PatWriteOutcomeUnknownError(operation.info.name, operation.success_status)
        raise InvalidResponseError(f"{operation.info.name} returned invalid PAT metadata.")

    def _send(
        self,
        name: str,
        *,
        pat_id: str | None = None,
        query: httpx.QueryParams | None = None,
        json_body: dict[str, object] | None = None,
    ) -> object:
        operation = _OPERATIONS[name]
        write = operation.method != "GET"
        try:
            return self._pipeline.send(
                operation,
                path_parameters={"pat_id": pat_id} if pat_id is not None else None,
                query=query,
                json_body=json_body,
            )
        except (ClientAuthenticationError, AuthorizationError) as error:
            raise type(error)(error.operation, error.status_code, guidance=_MANAGEMENT_GUIDANCE) from None
        except HttpResponseError as error:
            if error.status_code in (400, 422):
                raise PatRequestError(error.operation, error.status_code, guidance=_REQUEST_GUIDANCE[name]) from None
            if error.status_code == 404 and pat_id is not None:
                raise PatNotFoundError(error.operation, error.status_code) from None
            if write and (200 <= error.status_code < 300 or error.status_code >= 500):
                raise PatWriteOutcomeUnknownError(error.operation, error.status_code) from None
            raise
        except PoolTimeoutError:
            raise
        except (TransportError, InvalidResponseError):
            if write:
                raise PatWriteOutcomeUnknownError(operation.info.name) from None
            raise
