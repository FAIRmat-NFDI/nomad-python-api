"""Validate and normalize deployment API base URLs."""

from urllib.parse import urlsplit

import httpx

_PRODUCTION = "https://nomad-lab.eu/prod/v1/api/v1"


def normalize_endpoint(endpoint: str) -> str:
    """Normalize a deployment's complete HTTPS API base URL."""
    if endpoint == "prod":
        return _PRODUCTION
    message = "Use 'prod' or a complete HTTPS NOMAD API base URL."
    if any(
        character in "?#\\" or character.isspace() or not character.isprintable()
        for character in endpoint
    ):
        raise ValueError(message)
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
        url = httpx.URL(endpoint)
    except (ValueError, httpx.InvalidURL):
        raise ValueError(message) from None
    path = parsed.path.rstrip("/")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or "@" in parsed.netloc
        or port == 0
        or not path.endswith("/api/v1")
        or {".", ".."}.intersection(path.split("/"))
        or "%" in path
    ):
        raise ValueError(message)
    return str(url).rstrip("/")
