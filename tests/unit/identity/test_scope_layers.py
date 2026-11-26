from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from nomad_python_api import NomadClient, Scope
from nomad_python_api.exceptions import ScopeNotAllowedError, ScopeNotGrantedError
from nomad_python_api.identity import BearerTokenCredential, BrowserCredential, PasswordCredential
from nomad_python_api.identity._pat_models import PatIssuedResult

ISSUER = "https://identity.example/realms/materials"
TOKEN = ISSUER + "/protocol/openid-connect/token"
TOKEN_RESPONSE = {"access_token": "access-example", "token_type": "Bearer", "expires_in": 120}


def issued_pat(scopes):
    issued = PatIssuedResult.model_validate({
        "pat": {
            "id": "507f1f77bcf86cd799439011", "name": "job", "scopes": scopes,
            "created_at": "2026-11-26T08:00:00Z", "revoked": False,
        },
        "raw_token": "fixture-pat",
    })
    issued.pat._endpoint = "https://nomad-lab.eu/prod/v1/api/v1"
    return issued


def browser(**options):
    return BrowserCredential(
        issuer=ISSUER, client_id="materials-sdk",
        authorization_endpoint=ISSUER + "/protocol/openid-connect/auth", token_endpoint=TOKEN,
        **options,
    )


def password_form(nomad_http, **options):
    def respond(request):
        if request.method == "POST":
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(200, json={"user_id": "account"})

    nomad_http.respond = respond
    credential = PasswordCredential(username="user", password="secret", **options)
    with NomadClient(credential=credential) as client:
        client.identity.me()
    return credential, parse_qs(nomad_http.requests[0].content.decode())


def test_password_requested_scopes_are_sent_sorted_and_deduplicated(nomad_http):
    credential, form = password_form(
        nomad_http, requested_scopes=[Scope.USERS_READ, "uploads:read", "users:read"],
    )
    assert credential.requested_scopes == ("uploads:read", "users:read")
    assert credential.granted_scopes is None
    assert form["scope"] == ["uploads:read users:read"]


def test_password_without_requested_scopes_omits_the_field(nomad_http):
    credential, form = password_form(nomad_http)
    assert credential.requested_scopes is None
    assert "scope" not in form


@pytest.mark.parametrize(
    "value",
    [[], [""], ["users read"], ["a\tb"], ['say"hi'], [r"a\b"], ["café"], "users:read", [None]],
)
def test_invalid_requested_scopes_are_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        PasswordCredential(username="user", password="secret", requested_scopes=value)
    with pytest.raises((ValueError, TypeError)):
        browser(requested_scopes=value)


def test_requested_scope_boundaries_are_accepted():
    names = [f"scope-{index:02d}" for index in range(64)]
    credential = browser(requested_scopes=names)
    assert credential.requested_scopes == tuple(names)

    longest = "a" * 256
    assert browser(requested_scopes=[longest]).requested_scopes == (longest,)

    exact_joined_limit = [f"{'a' * 255}{index}" for index in range(7)] + ["b" * 249]
    assert len(" ".join(browser(requested_scopes=exact_joined_limit).requested_scopes or ())) == 2048


@pytest.mark.parametrize(
    "value",
    [
        [f"scope-{index:02d}" for index in range(65)],
        ["a" * 257],
        [f"{'a' * 255}{index}" for index in range(7)] + ["b" * 250],
    ],
)
def test_requested_scope_limits_are_rejected(value):
    with pytest.raises(ValueError):
        PasswordCredential(username="user", password="secret", requested_scopes=value)
    with pytest.raises(ValueError):
        browser(requested_scopes=value)


@pytest.mark.parametrize("requested, expected", [
    (None, "openid"),
    (["offline_access", "nomad-api", "openid"], "openid nomad-api offline_access"),
])
def test_browser_scope_always_starts_with_openid(nomad_http, browser_sign_in, requested, expected):
    def respond(request):
        if str(request.url) == TOKEN:
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(200, json={"user_id": "demo"})

    nomad_http.respond = respond
    credential = browser(requested_scopes=requested)
    assert credential.granted_scopes is None
    with NomadClient(credential=credential) as client:
        client.identity.me()
    assert parse_qs(urlsplit(browser_sign_in[0]).query)["scope"] == [expected]


def test_known_pat_grants_block_locally_before_http(nomad_http):
    credential = BearerTokenCredential.from_issued(issued_pat(["users:read"]))
    assert credential.granted_scopes == frozenset({"users:read"})
    nomad_http.respond = lambda request: httpx.Response(200, json={"user_id": "job"})
    with NomadClient(credential=credential) as client:
        assert client.identity.me().user_id == "job"
        with pytest.raises(ScopeNotGrantedError) as caught:
            client.identity.groups.delete("group-id")
    assert not isinstance(caught.value, ScopeNotAllowedError)
    assert caught.value.missing_scopes == frozenset({Scope.GROUPS_DELETE})
    assert "not granted: groups:delete" in str(caught.value)
    assert [request.url.path.rsplit("/", 1)[1] for request in nomad_http.requests] == ["me"]


def test_enforced_policy_is_checked_before_known_grants(nomad_http):
    credential = BearerTokenCredential.from_issued(issued_pat(["users:read"]))
    with NomadClient(credential=credential, enforced_scopes=set()) as client:
        with pytest.raises(ScopeNotAllowedError) as caught:
            client.identity.groups.delete("group-id")
    assert type(caught.value) is ScopeNotAllowedError
    assert not nomad_http.requests


def test_raw_bearer_tokens_leave_grants_to_nomad(nomad_http):
    credential = BearerTokenCredential("raw-token")
    assert credential.granted_scopes is None
    nomad_http.respond = lambda request: httpx.Response(204)
    with NomadClient(credential=credential) as client:
        client.identity.groups.delete("group-id")
    assert len(nomad_http.requests) == 1
