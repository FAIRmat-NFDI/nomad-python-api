from enum import Enum


class Scope(str, Enum):
    """NOMAD permission names used by this SDK."""

    USERS_READ = "users:read"
