from enum import Enum


class Scope(str, Enum):
    """NOMAD permission names used by this SDK."""

    USERS_READ = "users:read"
    UPLOADS_READ = "uploads:read"
    TOKENS_CREATE = "tokens:create"
    TOKENS_READ = "tokens:read"
    TOKENS_DELETE = "tokens:delete"
