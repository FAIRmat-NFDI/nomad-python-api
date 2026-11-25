from urllib.parse import parse_qs, urlsplit

import httpx
import pytest


def _configure_identity(nomad_http, issuer):
    authorization = issuer + "/protocol/openid-connect/auth"
    token = issuer + "/protocol/openid-connect/token"

    def respond(request):
        if str(request.url) == issuer + "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": issuer, "authorization_endpoint": authorization, "token_endpoint": token,
            })
        if str(request.url) == token:
            return httpx.Response(200, json={
                "access_token": "example-browser-token", "token_type": "Bearer", "expires_in": 300,
            })
        assert request.headers["Authorization"] == "Bearer example-browser-token"
        return httpx.Response(200, json={"user_id": "example-id"})

    nomad_http.respond = respond


@pytest.mark.snippet
def test_central_browser_login(nomad_http, browser_sign_in):
    issuer = "https://nomad-lab.eu/fairdi/keycloak/auth/realms/fairdi_nomad_prod"
    _configure_identity(nomad_http, issuer)

    # --8<-- [start:central_browser_login]
    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BrowserCredential

    credential = BrowserCredential(
        issuer="https://nomad-lab.eu/fairdi/keycloak/auth/realms/fairdi_nomad_prod",
        client_id="nomad_public",
        discover=True,
        identity_provider="helmholtz-aai",
    )

    with NomadClient(credential=credential, allowed_scopes={Scope.USERS_READ}) as client:
        account = client.identity.me()
    # --8<-- [end:central_browser_login]

    assert account.user_id == "example-id"
    assert parse_qs(urlsplit(browser_sign_in[0]).query)["kc_idp_hint"] == ["helmholtz-aai"]


@pytest.mark.snippet
def test_oasis_browser_login(nomad_http, browser_sign_in):
    _configure_identity(nomad_http, "https://login.example.edu/realms/materials")

    # --8<-- [start:oasis_browser_login]
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BrowserCredential

    endpoint = "https://oasis.example.edu/nomad-oasis/api/v1"
    issuer = "https://login.example.edu/realms/materials"
    credential = BrowserCredential(
        endpoint=endpoint,
        issuer=issuer,
        client_id="materials-python",
        authorization_endpoint=f"{issuer}/protocol/openid-connect/auth",
        token_endpoint=f"{issuer}/protocol/openid-connect/token",
        identity_provider="university-sso",
    )
    credential.authenticate()

    with NomadClient(credential=credential) as client:
        account = client.identity.me()
    # --8<-- [end:oasis_browser_login]

    assert account.user_id == "example-id"
    assert str(nomad_http.requests[-1].url) == endpoint + "/users/me"
    assert len(nomad_http.requests) == 2
    assert len(browser_sign_in) == 1
