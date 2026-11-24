from dataclasses import dataclass, field


@dataclass(frozen=True)
class Account:
    """Identity of the user authenticated by NOMAD."""

    user_id: str = field(repr=False)
    username: str | None = field(default=None, repr=False)
