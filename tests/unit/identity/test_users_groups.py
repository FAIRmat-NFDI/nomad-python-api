import json
import logging

import httpx
import pytest

from nomad_python_api import NomadClient, Scope
from nomad_python_api.exceptions import (
    AmbiguousUserError,
    CredentialEndpointMismatchError,
    GroupNotFoundError,
    HttpResponseError,
    IdentityWriteOutcomeUnknownError,
    InvalidResponseError,
    ScopeNotAllowedError,
    UserNotFoundError,
)
from nomad_python_api.identity import Account, BearerTokenCredential, Group, GroupMember, GroupRole, User

_GROUP = {
    "group_id": "diffraction-team",
    "group_name": "Diffraction team",
    "owner": "owner-id",
    "members": ["owner-id", "ana-id"],
    "members_info": [{"user_id": "owner-id", "role": "owner"}, {"user_id": "ana-id", "role": "member"}],
}


@pytest.fixture
def client(nomad_http):
    with NomadClient(credential=BearerTokenCredential("directory-fixture")) as client:
        yield client


def test_exact_lookups_and_prefix_candidates(client, nomad_http):
    def respond(request):
        params = request.url.params
        if request.url.path.endswith("/users/ana-id"):
            return httpx.Response(200, json={"user_id": "ana-id", "username": "ana"})
        if "prefix" in params:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": [{"user_id": "ana-id", "username": "ana"}]})

    nomad_http.respond = respond
    users = client.identity.users
    ana = users.get_by_id("ana-id")
    assert users.get(username="ana") == ana
    team = users.get_many([
        {"email": "ana+science@example.org"}, {"username": "ana"}, {"email": "ana+science@example.org"},
    ])
    assert team == [ana, ana, ana]
    assert team[0] is team[2]
    assert team[0].email is None
    assert users.search(prefix="no-match", extra_query={"realm": "oasis"}) == []
    requests = nomad_http.requests
    assert len(requests) == 5
    assert requests[2].url.params["email"] == "ana+science@example.org"
    assert requests[4].url.params["realm"] == "oasis"
    assert client.identity.get_operation_info("users.get_by_username").required_scopes == {Scope.USERS_READ}


@pytest.mark.parametrize("data, error", [
    ({"data": []}, UserNotFoundError),
    ({"data": [{"user_id": "u1"}, {"user_id": "u2"}]}, AmbiguousUserError),
    ({"data": [{"username": "redacted"}]}, InvalidResponseError),
])
def test_exact_lookup_errors_are_redacted(client, nomad_http, data, error):
    nomad_http.respond = lambda request: httpx.Response(200, json=data)
    with pytest.raises(error) as exc:
        client.identity.users.get_by_email("private@example.org")
    assert "private" not in str(exc.value)
    assert "redacted" not in str(exc.value)


def test_directory_validation_precedes_http(client, nomad_http):
    users = client.identity.users
    for selector in ({}, {"email": "a", "username": "b"}, {"user_id": "me"}, {"user_id": "jwt.payload.sig"}):
        with pytest.raises(ValueError):
            users.get(**selector)
    with pytest.raises(ValueError):
        users.get_many([{"email": "first@example.org"}, {"prefix": "wrong"}])
    with pytest.raises(ValueError):
        users.search(prefix="a", extra_query={"Email": "hidden"})
    with pytest.raises(ValueError):
        client.identity.groups.delete(None)
    assert not nomad_http.requests


def test_lookup_selectors_are_redacted_from_httpx_logs(client, nomad_http, caplog):
    def respond(request):
        profile = {"user_id": "ana-id"}
        data = profile if request.url.path.endswith("/ana-id") else {"data": [profile]}
        return httpx.Response(200, json=data)

    nomad_http.respond = respond
    with caplog.at_level(logging.INFO, logger="httpx"):
        assert client.identity.users.get_by_email("private@example.org").user_id == "ana-id"
        assert client.identity.users.get_by_id("ana-id").user_id == "ana-id"
    assert "GET https://" in caplog.text
    assert "/users/{user_id}" in caplog.text
    assert "private" not in caplog.text and "ana-id" not in caplog.text
    assert nomad_http.requests[0].url.params["email"] == "private@example.org"


