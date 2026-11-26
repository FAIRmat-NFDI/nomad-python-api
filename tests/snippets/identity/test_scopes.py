"""CI-tested examples for the Access and scopes guide."""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

import nomad_python_api  # noqa: F401  Import before fixtures patch httpx.Client.

pytestmark = pytest.mark.snippet
_CENTRAL = "https://nomad-lab.eu/prod/v1/api/v1"
_ISSUER = "https://nomad-lab.eu/fairdi/keycloak/auth/realms/fairdi_nomad_prod"
_TOKEN = {"access_token": "example-access-token", "token_type": "Bearer", "expires_in": 300}
_PAT = {
    "id": "507f1f77bcf86cd799439011", "name": "Account check", "scopes": ["users:read"],
    "revoked": False, "created_at": "2026-11-26T08:00:00Z",
}


@pytest.fixture
def deployment(nomad_http, monkeypatch):
    monkeypatch.setenv("NOMAD_PAT", "example-pat")
    monkeypatch.setenv("NOMAD_PASSWORD", "offline-example-password")
    monkeypatch.setenv("NOMAD_KEYCLOAK_ACCESS_TOKEN", "example-keycloak-token")

    def respond(request):
        path = request.url.path
        if path.endswith("/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": _ISSUER,
                "authorization_endpoint": _ISSUER + "/protocol/openid-connect/auth",
                "token_endpoint": _ISSUER + "/protocol/openid-connect/token",
            })
        if path.endswith("/token"):
            return httpx.Response(200, json=_TOKEN)
        if path.endswith("/auth/pats"):
            return httpx.Response(201, json={"pat": _PAT, "raw_token": "example-issued-pat"})
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"user_id": "example-id", "username": "demo"})
        return httpx.Response(403)

    nomad_http.respond = respond
    return nomad_http


def _paths(deployment):
    return [request.url.path.rsplit("/", 1)[1] for request in deployment.requests]


def test_read_only_notebook(deployment, browser_sign_in, capsys):
    # --8<-- [start:scopes_read_only_notebook]
    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.exceptions import ScopeNotAllowedError
    from nomad_python_api.identity import BrowserCredential

    # A browser token carries all of your account's permissions.
    credential = BrowserCredential(
        issuer="https://nomad-lab.eu/fairdi/keycloak/auth/realms/fairdi_nomad_prod",
        client_id="nomad_public",
        discover=True,
    )

    # This notebook may only read, whatever the token would allow.
    with NomadClient(
        credential=credential,
        enforced_scopes={Scope.USERS_READ, Scope.GROUPS_READ},
    ) as client:
        account = client.identity.me()
        print("Signed in as:", account.username)
        try:
            client.identity.groups.delete("example-group-id")
        except ScopeNotAllowedError as error:
            missing = ", ".join(sorted(scope.value for scope in error.missing_scopes))
            print(f"Blocked locally: {error.operation} needs {missing}")
    # --8<-- [end:scopes_read_only_notebook]

    assert capsys.readouterr().out.splitlines() == [
        "Signed in as: demo",
        "Blocked locally: identity.groups.delete needs groups:delete",
    ]
    assert _paths(deployment) == ["openid-configuration", "token", "me"]
    assert len(browser_sign_in) == 1


def test_per_worker_policies(deployment, capsys):
    # --8<-- [start:scopes_per_worker]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    # One credential, two clients with different local policies.
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    reader = NomadClient(credential=credential, enforced_scopes={Scope.USERS_READ})
    maintainer = NomadClient(
        credential=credential,
        enforced_scopes={Scope.USERS_READ, Scope.GROUPS_READ, Scope.GROUPS_WRITE},
    )
    with reader, maintainer:
        update = maintainer.identity.get_operation_info("groups.update")
        for name, client in (("reader", reader), ("maintainer", maintainer)):
            allowed = update.required_scopes <= (client.enforced_scopes or set())
            print(f"{name} may update groups: {allowed}")
        print("Reader account:", reader.identity.me().username)
    # --8<-- [end:scopes_per_worker]

    assert capsys.readouterr().out.splitlines() == [
        "reader may update groups: False",
        "maintainer may update groups: True",
        "Reader account: demo",
    ]
    assert _paths(deployment) == ["me"]


