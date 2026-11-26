import json
import pickle
from dataclasses import asdict
from datetime import datetime

import httpx
import pytest

from nomad_python_api import NomadClient, Scope
from nomad_python_api.exceptions import (
    AuthorizationError,
    ClientAuthenticationError,
    CredentialEndpointMismatchError,
    InvalidResponseError,
    PatNotFoundError,
    PatRequestError,
    PatWriteOutcomeUnknownError,
    PoolTimeoutError,
    RateLimitError,
    ScopeNotAllowedError,
)
from nomad_python_api.identity import Account, BearerTokenCredential, PatCreateOptions


_OPTIONS = {"name": "analysis", "scopes": [Scope.USERS_READ, "uploads:read", "users:read"]}
_METADATA = {
    "id": "p-1",
    "name": "analysis",
    "scopes": ["users:read"],
    "created_at": "2026-11-26T08:00:00Z",
    "last_used_at": None,
    "description": "A test PAT",
    "revoked": False,
}
_ISSUED = {"pat": _METADATA, "raw_token": "fixture-only-secret"}


@pytest.fixture
def make_client():
    from contextlib import ExitStack

    with ExitStack() as stack:
        def make(handler, *, credential=None, scopes=None, **http_options):
            http = stack.enter_context(httpx.Client(transport=httpx.MockTransport(handler), **http_options))
            return stack.enter_context(NomadClient(
                credential=credential or BearerTokenCredential("management-fixture"),
                allowed_scopes=scopes,
                http_client=http,
            ))

        yield make


def test_issue_and_manage_the_same_credential(make_client):
    requests = []

    def server(request):
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "GET":
            return httpx.Response(200, json=_METADATA)
        if request.url.path.endswith("/rotate"):
            return httpx.Response(200, json={
                "pat": dict(_METADATA, id="p-2"), "raw_token": "replacement-fixture",
            })
        return httpx.Response(201, json=_ISSUED)

    client = make_client(server, params={"borrowed": "ignored"})
    pats = client.identity.pats
    issued = pats.create(PatCreateOptions(**_OPTIONS), extra_json={"site_label": "x"})
    assert json.loads(requests[0].content) == {
        "metadata": {"name": "analysis", "scopes": ["users:read", "uploads:read"]}, "site_label": "x",
    }
    assert not requests[0].url.query
    assert "raw_token" not in issued.model_dump()
    assert "fixture-only-secret" not in issued.model_dump_json()
    assert "fixture-only-secret" not in repr(issued)
    with pytest.raises(TypeError, match="cannot be pickled"):
        pickle.dumps(issued)

    credential = BearerTokenCredential.from_issued(issued)
    assert credential.pat_id == "p-1"

    def job_server(request):
        assert request.headers["Authorization"] == "Bearer fixture-only-secret"
        return httpx.Response(200, json={"user_id": "researcher"})

    assert make_client(job_server, credential=credential).identity.me().user_id == "researcher"
    assert pats.get(credential).description == "A test PAT"
    replacement = pats.rotate(credential)
    assert credential.pat_id == "p-1" and replacement.pat.id == "p-2"
    assert pats.delete(replacement.pat) is None
    assert [request.url.path.rsplit("/auth/pats", 1)[1] for request in requests] == [
        "", "/p-1", "/p-1/rotate", "/p-2",
    ]
    assert all(request.headers["Authorization"] == "Bearer management-fixture" for request in requests)
    assert all(not request.content for request in requests[1:])


def test_creation_distinguishes_null_optional_fields_and_rejects_collisions(make_client):
    requests = []

    def server(request):
        requests.append(json.loads(request.content))
        return httpx.Response(201, json=_ISSUED)

    pats = make_client(server).identity.pats
    pats.create(dict(_OPTIONS, expires_in_days=None, description=None))
    assert requests[0]["expires_in_days"] is None
    assert requests[0]["metadata"]["description"] is None
    for extension in ({"expires_in_days": 5}, {"Metadata": {}}, {"raw_token": "private"}):
        with pytest.raises(ValueError, match="custom JSON fields"):
            pats.create(_OPTIONS, extra_json=extension)
    for scopes in ([], ["*:read"], [Scope.TOKENS_CREATE], ["bad scope"], [42]):
        with pytest.raises(ValueError, match="Invalid PAT creation"):
            pats.create(dict(_OPTIONS, scopes=scopes))
    assert len(requests) == 1


