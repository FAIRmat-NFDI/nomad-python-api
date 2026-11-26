import json

import httpx
import pytest

from nomad_python_api import (
    NomadClient,
    OwnershipResourceRef,
    OwnershipResourceType,
    OwnershipTransferCreateRequest,
    OwnershipTransferDirection,
    Scope,
)
from nomad_python_api.exceptions import (
    OwnershipTransferNotFoundError,
    OwnershipTransferNotPendingError,
    OwnershipTransferOutcomeUnknownError,
    ScopeNotAllowedError,
)
from nomad_python_api.identity import BearerTokenCredential

_TRANSFER = {
    "transfer_id": "transfer-1",
    "resource_type": "group",
    "resource_id": "group-1",
    "resource_name": "Diffraction team",
    "source_user_id": "source-user",
    "target_user_id": "target-user",
    "requested_at": "2026-11-26T08:00:00Z",
    "updated_at": "2026-11-26T08:01:00Z",
}


@pytest.fixture
def client(nomad_http):
    with NomadClient(credential=BearerTokenCredential("ownership-fixture")) as value:
        yield value


def test_create_accept_and_cancel_with_object_and_rest_inputs(client, nomad_http):
    group_data = {
        "group_id": "group-1", "group_name": "Diffraction team", "owner": "source-user",
    }

    def respond(request):
        if request.url.path.endswith("/respond"):
            return httpx.Response(200, json={
                "transfer_id": "transfer-1", "resource_type": "group", "resource_id": "group-1",
                "result": {"data": dict(group_data, owner="target-user")},
            })
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={
                "transfer_id": "transfer-1", "resource_type": "group", "resource_id": "group-1",
            })
        if request.url.path.endswith("/groups/group-1"):
            return httpx.Response(200, json=group_data)
        if request.method == "GET":
            return httpx.Response(200, json={"transfers": []})
        return httpx.Response(200, json=_TRANSFER)

    nomad_http.respond = respond
    group = client.identity.groups.get("group-1")
    transfer = group.ownership_transfers.create(target={"email": "email1@example.org"})
    assert transfer.transfer_id == "transfer-1"
    assert json.loads(nomad_http.requests[1].content) == {
        "resource_type": "group", "resource_id": "group-1",
        "target_user": "email1@example.org", "target_user_type": "email",
    }

    accepted = transfer.accept()
    assert accepted.resource.owner_id == "target-user"
    assert accepted.resource.ownership_transfers.get(state="pending") == []

    cancelled = client.ownership_transfers.cancel({
        "transfer_id": transfer.transfer_id, "resource_type": "group",
    })
    assert cancelled.transfer_id == transfer.transfer_id
    assert json.loads(nomad_http.requests[2].content) == {"action": "accept"}


def test_create_accepts_complete_typed_and_mapping_requests(client, nomad_http):
    nomad_http.respond = lambda request: httpx.Response(200, json=_TRANSFER)
    request = OwnershipTransferCreateRequest(
        resource_type="group", resource_id="group-1",
        target_user="target-user", target_user_type="user_id",
    )
    assert client.ownership_transfers.create(request).resource_id == "group-1"
    assert client.ownership_transfers.create(request.model_dump()).resource_id == "group-1"
    assert len(nomad_http.requests) == 2


def test_list_combines_built_in_types_and_get_discovers_type(client, nomad_http):
    older = dict(_TRANSFER, resource_type="upload", resource_id="upload-1", updated_at="2026-11-26T07:00:00Z")

    def respond(request):
        resource_type = request.url.params["resource_type"]
        if "/transfer-1" in request.url.path:
            return httpx.Response(404 if resource_type == "upload" else 200, json=_TRANSFER)
        return httpx.Response(200, json={"transfers": [older if resource_type == "upload" else _TRANSFER]})

    nomad_http.respond = respond
    transfers = client.ownership_transfers.get(direction=OwnershipTransferDirection.ALL)
    assert [item.resource_type for item in transfers] == ["group", "upload"]
    assert client.ownership_transfers.get("transfer-1").resource_type == "group"
    assert [request.url.params["resource_type"] for request in nomad_http.requests] == [
        "upload", "group", "upload", "group",
    ]