def test_library_boundary(deployment, capsys):
    # --8<-- [start:scopes_library_boundary]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.exceptions import ScopeNotAllowedError
    from nomad_python_api.identity import BearerTokenCredential

    def summarize_account(client: NomadClient) -> str:
        """A helper that should only ever read."""
        try:
            client.identity.groups.delete("example-group-id")  # A bug in the helper
        except ScopeNotAllowedError:
            pass
        return client.identity.me().username

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    # Hand the helper a client that can only read your account.
    with NomadClient(credential=credential, enforced_scopes={Scope.USERS_READ}) as read_only:
        print("Summary:", summarize_account(read_only))
    # --8<-- [end:scopes_library_boundary]

    assert capsys.readouterr().out.splitlines() == ["Summary: demo"]
    assert _paths(deployment) == ["me"]


def test_granted_from_pat(deployment, capsys):
    # --8<-- [start:scopes_granted_from_pat]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.exceptions import ScopeNotGrantedError
    from nomad_python_api.identity import BearerTokenCredential, PatCreateOptions

    signed_in = BearerTokenCredential(os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"])
    with NomadClient(credential=signed_in) as client:
        issued = client.identity.pats.create(
            PatCreateOptions(name="Account check", scopes=[Scope.USERS_READ], expires_in_days=1)
        )

    # The SDK knows exactly what NOMAD granted to this PAT.
    job_credential = BearerTokenCredential.from_issued(issued)
    print("Granted:", sorted(job_credential.granted_scopes or ()))

    with NomadClient(credential=job_credential) as job:
        print("Account:", job.identity.me().username)
        try:
            job.identity.groups.delete("example-group-id")
        except ScopeNotGrantedError as error:
            print("Not sent:", error)
    # --8<-- [end:scopes_granted_from_pat]

    assert capsys.readouterr().out.splitlines() == [
        "Granted: ['users:read']",
        "Account: demo",
        "Not sent: identity.groups.delete requires scopes the credential's token was not granted: "
        "groups:delete.",
    ]
    assert _paths(deployment) == ["pats", "me"]


def test_raw_token_grants_unknown(deployment, capsys):
    # --8<-- [start:scopes_raw_token_unknown]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.exceptions import AuthorizationError
    from nomad_python_api.identity import BearerTokenCredential

    # A pasted token: the SDK cannot know its scopes, so NOMAD decides.
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    print("Granted:", "unknown" if credential.granted_scopes is None else credential.granted_scopes)
    with NomadClient(credential=credential) as client:
        try:
            client.identity.groups.delete("example-group-id")
        except AuthorizationError:
            print("NOMAD refused the request (HTTP 403).")
    # --8<-- [end:scopes_raw_token_unknown]

    assert capsys.readouterr().out.splitlines() == [
        "Granted: unknown",
        "NOMAD refused the request (HTTP 403).",
    ]
    assert _paths(deployment) == ["example-group-id"]


def test_password_requested_scopes(deployment, capsys):
    # --8<-- [start:scopes_password_requested]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import PasswordCredential

    credential = PasswordCredential(
        username="user1",
        password=os.environ["NOMAD_PASSWORD"],
        # Asked for at sign-in. Standard NOMAD ignores it.
        requested_scopes={"users:read"},
    )
    # The reliable restriction is the client's enforced policy.
    with NomadClient(credential=credential, enforced_scopes={Scope.USERS_READ}) as client:
        print("Requested:", credential.requested_scopes)
        print("Account:", client.identity.me().username)
    # --8<-- [end:scopes_password_requested]

    assert capsys.readouterr().out.splitlines() == ["Requested: ('users:read',)", "Account: demo"]
    login = deployment.requests[0]
    assert str(login.url) == _CENTRAL + "/auth/token"
    assert parse_qs(login.content.decode())["scope"] == ["users:read"]


def test_default_browser_scope_is_openid(deployment, browser_sign_in):
    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BrowserCredential

    credential = BrowserCredential(issuer=_ISSUER, client_id="nomad_public", discover=True)
    with NomadClient(credential=credential) as client:
        client.identity.me()
    assert parse_qs(urlsplit(browser_sign_in[0]).query)["scope"] == ["openid"]
