import json
import logging
import re
from collections.abc import Mapping
from contextvars import ContextVar
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .._core._operation import Operation
from .._core._pipeline import RequestPipeline
from ..exceptions import (
    HttpResponseError,
    IdentityWriteOutcomeUnknownError,
    InvalidResponseError,
    PoolTimeoutError,
    TransportError,
)

_ID = re.compile(r"[A-Za-z0-9_-]+")
_RESERVED = {"authorization", "access_token", "token", "raw_token", "extra_json", "extra_query"}
_Model = TypeVar("_Model", bound=BaseModel)
_LOOKUP_URL: ContextVar[tuple[httpx.URL, str] | None] = ContextVar("nomad_directory_url", default=None)


class _DirectoryQueryLogFilter(logging.Filter):
    """Remove directory selectors from HTTPX's own request summary."""

    def filter(self, record: logging.LogRecord) -> bool:
        lookup = _LOOKUP_URL.get()
        args = record.args
        if lookup is not None and isinstance(args, tuple) and len(args) >= 2:
            endpoint, display = lookup
            url = args[1]
            if isinstance(url, httpx.URL) and url.copy_with(query=None) == endpoint:
                record.args = (args[0], display, *args[2:])
        return True


_LOOKUP_LOG_FILTER = _DirectoryQueryLogFilter()


def send_directory_lookup(
    pipeline: RequestPipeline, operation: Operation, query: httpx.QueryParams | None = None,
    *, user_id: str | None = None,
) -> object:
    logging.getLogger("httpx").addFilter(_LOOKUP_LOG_FILTER)
    display = pipeline.endpoint + operation.path
    path = {"user_id": user_id} if user_id is not None else None
    endpoint = httpx.URL(display.format(**path) if path is not None else display)
    reset = _LOOKUP_URL.set((endpoint, display))
    try:
        return pipeline.send(operation, query=query, path_parameters=path)
    finally:
        _LOOKUP_URL.reset(reset)


def directory_id(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or value.startswith("nomad_pat_"):
        raise ValueError("Supply a valid NOMAD user or group ID.")
    return value


def extra_fields(
    values: Mapping[str, object] | None, reserved: set[str], *, option: str
) -> dict[str, object]:
    if values is None:
        return {}
    if not isinstance(values, Mapping) or any(
        not isinstance(key, str) or not key or key.lower() in reserved | _RESERVED
        for key in values
    ):
        raise ValueError(f"{option} must contain only custom fields.")
    return dict(values)


def json_extension(values: Mapping[str, object] | None, reserved: set[str]) -> dict[str, object]:
    fields = extra_fields(values, reserved, option="extra_json")
    try:
        return json.loads(json.dumps(fields, allow_nan=False))
    except (TypeError, ValueError, RecursionError):
        raise ValueError("extra_json must contain JSON-compatible values.") from None


def send_directory_write(
    pipeline: RequestPipeline,
    operation: Operation,
    model: type[_Model] | None,
    *,
    path: Mapping[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> _Model | None:
    try:
        data = pipeline.send(operation, path_parameters=path, json_body=body)
    except PoolTimeoutError:
        raise
    except (TransportError, InvalidResponseError):
        raise IdentityWriteOutcomeUnknownError(operation.info.name) from None
    except HttpResponseError as error:
        if 200 <= error.status_code < 300 or error.status_code >= 500:
            raise IdentityWriteOutcomeUnknownError(operation.info.name, error.status_code) from None
        raise
    if model is None:
        return None
    try:
        return model.model_validate(data)
    except ValidationError:
        pass
    raise IdentityWriteOutcomeUnknownError(operation.info.name, operation.success_status)


def query_extension(
    values: Mapping[str, object] | None, reserved: set[str],
) -> httpx.QueryParams:
    fields = extra_fields(values, reserved, option="extra_query")
    if isinstance(values, httpx.QueryParams):
        return values
    try:
        return httpx.QueryParams(fields)
    except (TypeError, ValueError):
        raise ValueError("extra_query must contain serializable query values.") from None
