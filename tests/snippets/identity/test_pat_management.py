"""CI-tested examples for the PAT user guide."""

import json

import httpx
import pytest

pytestmark = pytest.mark.snippet
_CREATED = "2026-04-01T10:00:00Z"


@pytest.fixture
def deployment(monkeypatch, nomad_http):
    active = {}

    def respond(request):
        authorization = request.headers["Authorization"]
        path = request.url.path.split("/api/v1", 1)[1]
        if path == "/users/me":
            if authorization == "Bearer keycloak-fixture" or authorization[7:] in active.values():
                return httpx.Response(200, json={
                    "user_id": "researcher-id", "username": "researcher", "name": "Researcher",
                })
            return httpx.Response(401)
        if authorization != "Bearer keycloak-fixture":
            return httpx.Response(403)

        def metadata(pat_id):
            return {
                "id": pat_id, "name": "Diffraction analysis", "scopes": ["users:read", "uploads:read"],
                "revoked": False, "created_at": _CREATED,
            }

        if request.method == "POST":
            if path.endswith("/rotate"):
                active.pop(path.split("/")[-2])
            pat_id = f"{len(nomad_http.requests):024x}"
            active[pat_id] = f"fixture-secret-{len(nomad_http.requests)}"
            status = 200 if path.endswith("/rotate") else 201
            pat = metadata(pat_id)
            if status == 201:
                pat["name"] = json.loads(request.content)["metadata"]["name"]
            return httpx.Response(status, json={"pat": pat, "raw_token": active[pat_id]})
        if request.method == "DELETE":
            active.pop(path.split("/")[-1])
            return httpx.Response(204)
        if path != "/auth/pats":
            return httpx.Response(200, json=metadata(path.split("/")[-1]))
        cursor = request.url.params.get("page_after_value")
        pat_id = "507f1f77bcf86cd799439012" if cursor else "507f1f77bcf86cd799439011"
        return httpx.Response(200, json={
            "data": [metadata(pat_id)], "query": {},
            "pagination": {"total": 2, "next_page_after_value": None if cursor else "opaque-cursor"},
        })

    nomad_http.respond = respond
    monkeypatch.setenv("NOMAD_KEYCLOAK_ACCESS_TOKEN", "keycloak-fixture")
    monkeypatch.setenv("NOMAD_PAT", "job-fixture")
    return nomad_http.requests


def test_management_sign_in(deployment):
    # --8<-- [start:pat_client]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        # Read the account linked to the Keycloak access token.
        me = client.identity.me()
        print(me.username, me.as_user().name)
    # --8<-- [end:pat_client]

    assert me.username == "researcher"
    assert str(deployment[0].url).startswith("https://nomad-lab.eu/prod/v1/api/v1")


def test_object_create(deployment):
    # --8<-- [start:pat_create_object]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential, PatCreateOptions

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        # Grant the permissions needed by the research job.
        options = PatCreateOptions(
            name="Diffraction analysis",
            description="Read account and project metadata from an HPC job",
            scopes=[Scope.USERS_READ, "uploads:read"],
            expires_in_days=30,
        )
        issued = client.identity.pats.create(options)
        print(issued.pat.name, issued.pat.expired_at)
    # --8<-- [end:pat_create_object]

    assert issued.pat.name == "Diffraction analysis"


def test_pat_lifecycle(deployment):
    # --8<-- [start:pat_lifecycle]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        pats = client.identity.pats
        # Issue a temporary PAT for this example.
        issued = pats.create({"name": "Temporary diffraction job", "scopes": ["users:read"]})

        job_credential = BearerTokenCredential.from_issued(issued)
        with NomadClient(credential=job_credential) as job:
            print(job.identity.me().username)

        metadata = pats.get(issued.pat.id)
        # Rotate the PAT before handing the replacement to the job.
        replacement = pats.rotate(job_credential)
        new_job_credential = BearerTokenCredential.from_issued(replacement)
        with NomadClient(credential=new_job_credential) as job:
            print(job.identity.me().username)

        # Run this when the replacement is no longer needed.
        pats.revoke(replacement.pat)
    # --8<-- [end:pat_lifecycle]
    assert metadata.id == issued.pat.id
    assert replacement.pat.id != metadata.id
    assert deployment[-1].method == "DELETE"


def test_bulk_dictionary_options(deployment):
    # --8<-- [start:pat_create_dict]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        # Reuse the same scopes for both research runs.
        pats = client.identity.pats
        shared_options = {"scopes": ["users:read", "uploads:read"]}
        runs = [
            {"name": "Diffraction preview"},  # Use the deployment's default expiry.
            {"name": "Diffraction refinement", "expires_in_days": 7},
        ]
        issued_by_run = {}
        for run in runs:
            issued_by_run[run["name"]] = pats.create({**shared_options, **run})
    # --8<-- [end:pat_create_dict]
    preview, refinement = (json.loads(request.content) for request in deployment)
    assert list(issued_by_run) == [run["name"] for run in runs]
    assert [issued.pat.name for issued in issued_by_run.values()] == list(issued_by_run)
    assert preview["metadata"] == {**shared_options, "name": runs[0]["name"]}
    assert "expires_in_days" not in preview
    assert refinement["metadata"] == {**shared_options, "name": runs[1]["name"]}
    assert refinement["expires_in_days"] == 7


