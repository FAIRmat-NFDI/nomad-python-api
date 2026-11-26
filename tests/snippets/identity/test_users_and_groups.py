import json

import httpx
import pytest

pytestmark = pytest.mark.snippet


@pytest.fixture(autouse=True)
def deployment(nomad_http, monkeypatch):
    monkeypatch.setenv("NOMAD_PAT", "directory-fixture")
    group = {
        "group_id": "group-id-1",
        "owner": "owner-id",
        "group_name": "Diffraction team",
        "members_info": [{"user_id": "owner-id", "role": "owner"}],
    }

    def respond(request):
        path = request.url.path.split("/api/v1", 1)[1]
        if path == "/users/me":
            return httpx.Response(200, json={"user_id": "owner-id", "username": "researcher"})
        if path == "/users/invite":
            return httpx.Response(200, json={"user_id": "invited-id"} | json.loads(request.content))
        if path == "/users":
            username = request.url.params.get("username", "user1")
            return httpx.Response(200, json={"data": [{"user_id": f"{username}-id", "username": username}]})
        if path.startswith("/users/"):
            return httpx.Response(200, json={"user_id": path.rsplit("/", 1)[-1], "username": "user1"})
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST":
            body = json.loads(request.content)
            group.update({key: value for key, value in body.items() if key in {"group_name", "description", "members_info"}})
            return httpx.Response(201 if path == "/groups" else 200, json=group)
        if path == "/groups":
            return httpx.Response(200, json={"data": [group], "pagination": {"total": 1}})
        return httpx.Response(200, json=group)

    nomad_http.respond = respond


def test_directory_lookup(nomad_http):
    # --8<-- [start:directory_lookup]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # Replace these example values with your search inputs.
    email = "email1@example.org"
    username = "user2"
    prefix = "user"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential) as client:
        users = client.identity.users
        # An exact lookup returns one user. Keep the ID for later operations.
        collaborator = users.get_by_email(email)
        same_user = users.get_by_id(collaborator.user_id)
        team = users.get_many([
            {"email": email},
            {"username": username},
        ])
        # Inspect prefix matches before choosing anyone to add to a group.
        candidates = users.search(prefix=prefix)
        print(same_user.user_id, [user.user_id for user in team])
        print([(user.user_id, user.username) for user in candidates])
    # --8<-- [end:directory_lookup]
    assert collaborator.user_id == same_user.user_id
    assert [user.username for user in team] == ["user1", "user2"]
    assert candidates[0].username == "user1"
    assert len(nomad_http.requests) == 5


def test_invite():
    # --8<-- [start:directory_invite]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential, UserInviteOptions

    # Replace this example address with the intended recipient.
    email = "email1@example.org"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    invitation = UserInviteOptions(email=email)
    # This sends an invitation to the configured address.
    with NomadClient(credential=credential) as client:
        invited = client.identity.users.invite(invitation)
    print(invited.user_id)
    # --8<-- [end:directory_invite]
    assert invited.user_id == "invited-id"


def test_create_group(nomad_http):
    # --8<-- [start:directory_create_group]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential, GroupMember, GroupRole

    # Choose two different users who already have accounts.
    email = "email1@example.org"
    username = "user2"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential) as client:
        users = client.identity.users
        collaborator = users.get_by_email(email)
        maintainer = users.get_by_username(username)
        # NOMAD assigns the signed-in user as owner.
        group = client.identity.groups.create(
            name="Diffraction team",
            members=[collaborator, GroupMember(user_id=maintainer.user_id, role=GroupRole.MAINTAINER)],
        )
    # Save the group ID for later scripts.
    print(group.name, group.group_id)
    # --8<-- [end:directory_create_group]
    assert [member.role for member in group.members] == [GroupRole.OWNER, GroupRole.MEMBER, GroupRole.MAINTAINER]
    assert nomad_http.requests[-1].method == "POST"


def test_group_roles(nomad_http):
    # --8<-- [start:directory_group_roles]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential, GroupMember, GroupRole

    # Use the ID of an existing group and the username to promote.
    group_id = "group-id-1"
    username = "user2"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential) as client:
        groups = client.identity.groups
        group = groups.get(group_id)
        maintainer = client.identity.users.get_by_username(username)
        if group.members is None or maintainer.user_id == group.owner_id:
            raise ValueError("Choose a non-owner and a group with membership details.")
        groups.update(group, description="Collaborators for the next beamtime")
        # Preserve everyone else and add or promote the chosen maintainer.
        members = [member for member in group.members if member.user_id != maintainer.user_id]
        members.append(GroupMember(user_id=maintainer.user_id, role=GroupRole.MAINTAINER))
        group = groups.replace_members(group, members=members)
        print(group.group_id, len(members))
    # --8<-- [end:directory_group_roles]
    assert group.members[-1].role is GroupRole.MAINTAINER
    assert len(nomad_http.requests) == 4


def test_group_list(nomad_http):
    # --8<-- [start:directory_list_groups]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential) as client:
        # Fetch results as needed and stop after five matches.
        matches = client.identity.groups.list(limit=5).filter(search_terms="Diffraction")
        for group in matches:
            print(group.name, group.group_id)
    # --8<-- [end:directory_list_groups]
    assert len(nomad_http.requests) == 1


def test_delete_group(nomad_http):
    # --8<-- [start:directory_delete_group]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # Replace this placeholder only with the ID of a group you intend to delete.
    group_id = "group-id-1"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential) as client:
        # Set this ID only for a group you have decided to delete.
        client.identity.groups.delete(group_id)
    # --8<-- [end:directory_delete_group]
    assert nomad_http.requests[-1].method == "DELETE"
