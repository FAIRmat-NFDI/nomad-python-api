from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from weakref import ref

from ._user import User

if TYPE_CHECKING:
    from ._pat_paging import PatList
    from ._pats import PatOperations


@dataclass(frozen=True)
class Account:
    """Identity of the user authenticated by NOMAD."""

    user_id: str = field(repr=False)
    username: str | None = field(default=None, repr=False)
    name: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    first_name: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    last_name: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    email: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    affiliation: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    affiliation_address: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    created: datetime | None = field(default=None, kw_only=True, repr=False, compare=False)
    repo_user_id: str | None = field(default=None, kw_only=True, repr=False, compare=False)
    is_admin: bool | None = field(default=None, kw_only=True, repr=False, compare=False)
    is_oasis_admin: bool | None = field(default=None, kw_only=True, repr=False, compare=False)

    @classmethod
    def _from_user(cls, user: User, pats: PatOperations) -> Account:
        account = cls(**user.model_dump())
        object.__setattr__(account, "_pats_ref", ref(pats))
        return account

    def as_user(self) -> User:
        """Return the same profile as a local, serializable User model."""
        return User.model_validate(asdict(self))

    def get_all_pats(self, **options: object) -> PatList:
        """List this client's PATs using the originating client's credentials."""
        reference = getattr(self, "_pats_ref", None)
        pats = reference() if reference is not None else None
        if pats is None:
            raise RuntimeError("This account is detached. Call identity.me() on an open client.")
        return pats.list(**options)

    def __getstate__(self) -> dict[str, object]:
        return asdict(self)