def test_invite_maps_the_write_and_preserves_typed_errors(client, nomad_http):
    users = client.identity.users
    options = {"email": "recipient@example.org", "first_name": "Ana"}
    nomad_http.respond = lambda request: httpx.Response(200, json={
        "user_id": "invited-id", "email": "recipient@example.org",
    })
    assert users.invite(options, extra_json={"institute": "Lab"}).user_id == "invited-id"
    request, = nomad_http.requests
    assert request.method == "PUT" and request.url.path.endswith("/users/invite")
    assert json.loads(request.content) == dict(options, institute="Lab")
    with pytest.raises(ValueError):
        users.invite(options, extra_json={"is_admin": True})
    assert len(nomad_http.requests) == 1

    nomad_http.respond = lambda request: httpx.Response(400, json={"detail": "recipient@example.org"})
    with pytest.raises(HttpResponseError) as error:
        users.invite(options)
    assert error.value.status_code == 400
    assert options["email"] not in str(error.value)


def test_invite_timeout_is_uncertain_and_never_replayed(client, nomad_http):
    def respond(request):
        raise httpx.ReadTimeout("fixture timeout", request=request)

    nomad_http.respond = respond
    with pytest.raises(IdentityWriteOutcomeUnknownError, match="identity.users.invite"):
        client.identity.users.invite({"email": "recipient@example.org"})
    assert len(nomad_http.requests) == 1


