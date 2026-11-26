from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, StrictStr, field_validator

from .._scopes import Scope

_MANAGEMENT_SCOPES = {Scope.TOKENS_CREATE, Scope.TOKENS_READ, Scope.TOKENS_DELETE}


class PatCreateOptions(BaseModel):
    """Options for a new personal access token."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    name: StrictStr = Field(min_length=1)
    scopes: tuple[StrictStr, ...]
    description: StrictStr | None = None
    expires_in_days: int | None = Field(default=30, ge=0, strict=True)

    @field_validator("scopes")
    @classmethod
    def _check_scopes(cls, scopes: tuple[str, ...]) -> tuple[str, ...]:
        if not scopes or any(
            not scope or "*" in scope or any(char.isspace() for char in scope)
            or scope in _MANAGEMENT_SCOPES for scope in scopes
        ):
            raise ValueError("Use explicit, nonempty PAT scopes without management permissions.")
        return tuple(dict.fromkeys(scopes))


class PatMetadata(BaseModel):
    """Personal access token metadata returned by NOMAD."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    _endpoint: str | None = PrivateAttr(default=None)

    id: StrictStr = Field(min_length=1)
    name: StrictStr
    scopes: tuple[StrictStr, ...]
    revoked: bool = Field(strict=True)
    created_at: datetime
    description: StrictStr | None = None
    expired_at: datetime | None = None
    last_used_at: datetime | None = None


class PatIssuedResult(BaseModel):
    """New PAT metadata and its one-time secret."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    pat: PatMetadata
    raw_token: SecretStr = Field(min_length=1, repr=False, exclude=True)

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("PAT issuance results contain a one-time secret and cannot be pickled.")
