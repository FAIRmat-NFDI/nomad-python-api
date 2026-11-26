from collections.abc import Callable, Iterator, Mapping
from datetime import datetime
from itertools import islice
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..exceptions import InvalidResponseError
from ._pat_models import PatMetadata


class PatFilters(BaseModel):
    """Filters echoed by NOMAD for a page of PAT metadata."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    search: str | None = None
    revoked: bool | None = Field(default=None, strict=True)
    state: Literal["active", "inactive"] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    last_used_after: datetime | None = None
    last_used_before: datetime | None = None
    expires_after: datetime | None = None
    expires_before: datetime | None = None


class PatPagination(BaseModel):
    """Pagination metadata returned by NOMAD."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    total: int = Field(ge=0, strict=True)
    page_size: int | None = None
    order_by: str | None = None
    order: Literal["asc", "desc"] | None = None
    page_after_value: str | None = None
    page: int | None = None
    page_offset: int | None = None
    next_page_after_value: str | None = None
    page_url: str | None = Field(default=None, repr=False)
    next_page_url: str | None = Field(default=None, repr=False)
    prev_page_url: str | None = Field(default=None, repr=False)
    first_page_url: str | None = Field(default=None, repr=False)


class PatPage(BaseModel):
    """A page of PAT metadata and the associated filters and pagination."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    items: tuple[PatMetadata, ...] = Field(validation_alias="data")
    query: PatFilters
    pagination: PatPagination

    @property
    def next_cursor(self) -> str | None:
        return self.pagination.next_page_after_value


class _PatListOptions(PatFilters):
    model_config = ConfigDict(extra="forbid")

    page_size: int | None = Field(default=None, ge=0, strict=True)
    order_by: Literal[
        "created_asc", "created_desc", "expires_asc", "expires_desc",
        "last_used_asc", "last_used_desc", "name_asc", "name_desc",
    ] | None = None
    order: Literal["asc", "desc"] | None = None
    page_after_value: str | None = Field(default=None, min_length=1)
    page: int | None = Field(default=None, ge=1, strict=True)
    page_offset: int | None = Field(default=None, ge=0, strict=True)


_POSITIONS = ("page_after_value", "page", "page_offset")
_RESERVED_QUERY_FIELDS = _PatListOptions.model_fields.keys() | {
    "limit", "extra_query", "authorization", "access_token", "token", "raw_token",
}


class PatList:
    """Reusable lazy iterable of PATs. A new iteration starts a new listing."""

    def __init__(
        self,
        fetch: Callable[[httpx.QueryParams], PatPage],
        options: Mapping[str, object],
        *,
        limit: int | None = None,
        extra_query: Mapping[str, object] | None = None,
    ) -> None:
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError("limit must be a nonnegative integer.")
        try:
            validated = _PatListOptions.model_validate(dict(options))
        except ValidationError:
            raise ValueError("Invalid PAT listing options.") from None
        params = validated.model_dump(mode="json", exclude_none=True)
        if sum(name in params for name in _POSITIONS) > 1:
            raise ValueError("Choose one PAT pagination position.")
        if extra_query is not None:
            if not isinstance(extra_query, Mapping) or any(
                not isinstance(name, str) or not name or name.lower() in _RESERVED_QUERY_FIELDS
                for name in extra_query
            ):
                raise ValueError("extra_query must contain only custom query fields.")
        self._fetch = fetch
        self._params = params
        self._limit = limit
        try:
            self._extra = httpx.QueryParams(extra_query)
        except (TypeError, ValueError):
            raise ValueError("extra_query must contain serializable query values.") from None

    def filter(self, **filters: object) -> "PatList":
        """Return another lazy listing with additional server-side filters."""
        if filters.keys() - PatFilters.model_fields.keys():
            raise ValueError("Use documented PAT filter names.")
        try:
            updates = PatFilters.model_validate(filters).model_dump(mode="json", exclude_unset=True)
        except ValidationError:
            raise ValueError("Invalid PAT filters.") from None
        if any(key in self._params and self._params[key] != value for key, value in updates.items()):
            raise ValueError("A PAT filter already has a different value.")
        return PatList(
            self._fetch, self._params | updates, limit=self._limit, extra_query=self._extra,
        )

    def __iter__(self) -> Iterator[PatMetadata]:
        items = (item for page in self._pages(self._params) for item in page.items)
        return items if self._limit is None else islice(items, self._limit)

    def by_page(self, continuation_token: str | None = None) -> Iterator[PatPage]:
        """Yield whole pages, optionally resuming from a previous page's cursor."""
        if self._limit is not None:
            raise ValueError("Use limit for item iteration or by_page for whole pages.")
        params = dict(self._params)
        if continuation_token is not None:
            if not isinstance(continuation_token, str) or not continuation_token:
                raise ValueError("Supply a nonempty continuation token.")
            if any(key in params for key in _POSITIONS):
                raise ValueError("Choose a continuation token or a PAT pagination position.")
            params["page_after_value"] = continuation_token
        return self._pages(params)

    def _pages(self, params: dict[str, object]) -> Iterator[PatPage]:
        params = dict(params)
        seen = {params.get("page_after_value")}
        while True:
            page = self._fetch(httpx.QueryParams(params).merge(self._extra))
            cursor = page.next_cursor
            if cursor and cursor in seen:
                raise InvalidResponseError("identity.pats.list received a repeated continuation token.")
            yield page
            if not cursor or params.get("page_size") == 0:
                return
            seen.add(cursor)
            params.pop("page", None)
            params.pop("page_offset", None)
            params["page_after_value"] = cursor
