"""Read-only checks against a real NOMAD deployment."""

import os

import httpx
import pytest

from nomad_python_api import NomadClient, Scope
from nomad_python_api._core._endpoint import normalize_endpoint
from nomad_python_api.identity import BearerTokenCredential

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def endpoint() -> str:
    configured_url = os.environ.get("NOMAD_TEST_API_URL", "").strip()
    if not configured_url:
        pytest.fail("NOMAD_TEST_API_URL is missing or empty.", pytrace=False)
    if configured_url.startswith("https://"):
        try:
            return normalize_endpoint(configured_url)
        except ValueError:
            pass
    pytest.fail(
        "NOMAD_TEST_API_URL must be a plain HTTPS API base URL ending in /api/v1.",
        pytrace=False,
    )


def test_account_accepts_a_real_pat(endpoint: str) -> None:
    token = os.environ.get("NOMAD_TEST_PAT")
    if not token:
        pytest.fail("Set NOMAD_TEST_PAT to a PAT with users:read for this deployment.", pytrace=False)

    credential = BearerTokenCredential(token, endpoint=endpoint)
    with NomadClient(
        credential=credential,
        enforced_scopes={Scope.USERS_READ},
    ) as client:
        account = client.identity.me()

    if not account.user_id:
        pytest.fail("NOMAD returned an account without a user ID.", pytrace=False)


def test_account_requires_authentication(endpoint: str) -> None:
    with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False) as http:
        with http.stream("GET", f"{endpoint}/users/me") as response:
            assert response.status_code == 401