def test_filtering_and_resume(deployment):
    # --8<-- [start:pat_list]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        # Get the signed-in account and use either listing method.
        me = client.identity.me()
        pats = client.identity.pats
        for pat in me.get_all_pats():
            print(pat.name, pat.revoked)

        for pat in pats.list(state="active", limit=5):
            print(pat.id, pat.expired_at)

        filters = {"search": "Diffraction", "created_after": "2026-04-01T00:00:00Z"}
        selected = pats.list(order_by="created_desc").filter(**filters).filter(revoked=False)
        for pat in selected:
            print(pat.name, pat.created_at)
    # --8<-- [end:pat_list]

    # --8<-- [start:pat_pages]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        # Start from the first page with a fixed filter.
        listing = client.identity.pats.list(state="active", page_size=20)
        first_page = next(listing.by_page())
        for pat in first_page.items:
            print(pat.name)

        # Save this cursor only after processing the whole page.
        checkpoint = first_page.next_cursor
        if checkpoint is not None:
            for page in listing.by_page(continuation_token=checkpoint):
                for pat in page.items:
                    print(pat.name)
    # --8<-- [end:pat_pages]
    assert deployment[-1].url.params["page_after_value"] == "opaque-cursor"
    assert any(request.url.params.get("revoked") == "false" for request in deployment)


def test_oasis_extensions(deployment):
    # --8<-- [start:pat_oasis]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # Set the API URL of the Oasis that supports these extra fields.
    endpoint = "https://research.example.org/api/v1"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    with NomadClient(credential=credential) as client:
        # Use these fields only if your Oasis provides them.
        pats = client.identity.pats
        options = {"name": "Diffraction analysis", "scopes": ["users:read"]}
        issued = pats.create(options, extra_json={"institute_tag": "beamline"})
        matches = pats.list(
            state="active", extra_query={"institute_tag": "beamline"},
        )
        for pat in matches:
            print(pat.name)

        try:
            pats.list(extra_query={"state": "inactive"})
        except ValueError:
            print("Pass state as a named filter.")
    # --8<-- [end:pat_oasis]
    assert json.loads(deployment[0].content)["institute_tag"] == "beamline"
    assert deployment[1].url.params["institute_tag"] == "beamline"

def test_pat_permission_error(deployment, capsys):
    # --8<-- [start:pat_permission_error]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.exceptions import AuthorizationError, ClientAuthenticationError
    from nomad_python_api.identity import BearerTokenCredential

    # Use the issuing deployment and the metadata ID of your PAT.
    endpoint = "prod"
    pat_id = "507f1f77bcf86cd799439011"
    credential = BearerTokenCredential(
        os.environ["NOMAD_PAT"], endpoint=endpoint,
    )
    with NomadClient(credential=credential) as job:
        try:
            job.identity.pats.get(pat_id)
        except AuthorizationError:
            print("Sign in with a management access token to read PAT metadata.")
        except ClientAuthenticationError:
            print("Check the token and its issuing deployment.")
    # --8<-- [end:pat_permission_error]
    assert "management access token" in capsys.readouterr().out


@pytest.mark.parametrize(("failure", "expected"), [
    ("target", "metadata ID and account"),
    ("uncertain", "Check the original PAT"),
])
def test_rotation_error_recovery(nomad_http, monkeypatch, capsys, failure, expected):
    def respond(request):
        if failure == "uncertain":
            raise httpx.ReadTimeout("test-only timeout", request=request)
        return httpx.Response(404)

    nomad_http.respond = respond
    monkeypatch.setenv("NOMAD_KEYCLOAK_ACCESS_TOKEN", "keycloak-fixture")

    # --8<-- [start:pat_rotation_errors]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.exceptions import PatNotFoundError, PatWriteOutcomeUnknownError
    from nomad_python_api.identity import BearerTokenCredential

    # For an Oasis, replace "prod" with its full HTTPS API v1 URL.
    endpoint = "prod"
    credential = BearerTokenCredential(
        os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"],
        endpoint=endpoint,
    )
    # Supply the metadata ID of the PAT you intend to replace.
    pat_id = "507f1f77bcf86cd799439011"
    with NomadClient(credential=credential) as client:
        pats = client.identity.pats
        try:
            replacement = pats.rotate(pat_id)
        except PatNotFoundError:
            print("Check the target's PAT metadata ID and account.")
        except PatWriteOutcomeUnknownError:
            print("Check the original PAT with pats.get(pat_id) before another write.")
    # --8<-- [end:pat_rotation_errors]
    assert expected in capsys.readouterr().out
