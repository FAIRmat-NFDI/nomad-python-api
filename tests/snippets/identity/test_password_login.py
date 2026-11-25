from urllib.parse import parse_qs

import httpx
import pytest

pytestmark = pytest.mark.snippet
_USER = "example-user"
_PASSWORD = "offline-example-password"


@pytest.fixture
def password_login(nomad_http, monkeypatch):
    monkeypatch.setenv("NOMAD_USERNAME", _USER)
    monkeypatch.setenv("NOMAD_PASSWORD", _PASSWORD)

    def respond(request):
        if request.method == "POST":
            assert parse_qs(request.content.decode()) == {
                "grant_type": ["password"], "username": [_USER], "password": [_PASSWORD],
            }
            return httpx.Response(200, json={
                "access_token": "example-access-token", "token_type": "Bearer", "expires_in": 300,
            })
        assert request.headers["Authorization"] == "Bearer example-access-token"
        return httpx.Response(200, json={"user_id": "example-id"})

    nomad_http.respond = respond
    return nomad_http.requests


def test_central_password_login(password_login):
    # --8<-- [start:central_password_login]
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import PasswordCredential

    credential = PasswordCredential()  # Reads NOMAD_USERNAME and NOMAD_PASSWORD.
    with NomadClient(credential=credential) as client:
        account = client.identity.me()
    # --8<-- [end:central_password_login]

    assert account.user_id == "example-id"
    assert [str(request.url) for request in password_login] == [
        "https://nomad-lab.eu/prod/v1/api/v1/auth/token",
        "https://nomad-lab.eu/prod/v1/api/v1/users/me",
    ]


def test_oasis_password_login(password_login):
    # --8<-- [start:oasis_password_login]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import PasswordCredential

    credential = PasswordCredential(
        endpoint="https://oasis.example.edu/nomad-oasis/api/v1",
        username=os.environ["NOMAD_USERNAME"],
        password=os.environ["NOMAD_PASSWORD"],
    )
    credential.authenticate()
    with NomadClient(credential=credential) as client:
        account = client.identity.me()
    # --8<-- [end:oasis_password_login]

    assert account.user_id == "example-id"
    assert [str(request.url) for request in password_login] == [
        "https://oasis.example.edu/nomad-oasis/api/v1/auth/token",
        "https://oasis.example.edu/nomad-oasis/api/v1/users/me",
    ]
