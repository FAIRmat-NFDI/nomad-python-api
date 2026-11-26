from enum import Enum


class Scope(str, Enum):
    """NOMAD permission names used by this SDK."""

    USERS_READ = "users:read"
    USERS_INVITE = "users:invite"
    GROUPS_READ = "groups:read"
    GROUPS_WRITE = "groups:write"
    GROUPS_DELETE = "groups:delete"
    UPLOADS_READ = "uploads:read"
    TOKENS_CREATE = "tokens:create"
    TOKENS_READ = "tokens:read"
    TOKENS_DELETE = "tokens:delete"