def test_explicit_custom_type_skips_discovery(client, nomad_http):
    custom = dict(_TRANSFER, resource_type="dataset", resource_id="dataset-1")
    nomad_http.respond = lambda request: httpx.Response(200, json=custom)
    result = client.ownership_transfers.get("transfer-1", resource_type="dataset")
    assert result.resource_type == "dataset"
    assert len(nomad_http.requests) == 1


def test_resource_and_target_normalization(client, nomad_http):
    nomad_http.respond = lambda request: httpx.Response(200, json=_TRANSFER)
    ref = OwnershipResourceRef.group("group-1")
    client.ownership_transfers.create(resource=ref, target={"username": "researcher1"})
    client.ownership_transfers.create(
        resource={"group_id": "group-1", "group_name": "Diffraction team"},
        target={"user_id": "target-user", "email": "email1@example.org"},
    )
    assert json.loads(nomad_http.requests[0].content)["target_user_type"] == "username"
    assert json.loads(nomad_http.requests[1].content)["target_user_type"] == "user_id"


@pytest.mark.parametrize("bad_resource", [
    {}, {"resource_type": "group"}, {"group_id": "g", "upload_id": "u"},
    {"resource_type": "group", "resource_id": "g", "group_id": "g"},
])
def test_invalid_resources_fail_before_http(client, nomad_http, bad_resource):
    with pytest.raises(ValueError):
        client.ownership_transfers.create(resource=bad_resource, target={"user_id": "target"})
    assert not nomad_http.requests


def test_bulk_is_sequential_continues_failures_and_rejects_duplicates(client, nomad_http):
    def respond(request):
        transfer_id = request.url.path.split("/")[-2]
        if transfer_id == "transfer-2":
            return httpx.Response(400, json={"detail": "not pending"})
        return httpx.Response(200, json={
            "transfer_id": transfer_id, "resource_type": "group", "resource_id": "group-1",
        })

    nomad_http.respond = respond
    result = client.ownership_transfers.accept(
        ["transfer-1", "transfer-2", "transfer-3"], resource_type="group",
    )
    assert [item.transfer_id for item in result.succeeded] == ["transfer-1", "transfer-3"]
    assert isinstance(result.failed[0].error, OwnershipTransferNotPendingError)
    with pytest.raises(ValueError, match="unique"):
        client.ownership_transfers.cancel(["transfer-1", "transfer-1"], resource_type="group")
    assert len(nomad_http.requests) == 3


def test_errors_and_uncertain_writes_are_typed(client, nomad_http):
    nomad_http.respond = lambda request: httpx.Response(404, json={})
    with pytest.raises(OwnershipTransferNotFoundError):
        client.ownership_transfers.get("missing", resource_type="group")

    nomad_http.respond = lambda request: httpx.Response(503, json={})
    with pytest.raises(OwnershipTransferOutcomeUnknownError):
        client.ownership_transfers.cancel("transfer-1", resource_type="group")

    nomad_http.respond = lambda request: httpx.Response(200, json={"unexpected": True})
    with pytest.raises(OwnershipTransferOutcomeUnknownError):
        client.ownership_transfers.accept("transfer-1", resource_type="group")


def test_scope_policy_and_metadata_are_local(nomad_http):
    with NomadClient(
        credential=BearerTokenCredential("ownership-fixture"),
        allowed_scopes={Scope.UPLOADS_READ},
    ) as client:
        info = client.ownership_transfers.get_operation_info("create")
        assert info.required_scopes == {Scope.UPLOADS_READ, Scope.UPLOADS_WRITE}
        with pytest.raises(ScopeNotAllowedError):
            client.ownership_transfers.create(
                resource=OwnershipResourceRef.group("group-1"), target={"user_id": "target-user"},
            )
    assert not nomad_http.requests


def test_detached_models_cannot_chain():
    from nomad_python_api import OwnershipTransfer
    from nomad_python_api.identity import Group

    transfer = OwnershipTransfer.model_validate(_TRANSFER)
    group = Group(group_id="group-1", owner_id="source-user")
    with pytest.raises(RuntimeError, match="not bound"):
        transfer.accept()
    with pytest.raises(RuntimeError, match="not bound"):
        group.ownership_transfers.get()
