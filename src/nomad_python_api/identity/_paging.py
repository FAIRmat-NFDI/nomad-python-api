from collections.abc import Callable, Iterator
from typing import Literal, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..exceptions import InvalidResponseError

POSITIONS = ("page_after_value", "page", "page_offset")


class Pagination(BaseModel):
    """Pagination metadata common to NOMAD directory lists."""

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


class _CursorPage(Protocol):
    @property
    def next_cursor(self) -> str | None: ...


_Page = TypeVar("_Page", bound=_CursorPage)


def iter_pages(
    fetch: Callable[[httpx.QueryParams], _Page], params: dict[str, object],
    extra: httpx.QueryParams, *, operation: str,
) -> Iterator[_Page]:
    params = dict(params)
    seen = {params.get("page_after_value")}
    while True:
        page = fetch(httpx.QueryParams(params).merge(extra))
        cursor = page.next_cursor
        if cursor and cursor in seen:
            raise InvalidResponseError(f"{operation} received a repeated continuation token.")
        yield page
        if not cursor or params.get("page_size") == 0:
            return
        seen.add(cursor)
        params.pop("page", None)
        params.pop("page_offset", None)
        params["page_after_value"] = cursor


def with_cursor(
    params: dict[str, object], cursor: str | None, *, resource: str
) -> dict[str, object]:
    if cursor is None:
        return params
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("Supply a nonempty continuation token.")
    if any(key in params for key in POSITIONS):
        raise ValueError(f"Choose a continuation token or a {resource} pagination position.")
    return params | {"page_after_value": cursor}