def test_group_lifecycle_maps_ids_roles_metadata_and_status(client, nomad_http):
    def respond(request):
        if request.url.path.endswith("/users/me"):
            return httpx.Response(200, json={"user_id": "owner-id"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(201 if request.url.path.endswith("/groups") else 200, json=_GROUP)

    nomad_http.respond = respond
    groups = client.identity.groups
    group = groups.create(
        name="Diffraction team",
        members=[User(user_id="ana-id"), GroupMember(user_id="sam-id", role=GroupRole.MAINTAINER)],
        extra_json={"beamline": "P01"},
    )
    assert isinstance(group, Group) and group.owner_id == "owner-id"
    assert group.name == "Diffraction team" and group.members[1].role is GroupRole.MEMBER
    assert Group.model_validate(group.model_dump()).members == group.members
    assert groups.get(group).group_id == group.group_id
    groups.update(group, description="New description")
    groups.replace_members(group, members=group.members)
    groups.update(group, legacy_member_ids=["ana-id"])
    assert groups.delete(group) is None
    me, create, read, edit, replace, legacy, revoke = nomad_http.requests
    assert me.method == "GET" and me.url.path.endswith("/users/me")
    assert json.loads(create.content) == {
        "beamline": "P01", "group_name": "Diffraction team",
        "members_info": [
            {"user_id": "owner-id", "role": "owner"},
            {"user_id": "ana-id", "role": "member"},
            {"user_id": "sam-id", "role": "maintainer"},
        ],
    }
    assert read.method == "GET" and read.url.path.endswith("/groups/diffraction-team")
    assert edit.url.path.endswith("/groups/diffraction-team/edit")
    assert json.loads(edit.content) == {"description": "New description"}
    assert json.loads(replace.content) == {"members_info": _GROUP["members_info"]}
    assert json.loads(legacy.content) == {"members": ["ana-id"]}
    assert revoke.method == "DELETE" and not revoke.content


def test_group_resolves_selectors_before_writing(client, nomad_http):
    def respond(request):
        if request.url.path.endswith("/users/me"):
            return httpx.Response(200, json={"user_id": "owner-id"})
        return httpx.Response(200, json={"data": [{"user_id": "ana-id"}]})

    nomad_http.respond = respond
    groups = client.identity.groups
    with pytest.raises(ValueError, match="unique"):
        groups.create(members=[{"email": "ana@example.org"}, "ana-id"])
    assert [request.method for request in nomad_http.requests] == ["GET", "GET"]
    with pytest.raises(ValueError, match="exactly one"):
        groups.create(members=[{"prefix": "ana"}])
    with pytest.raises(ValueError, match="current group owner"):
        groups.replace_members("diffraction-team", members=[])
    assert len(nomad_http.requests) == 2


def test_group_create_delegates_empty_membership_and_rejects_owner_overrides(nomad_http):
    nomad_http.respond = lambda request: httpx.Response(201, json=_GROUP)
    with NomadClient(
        credential=BearerTokenCredential("directory-fixture"), enforced_scopes={Scope.GROUPS_WRITE},
    ) as client:
        groups = client.identity.groups
        groups.create(name="Diffraction team", members=[])
        with pytest.raises(ValueError, match="assigns the owner automatically"):
            groups.create(members=[GroupMember(user_id="other-id", role=GroupRole.OWNER)])
        with pytest.raises(ValueError, match="custom fields"):
            groups.create(extra_json={"owner": "other-id"})
        with pytest.raises(TypeError, match="owner"):
            groups.create(owner="other-id")
        with pytest.raises(ScopeNotAllowedError) as error:
            groups.create(members=["other-id"])
    assert error.value.missing_scopes == {Scope.USERS_READ}
    assert len(nomad_http.requests) == 1
    assert nomad_http.requests[0].method == "POST"
    assert json.loads(nomad_http.requests[0].content) == {"group_name": "Diffraction team"}


def test_group_list_is_lazy_and_uses_only_the_cursor(client, nomad_http):
    def respond(request):
        more = "page_after_value" not in request.url.params
        return httpx.Response(200, json={
            "data": [_GROUP] if more else [{"group_id": "g2", "owner": "owner-id", "members_info": []}],
            "pagination": {
                "total": 2, "next_page_after_value": "next&opaque" if more else None,
                "next_page_url": "https://different.example.org/",
            },
        })

    nomad_http.respond = respond
    listing = client.identity.groups.list(
        group_id=["diffraction-team", "g2"], page=1, page_size=1, extra_query={"facility": "lab"},
    ).filter(search_terms="diffraction")
    assert not nomad_http.requests
    assert [page.items[0].group_id for page in listing.by_page()] == ["diffraction-team", "g2"]
    first, second = nomad_http.requests
    assert first.url.params.get_list("group_id") == ["diffraction-team", "g2"]
    assert first.url.params["page"] == "1" and first.url.params["facility"] == "lab"
    assert second.url.host == first.url.host and second.url.params["page_after_value"] == "next&opaque"
    assert "page" not in second.url.params
    assert len(list(client.identity.groups.list(limit=0))) == 0
    assert len(nomad_http.requests) == 2


def test_group_missing_roles_and_not_found(client, nomad_http):
    legacy = {"group_id": "group-id", "owner": "owner-id", "members": ["owner-id"]}
    nomad_http.respond = lambda request: httpx.Response(200, json={"data": [legacy]})
    page = next(client.identity.groups.list().by_page())
    assert page.pagination is None
    assert page.items[0].members is None
    assert page.items[0].member_ids == ("owner-id",)
    nomad_http.respond = lambda request: httpx.Response(404)
    with pytest.raises(GroupNotFoundError):
        client.identity.groups.get("group-id")


def test_group_write_is_uncertain_after_unusable_success(client, nomad_http):
    nomad_http.respond = lambda request: httpx.Response(200, json={})
    with pytest.raises(IdentityWriteOutcomeUnknownError) as error:
        client.identity.groups.update("group-id", description="changed")
    assert error.value.status_code == 200
    assert len(nomad_http.requests) == 1


def test_group_scope_and_cross_deployment_guard(nomad_http):
    nomad_http.respond = lambda request: httpx.Response(200, json={"user_id": "remote-id"})
    with NomadClient(credential=BearerTokenCredential("different", endpoint="https://oasis.example/api/v1")) as remote:
        member = remote.identity.users.get_by_id("remote-id")
    with NomadClient(credential=BearerTokenCredential("local")) as local:
        with pytest.raises(CredentialEndpointMismatchError):
            local.identity.groups.create(members=[member])
    with NomadClient(credential=BearerTokenCredential("local"), enforced_scopes={Scope.USERS_READ}) as local:
        with pytest.raises(ScopeNotAllowedError) as error:
            local.identity.groups.create(members=[{"email": "ana@example.org"}])
        assert error.value.missing_scopes == {Scope.GROUPS_WRITE}
    assert len(nomad_http.requests) == 1
