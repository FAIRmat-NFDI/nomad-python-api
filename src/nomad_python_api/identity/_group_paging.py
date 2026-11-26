from collections.abc import Callable, Iterator, Mapping
from itertools import islice
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from ._directory_support import directory_id, query_extension
from ._group_models import Group, GroupPage
from ._paging import POSITIONS, iter_pages, with_cursor


class _GroupFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    group_id: StrictStr | list[StrictStr] | None = None
    user_id: StrictStr | None = None
    search_terms: StrictStr | None = None


class _GroupListOptions(_GroupFilters):
    page_size: int | None = Field(default=None, ge=0, strict=True)
    order_by: StrictStr | None = None
    order: Literal["asc", "desc"] | None = None
    page_after_value: StrictStr | None = Field(default=None, min_length=1)
    page: int | None = Field(default=None, ge=1, strict=True)
    page_offset: int | None = Field(default=None, ge=0, strict=True)


class GroupList:
    """Reusable lazy iterable of groups, with optional explicit page access."""

    def __init__(
        self, fetch: Callable[[httpx.QueryParams], GroupPage], options: Mapping[str, object],
        *, limit: int | None = None, extra_query: Mapping[str, object] | None = None,
    ) -> None:
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError("limit must be a nonnegative integer.")
        try:
            params = _GroupListOptions.model_validate(dict(options)).model_dump(exclude_none=True)
        except ValidationError:
            raise ValueError("Invalid group listing options.") from None
        if sum(key in params for key in POSITIONS) > 1:
            raise ValueError("Choose one group pagination position.")
        ids = params.get("group_id")
        if ids is not None:
            if isinstance(ids, list):
                params["group_id"] = [directory_id(value) for value in ids]
            else:
                params["group_id"] = directory_id(ids)
        if "user_id" in params:
            directory_id(params["user_id"])
        self._fetch = fetch
        self._params = params
        self._limit = limit
        self._extra = query_extension(extra_query, set(_GroupListOptions.model_fields) | {"limit"})

    def filter(self, **filters: object) -> "GroupList":
        """Add documented group filters without making a request."""
        try:
            updates = _GroupFilters.model_validate(filters).model_dump(exclude_unset=True)
        except ValidationError:
            raise ValueError("Invalid group filters.") from None
        if any(key in self._params and self._params[key] != value for key, value in updates.items()):
            raise ValueError("A group filter already has a different value.")
        return GroupList(self._fetch, self._params | updates, limit=self._limit, extra_query=self._extra)

    def __iter__(self) -> Iterator[Group]:
        pages = iter_pages(self._fetch, self._params, self._extra, operation="identity.groups.list")
        items = (item for page in pages for item in page.items)
        return items if self._limit is None else islice(items, self._limit)

    def by_page(self, continuation_token: str | None = None) -> Iterator[GroupPage]:
        """Yield group pages, optionally resuming from an opaque server cursor."""
        if self._limit is not None:
            raise ValueError("Use limit for item iteration or by_page for whole pages.")
        params = with_cursor(self._params, continuation_token, resource="group")
        return iter_pages(self._fetch, params, self._extra, operation="identity.groups.list")
