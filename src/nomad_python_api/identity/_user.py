from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class User(BaseModel):
    """A NOMAD profile. Availability of optional fields depends on the operation."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    user_id: StrictStr = Field(min_length=1, repr=False)
    username: StrictStr | None = Field(default=None, repr=False)
    name: StrictStr | None = Field(default=None, repr=False)
    first_name: StrictStr | None = Field(default=None, repr=False)
    last_name: StrictStr | None = Field(default=None, repr=False)
    email: StrictStr | None = Field(default=None, repr=False)
    affiliation: StrictStr | None = Field(default=None, repr=False)
    affiliation_address: StrictStr | None = Field(default=None, repr=False)
    created: datetime | None = None
    repo_user_id: StrictStr | None = Field(default=None, repr=False)
    is_admin: StrictBool | None = None
    is_oasis_admin: StrictBool | None = None
