from base64 import urlsafe_b64encode
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from nomad_python_api import NomadClient, Scope
from nomad_python_api.exceptions import (
    BrowserAuthenticationError,
    ClientAuthenticationError,
    CredentialEndpointMismatchError,
    ReauthenticationRequiredError,
    ScopeNotAllowedError,
)
from nomad_python_api.identity import BearerTokenCredential, BrowserCredential, _token

ISSUER = "https://identity.example/realms/materials"
AUTHORIZE = ISSUER + "/protocol/openid-connect/auth"
TOKEN = ISSUER + "/protocol/openid-connect/token"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
CENTRAL = "https://nomad-lab.eu/prod/v1/api/v1"
OASIS = "https://oasis.example/nomad-oasis/api/v1"


def explicit(**options):
    return BrowserCredential(
        issuer=ISSUER, client_id="materials-sdk",
        authorization_endpoint=AUTHORIZE, token_endpoint=TOKEN, **options,
    )


def token_response(access="access-example", refresh="refresh-example"):
    document = {"access_token": access, "expires_in": 120, "token_type": "Bearer"}
    if refresh is not None:
        document["refresh_token"] = refresh
    return httpx.Response(200, json=document)


def authorization_url(url):
    parts = urlsplit(url)
    return parts._replace(query="").geturl(), parse_qs(parts.query)


def test_explicit_browser_flow_and_default_endpoint(nomad_http, browser_sign_in):
    def respond(request):
        if str(request.url) == TOKEN:
            return token_response()
        return httpx.Response(200, json={"user_id": "demo"})

    nomad_http.respond = respond
    credential = explicit()
    with NomadClient(credential=credential) as client:
        assert not nomad_http.requests
        assert not browser_sign_in
        assert client.identity.me().user_id == "demo"
        client.identity.me()
    assert len(browser_sign_in) == 1
    auth_url, auth = authorization_url(browser_sign_in[0])
    assert auth_url == AUTHORIZE
    assert set(auth) == {
        "client_id", "response_type", "response_mode", "scope", "redirect_uri", "state",
        "code_challenge", "code_challenge_method",
    }
    assert auth["response_type"] == ["code"]
    assert auth["response_mode"] == ["query"]
    assert auth["scope"] == ["openid"]
    assert auth["code_challenge_method"] == ["S256"]
    assert len(auth["state"][0]) >= 32
    exchange, *api_calls = nomad_http.requests
    form = parse_qs(exchange.content.decode())
    assert form.keys() == {"grant_type", "client_id", "code", "redirect_uri", "code_verifier"}
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["example-code"]
    assert form["client_id"] == auth["client_id"] == ["materials-sdk"]
    assert form["redirect_uri"] == auth["redirect_uri"] == ["http://127.0.0.1:54321/"]
    challenge = urlsafe_b64encode(sha256(form["code_verifier"][0].encode()).digest()).decode().rstrip("=")
    assert auth["code_challenge"] == [challenge]
    assert exchange.method == "POST"
    assert exchange.headers["content-type"] == "application/x-www-form-urlencoded"
    assert len(api_calls) == 2
    for call in api_calls:
        assert str(call.url) == CENTRAL + "/users/me"
        assert call.headers["Authorization"] == "Bearer access-example"
    assert all(http.is_closed for http in nomad_http.clients)


def test_bearer_default_endpoint(nomad_http):
    with NomadClient(credential=BearerTokenCredential("example-bearer")) as client:
        client.identity.me()
    assert str(nomad_http.requests[0].url) == CENTRAL + "/users/me"


def test_discovered_oasis_endpoints_and_provider(nomad_http, browser_sign_in):
    def respond(request):
        if str(request.url) == DISCOVERY:
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": AUTHORIZE, "token_endpoint": TOKEN,
                "code_challenge_methods_supported": ["S256"],
            })
        if str(request.url) == TOKEN:
            return token_response()
        return httpx.Response(200, json={"user_id": "oasis-user"})

    nomad_http.respond = respond
    credential = BrowserCredential(
        endpoint=OASIS, issuer=ISSUER, client_id="oasis-cli", discover=True,
        identity_provider="institute-enterprise", redirect_port=9123, redirect_path="/return",
    )
    credential.authenticate()
    credential.authenticate()
    with NomadClient(credential=credential) as client:
        assert client.identity.me().user_id == "oasis-user"
    assert [str(item.url) for item in nomad_http.requests] == [
        DISCOVERY, TOKEN, TOKEN, OASIS + "/users/me",
    ]
    assert all("Authorization" not in item.headers for item in nomad_http.requests[:3])
    first, second = [authorization_url(url)[1] for url in browser_sign_in]
    assert first["state"] != second["state"]
    assert first["code_challenge"] != second["code_challenge"]
    assert second["client_id"] == ["oasis-cli"]
    assert second["kc_idp_hint"] == ["institute-enterprise"]
    assert second["redirect_uri"] == ["http://127.0.0.1:9123/return"]


@pytest.mark.parametrize("options", [
    {}, {"authorization_endpoint": AUTHORIZE},
    {"authorization_endpoint": AUTHORIZE, "token_endpoint": TOKEN, "discover": True},
    {"authorization_endpoint": AUTHORIZE, "token_endpoint": "https://other.example/token"},
    {"authorization_endpoint": AUTHORIZE, "token_endpoint": TOKEN + "?"},
    {"discover": True, "redirect_path": "//example/"},
    {"discover": True, "login_timeout": 0}, {"discover": True, "redirect_port": -1},
])
def test_invalid_identity_configuration(options, nomad_http, browser_sign_in):
    with pytest.raises(ValueError):
        BrowserCredential(issuer=ISSUER, client_id="public-client", **options)
    assert not nomad_http.requests
    assert not browser_sign_in


