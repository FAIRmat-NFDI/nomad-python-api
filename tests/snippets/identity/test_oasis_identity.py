"""CI-tested examples for the Oasis identity setups guide."""

import ssl
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

import nomad_python_api  # noqa: F401  Import before fixtures patch httpx.Client.

pytestmark = pytest.mark.snippet
_OASIS = "https://oasis.example.edu/nomad-oasis/api/v1"
_TOKEN = {
    "access_token": "example-access-token", "token_type": "Bearer", "expires_in": 300,
    "refresh_token": "example-refresh-token",
}


@pytest.fixture
def identity(nomad_http):
    """Serve OIDC discovery, token exchange, and the account route for any issuer."""

    def respond(request):
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            issuer = url.removesuffix("/.well-known/openid-configuration")
            return httpx.Response(200, json={
                "issuer": issuer,
                "authorization_endpoint": issuer + "/authorize",
                "token_endpoint": issuer + "/token",
                "code_challenge_methods_supported": ["S256"],
            })
        if request.method == "POST":
            return httpx.Response(200, json=_TOKEN)
        assert request.headers["Authorization"] == "Bearer example-access-token"
        return httpx.Response(200, json={"user_id": "example-id", "username": "demo"})

    nomad_http.respond = respond
    return nomad_http


def _authorize(browser_sign_in):
    parts = urlsplit(browser_sign_in[0])
    return parts._replace(query="").geturl(), parse_qs(parts.query)


def test_oasis_with_central_realm(identity, browser_sign_in):
    # --8<-- [start:oasis_central_realm]
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BrowserCredential

    # The Oasis API is yours; sign-in uses NOMAD Central's Keycloak realm.
    credential = BrowserCredential(
        endpoint="https://oasis.example.edu/nomad-oasis/api/v1",
        issuer="https://nomad-lab.eu/fairdi/keycloak/auth/realms/fairdi_nomad_prod",
        client_id="nomad_public",
        discover=True,
    )
    with NomadClient(credential=credential) as client:
        print("Signed in as:", client.identity.me().username)
    # --8<-- [end:oasis_central_realm]

    assert str(identity.requests[-1].url) == _OASIS + "/users/me"
    assert _authorize(browser_sign_in)[1]["scope"] == ["openid"]


def test_oasis_own_keycloak(identity, browser_sign_in):
    # --8<-- [start:oasis_own_keycloak]
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BrowserCredential

    # Your Oasis runs its own Keycloak; discovery finds its endpoints.
    credential = BrowserCredential(
        endpoint="https://oasis.example.edu/nomad-oasis/api/v1",
        issuer="https://keycloak.example.edu/realms/materials",
        client_id="materials-python",
        discover=True,
    )
    with NomadClient(credential=credential) as client:
        print("Signed in as:", client.identity.me().username)
    # --8<-- [end:oasis_own_keycloak]

    assert str(identity.requests[0].url) == (
        "https://keycloak.example.edu/realms/materials/.well-known/openid-configuration"
    )
    assert _authorize(browser_sign_in)[0] == "https://keycloak.example.edu/realms/materials/authorize"


def test_oasis_keycloak_explicit(identity, browser_sign_in, monkeypatch):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    create_context = Mock(return_value=context)
    monkeypatch.setattr(ssl, "create_default_context", create_context)

    # --8<-- [start:oasis_keycloak_explicit]
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BrowserCredential

    # Older Keycloak releases serve realms under /auth.
    issuer = "https://login.example.edu/auth/realms/materials"
    credential = BrowserCredential(
        endpoint="https://oasis.example.edu/nomad-oasis/api/v1",
        issuer=issuer,
        client_id="materials-python",
        # Explicit endpoints skip discovery, e.g. when a proxy reports another issuer.
        authorization_endpoint=f"{issuer}/protocol/openid-connect/auth",
        token_endpoint=f"{issuer}/protocol/openid-connect/token",
        # Trust the identity service's private CA.
        ca_bundle="oasis-ca.pem",
        # Match the exact redirect URI registered in Keycloak.
        redirect_port=8765,
        redirect_path="/nomad-callback",
    )
    with NomadClient(credential=credential, ca_bundle="oasis-ca.pem") as client:
        print("Signed in as:", client.identity.me().username)
    # --8<-- [end:oasis_keycloak_explicit]

    assert not any("openid-configuration" in str(request.url) for request in identity.requests)
    url, query = _authorize(browser_sign_in)
    assert url == "https://login.example.edu/auth/realms/materials/protocol/openid-connect/auth"
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/nomad-callback"]
    create_context.assert_called_with(cafile="oasis-ca.pem")


def test_oasis_sso_brokered(identity, browser_sign_in):
    # --8<-- [start:oasis_sso_brokered]
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BrowserCredential

    # Keycloak brokers your institution's SSO; the alias skips Keycloak's chooser.
    credential = BrowserCredential(
        endpoint="https://oasis.example.edu/nomad-oasis/api/v1",
        issuer="https://keycloak.example.edu/realms/materials",
        client_id="materials-python",
        discover=True,
        identity_provider="institution-sso",  # The IdP alias configured in Keycloak
    )
    with NomadClient(credential=credential) as client:
        print("Signed in as:", client.identity.me().username)
    # --8<-- [end:oasis_sso_brokered]

    assert _authorize(browser_sign_in)[1]["kc_idp_hint"] == ["institution-sso"]


def test_oasis_direct_sso(identity, browser_sign_in):
    # --8<-- [start:oasis_direct_sso]
    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BrowserCredential

    # Requires an Oasis backend customised to accept this provider's tokens.
    credential = BrowserCredential(
        endpoint="https://oasis.example.edu/nomad-oasis/api/v1",
        issuer="https://sso.example.edu",  # The provider's exact issuer URL
        client_id="nomad-oasis-python",
        discover=True,
        # Ask for an access token for the Oasis API plus a refresh token.
        requested_scopes={"nomad-api", "offline_access"},
    )
    with NomadClient(credential=credential, enforced_scopes={Scope.USERS_READ}) as client:
        print("Signed in as:", client.identity.me().username)
    # --8<-- [end:oasis_direct_sso]

    url, query = _authorize(browser_sign_in)
    assert url == "https://sso.example.edu/authorize"
    assert query["scope"] == ["openid nomad-api offline_access"]
    assert "kc_idp_hint" not in query