def test_account_profile_is_local_and_pat_listing_is_lazy(make_client):
    requests = []
    profile = {
        "user_id": "user-id", "username": "example", "name": "A Researcher",
        "first_name": "A", "last_name": "Researcher", "email": "private@example.org",
        "affiliation": "Research group", "affiliation_address": "Example address",
        "created": "2024-10-01T12:00:00Z", "repo_user_id": "legacy-id",
        "is_admin": False, "is_oasis_admin": True,
    }

    def server(request):
        requests.append(request)
        if request.url.path.endswith("/users/me"):
            return httpx.Response(200, json=profile)
        query = request.url.params
        data = [dict(_METADATA, id="p-2")] if "page_after_value" in query else [_METADATA]
        return httpx.Response(200, json={
            "query": {"search": query.get("search")},
            "pagination": {
                "total": 2, "next_page_after_value": None if "page_after_value" in query else "next&opaque",
                "next_page_url": "https://unrelated.example.org/",
            },
            "data": data,
        })

    client = make_client(server)
    account = client.identity.me()
    assert account == Account("user-id", "example")
    assert account.email == "private@example.org" and account.is_oasis_admin
    assert isinstance(account.created, datetime)
    assert account.as_user().model_dump(mode="json") == profile
    assert "private@" not in repr(account)
    assert "_pats_ref" not in asdict(account)
    detached = pickle.loads(pickle.dumps(account))
    with pytest.raises(RuntimeError, match="detached"):
        detached.get_all_pats()

    listing = account.get_all_pats(page=1, extra_query={"tag": ["one", "two"]})
    query = listing.filter(search="name & other").filter(state="active")
    assert len(requests) == 1
    assert [pat.id for pat in query] == ["p-1", "p-2"]
    assert requests[1].url.params.get_list("tag") == ["one", "two"]
    assert requests[1].url.params["search"] == "name & other"
    assert requests[1].url.params["page"] == "1"
    assert "page" not in requests[2].url.params
    assert requests[2].url.params["page_after_value"] == "next&opaque"
    assert requests[2].url.host == requests[1].url.host
    assert next(listing.by_page()).query.search is None
    count = len(requests)
    assert list(client.identity.pats.list(limit=0)) == []
    assert len(requests) == count
    assert [page.items[0].id for page in client.identity.pats.list().by_page("next&opaque")] == ["p-2"]
    client.close()
    with pytest.raises(RuntimeError, match="closed"):
        account.get_all_pats()


@pytest.mark.parametrize(("status", "failure"), [
    (400, PatRequestError), (401, ClientAuthenticationError), (403, AuthorizationError),
    (404, PatNotFoundError), (422, PatRequestError), (429, RateLimitError),
    (500, PatWriteOutcomeUnknownError),
])
def test_pat_http_errors_are_typed_and_redacted(make_client, status, failure):
    def server(request):
        return httpx.Response(status, json={"detail": "raw-private-data"})

    with pytest.raises(failure) as caught:
        make_client(server).identity.pats.rotate("p-1")
    assert caught.value.status_code == status
    assert "raw-private-data" not in str(caught.value)


def test_pat_cannot_create_pat_and_local_policy_is_separate(make_client):
    calls = []

    def server(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer ordinary-pat-fixture"
        return httpx.Response(403)

    credential = BearerTokenCredential("ordinary-pat-fixture", pat_id="p-1")
    pats = make_client(server, credential=credential).identity.pats
    with pytest.raises(AuthorizationError, match="Keycloak access token"):
        pats.create(_OPTIONS)
    local = make_client(server, credential=credential, scopes=[Scope.TOKENS_CREATE])
    with pytest.raises(ScopeNotAllowedError) as error:
        local.identity.pats.rotate("p-1")
    assert error.value.missing_scopes == {Scope.TOKENS_DELETE}
    assert len(calls) == 1


def test_rotation_does_not_replay_an_uncertain_write(make_client):
    calls = []

    def server(request):
        calls.append(request)
        raise httpx.ReadTimeout("private detail", request=request)

    with pytest.raises(PatWriteOutcomeUnknownError, match="Check your PATs"):
        make_client(server).identity.pats.rotate("p-1")
    assert len(calls) == 1


def test_confirmed_unsent_pat_write_preserves_pool_error(nomad_http):
    def respond(request):
        raise httpx.PoolTimeout("mock pool exhaustion", request=request)

    nomad_http.respond = respond
    with NomadClient(credential=BearerTokenCredential("management-fixture")) as client:
        with pytest.raises(PoolTimeoutError):
            client.identity.pats.revoke("p-1")
    assert len(nomad_http.requests) == 1


def test_repeated_cursor_terminates_listing(make_client):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "data": [], "query": {}, "pagination": {"total": 20, "next_page_after_value": "repeated"},
        })

    pats = make_client(respond).identity.pats
    with pytest.raises(InvalidResponseError, match="repeated continuation"):
        list(pats.list())
    assert len(requests) == 2


def test_invalid_success_is_unknown_for_writes_and_typed_for_reads(make_client):
    def server(request):
        return httpx.Response(201 if request.method == "POST" else 200, json={"raw_token": "hidden"})

    pats = make_client(server).identity.pats
    with pytest.raises(PatWriteOutcomeUnknownError) as caught:
        pats.create(_OPTIONS)
    assert caught.value.status_code == 201
    assert caught.value.__context__ is None
    with pytest.raises(InvalidResponseError):
        pats.get("p-1")


def test_invalid_targets_and_listing_options_fail_before_http(make_client):
    def server(request):
        pytest.fail("Invalid request reached the transport.")

    pats = make_client(server).identity.pats
    for target in (BearerTokenCredential("fixture"), "..", "a/b", "nomad_pat_placeholder"):
        with pytest.raises(ValueError, match="PAT metadata ID"):
            pats.get(target)
    with pytest.raises(CredentialEndpointMismatchError):
        pats.revoke(BearerTokenCredential("fixture", pat_id="p-1", endpoint="https://oasis.example/api/v1"))
    with pytest.raises(ValueError, match="custom query fields"):
        pats.list(extra_query={"state": "active"})
    with pytest.raises(ValueError, match="different value"):
        pats.list(state="active").filter(state="inactive")
    with pytest.raises(ValueError, match="pagination position"):
        pats.list(page=2, page_offset=5)