@pytest.mark.parametrize("override", [
    {"issuer": ISSUER + "/other"}, {"token_endpoint": "https://other.example/token"},
    {"code_challenge_methods_supported": ["plain"]},
])
def test_invalid_discovery_stops_sign_in(override, nomad_http, browser_sign_in):
    def respond(request):
        if str(request.url) != DISCOVERY:
            pytest.fail("Only discovery should be requested")
        return httpx.Response(200, json={
            "issuer": ISSUER, "authorization_endpoint": AUTHORIZE, "token_endpoint": TOKEN, **override,
        })

    nomad_http.respond = respond
    credential = BrowserCredential(issuer=ISSUER, client_id="public-client", discover=True)
    with pytest.raises(BrowserAuthenticationError):
        credential.authenticate()
    assert not browser_sign_in


def test_scope_mismatch_and_closed_client_block_browser(nomad_http, browser_sign_in):
    with pytest.raises(CredentialEndpointMismatchError):
        explicit(endpoint=OASIS)._get_token(endpoint=CENTRAL, scopes=frozenset())
    with NomadClient(credential=explicit(), enforced_scopes=set()) as client:
        with pytest.raises(ScopeNotAllowedError):
            client.identity.me()
    with pytest.raises(RuntimeError, match="closed"):
        client.identity.me()
    assert not browser_sign_in
    assert not nomad_http.requests


def test_refresh_rotation_and_expiry(nomad_http, browser_sign_in, monkeypatch):
    now = 100.0
    monkeypatch.setattr(_token, "monotonic", lambda: now)
    responses = iter([token_response(), token_response("access-rotated", "refresh-rotated"),
                      token_response("access-next", None), httpx.Response(400, json={"error": "invalid_grant"})])
    nomad_http.respond = lambda request: next(responses)
    credential = explicit()

    def token():
        return credential._get_token(endpoint=CENTRAL, scopes=frozenset({Scope.USERS_READ}))

    assert token() == "access-example"
    now += 89
    assert token() == "access-example"
    now += 1
    assert token() == "access-rotated"
    now += 90
    assert token() == "access-next"
    now += 90
    with pytest.raises(ReauthenticationRequiredError, match="authenticate"):
        token()
    with pytest.raises(ReauthenticationRequiredError):
        token()
    refreshes = [parse_qs(item.content.decode()) for item in nomad_http.requests[1:]]
    assert [form["refresh_token"][0] for form in refreshes] == [
        "refresh-example", "refresh-rotated", "refresh-rotated",
    ]
    assert all(form.keys() == {"client_id", "grant_type", "refresh_token"} for form in refreshes)
    assert len(browser_sign_in) == 1


def test_missing_refresh_token_requires_explicit_sign_in(nomad_http, browser_sign_in, monkeypatch):
    now = 100.0
    monkeypatch.setattr(_token, "monotonic", lambda: now)
    nomad_http.respond = lambda request: token_response(refresh=None)
    credential = explicit()
    credential.authenticate()
    now += 100
    assert credential._get_token(endpoint=CENTRAL, scopes=frozenset()) == "access-example"
    now += 20
    with pytest.raises(ReauthenticationRequiredError):
        credential._get_token(endpoint=CENTRAL, scopes=frozenset())
    credential.authenticate()
    assert credential._get_token(endpoint=CENTRAL, scopes=frozenset()) == "access-example"
    assert len(browser_sign_in) == 2


def test_concurrent_requests_share_login_and_refresh(nomad_http, browser_sign_in, monkeypatch):
    now = 100.0
    monkeypatch.setattr(_token, "monotonic", lambda: now)
    responses = iter([token_response(), token_response("access-next")])
    nomad_http.respond = lambda request: next(responses)
    credential = explicit()

    def concurrently():
        ready = Barrier(4, timeout=5)

        def call(_):
            ready.wait()
            return credential._get_token(endpoint=CENTRAL, scopes=frozenset())

        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(call, range(4)))

    assert concurrently() == ["access-example"] * 4
    now += 90
    assert concurrently() == ["access-next"] * 4
    assert len(browser_sign_in) == 1
    assert len(nomad_http.requests) == 2


def test_refresh_transport_error_is_redacted_and_later_calls_can_recover(
    nomad_http, browser_sign_in, monkeypatch,
):
    now = 100.0
    monkeypatch.setattr(_token, "monotonic", lambda: now)

    def respond(request):
        if len(nomad_http.requests) == 2:
            raise httpx.ReadTimeout("private failure details", request=request)
        return token_response()

    nomad_http.respond = respond
    credential = explicit()
    credential.authenticate()
    now += 90
    with pytest.raises(BrowserAuthenticationError, match="Could not reach") as caught:
        credential._get_token(endpoint=CENTRAL, scopes=frozenset())
    assert caught.value.__context__ is None
    with pytest.raises(BrowserAuthenticationError, match="refresh failed"):
        credential._get_token(endpoint=CENTRAL, scopes=frozenset())
    now += 1
    assert credential._get_token(endpoint=CENTRAL, scopes=frozenset()) == "access-example"
    assert len(nomad_http.requests) == 3
    assert len(browser_sign_in) == 1


def test_api_401_does_not_repeat_browser_or_request(nomad_http, browser_sign_in):
    nomad_http.respond = lambda request: (token_response() if str(request.url) == TOKEN
                                          else httpx.Response(401))
    with NomadClient(credential=explicit()) as client:
        with pytest.raises(ClientAuthenticationError):
            client.identity.me()
    assert len(browser_sign_in) == 1
    assert [str(item.url) for item in nomad_http.requests] == [TOKEN, CENTRAL + "/users/me"]
