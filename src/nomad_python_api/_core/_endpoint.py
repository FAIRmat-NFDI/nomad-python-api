"""Validate and normalize deployment API base URLs."""

from urllib.parse import urlsplit

import httpx

_PRODUCTION = "https://nomad-lab.eu/prod/v1/api/v1"


def normalize_endpoint(endpoint: str) -> str:
    """Normalize a deployment's complete HTTPS API base URL."""
    if endpoint == "prod":
        return _PRODUCTION
    message = "Use 'prod' or a complete HTTPS NOMAD API base URL."
    if any(character.isspace() or not character.isprintable() for character in endpoint):
        raise ValueError(message)
    if any(character in endpoint for character in ("?", "#", "\\")):
        raise ValueError(message)
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
        url = httpx.URL(endpoint)
    except (ValueError, httpx.InvalidURL):
        raise ValueError(message) from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and port < 1)
        or not parsed.path.rstrip("/").endswith("/api/v1")
        or ".." in parsed.path.split("/")
        or "." in parsed.path.split("/")
        or "%" in parsed.path
    ):
        raise ValueError(message)
    return str(url).rstrip("/")
