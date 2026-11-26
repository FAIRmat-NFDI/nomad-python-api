"""CI-tested examples for the ownership-transfer guide."""

import json

import httpx
import pytest

pytestmark = pytest.mark.snippet


@pytest.fixture(autouse=True)
def deployment(monkeypatch, nomad_http):
    monkeypatch.setenv("NOMAD_PAT", "ownership-fixture")
    transfer = {
        "transfer_id": "transfer-id-1",
        "resource_type": "group",
        "resource_id": "group-id-1",
        "resource_name": "Diffraction team",
        "source_user_id": "source-user-id",
        "target_user_id": "target-user-id",
        "requested_at": "2026-11-26T08:00:00Z",
        "updated_at": "2026-11-26T08:01:00Z",
    }

    def respond(request):
        path = request.url.path.split("/api/v1", 1)[1]
        if path == "/groups/group-id-1":
            return httpx.Response(200, json={
                "group_id": "group-id-1", "group_name": "Diffraction team",
                "owner": "source-user-id",
            })
        if request.method == "GET" and path == "/ownership-transfers":
            return httpx.Response(200, json={
                "transfers": [dict(transfer, resource_type=request.url.params["resource_type"])],
            })
        if request.method == "GET":
            if request.url.params["resource_type"] == "upload":
                return httpx.Response(404)
            return httpx.Response(200, json=transfer)
        if path.endswith("/respond"):
            return httpx.Response(200, json={
                "transfer_id": "transfer-id-1", "resource_type": "group",
                "resource_id": "group-id-1", "result": {"status": "accepted"},
            })
        if path.endswith("/cancel"):
            return httpx.Response(200, json={
                "transfer_id": path.split("/")[-2], "resource_type": "group",
                "resource_id": "group-id-1",
            })
        body = json.loads(request.content)
        return httpx.Response(200, json=dict(
            transfer,
            resource_type=body["resource_type"],
            resource_id=body["resource_id"],
        ))

    nomad_http.respond = respond


def test_create_from_group_chain():
    # --8<-- [start:ownership_create_chain]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    group_id = "group-id-1"
    target_email = "email1@example.org"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])

    with NomadClient(credential=credential) as client:
        group = client.identity.groups.get(group_id)

        # The returned transfer remembers this client, so later actions can be chained.
        transfer = group.ownership_transfers.create(target={"email": target_email})
        print(transfer.resource_type, transfer.resource_name)
    # --8<-- [end:ownership_create_chain]
    assert transfer.resource_type == "group"


def test_create_from_objects_and_dictionaries():
    # --8<-- [start:ownership_create_forms]
    import os

    from nomad_python_api import (
        NomadClient,
        OwnershipResourceRef,
        OwnershipTransferCreateRequest,
    )
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    resource = OwnershipResourceRef.group("group-id-1")
    target = {"username": "user1"}

    with NomadClient(credential=credential) as client:
        # Object plus dictionary style is useful when values come from earlier SDK calls.
        first = client.ownership_transfers.create(resource=resource, target=target)

        # A complete typed REST request is useful for validated batch input.
        options = OwnershipTransferCreateRequest(
            resource_type="group",
            resource_id="group-id-1",
            target_user="target-user-id",
            target_user_type="user_id",
        )
        second = client.ownership_transfers.create(options)
        print(first.resource_id, second.resource_id)
    # --8<-- [end:ownership_create_forms]
    assert first.resource_id == second.resource_id == "group-id-1"


def test_list_filter_and_known_id():
    # --8<-- [start:ownership_list_get]
    import os

    from nomad_python_api import NomadClient, OwnershipResourceType, OwnershipTransferDirection
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])

    with NomadClient(credential=credential) as client:
        # With no resource type, the SDK combines built-in group and project transfers.
        pending = client.ownership_transfers.get(
            direction=OwnershipTransferDirection.INCOMING,
            state="pending",
        )

        # If the type is known, pass it to avoid discovery requests.
        transfer = client.ownership_transfers.get(
            "transfer-id-1",
            resource_type=OwnershipResourceType.GROUP,
        )
        print(len(pending), transfer.resource_name)
    # --8<-- [end:ownership_list_get]
    assert len(pending) == 2


def test_chained_and_bulk_actions():
    # --8<-- [start:ownership_actions]
    import os

    from nomad_python_api import NomadClient, OwnershipResourceType
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])

    with NomadClient(credential=credential) as client:
        # A bare known ID is discoverable across the built-in resource types.
        accepted = client.ownership_transfers.get("transfer-id-1").accept()

        # Bulk helpers are sequential and report each success or failure.
        result = client.ownership_transfers.cancel(
            ["transfer-id-2", "transfer-id-3"],
            resource_type=OwnershipResourceType.GROUP,
        )
        print(accepted.transfer_id, len(result.succeeded), len(result.failed))
    # --8<-- [end:ownership_actions]
    assert len(result.succeeded) == 2 and not result.failed
