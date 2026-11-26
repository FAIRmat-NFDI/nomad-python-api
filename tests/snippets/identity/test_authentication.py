"""Runnable examples for the Authentication and REST Reference pages."""

from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.snippet
_API = "https://nomad-lab.eu/prod/v1/api/v1"
_DEV_API = "https://nomad-dev.example.org/api/v1"
_TOKEN = "test-only-token"
_SETTINGS = Path(__file__).parent / "fixtures" / "nomad-settings.json"


@pytest.fixture(autouse=True)
def fake_token(monkeypatch):
    monkeypatch.setenv("NOMAD_PAT", _TOKEN)


def assert_account_request(nomad_http, endpoint=_API):
    assert len(nomad_http.requests) == 1
    request = nomad_http.requests[0]
    assert (request.method, str(request.url), request.content) == ("GET", f"{endpoint}/users/me", b"")
    assert request.headers["authorization"] == f"Bearer {_TOKEN}"


def test_named_setup(nomad_http):
    # --8<-- [start:named_setup]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])

    with NomadClient(
        credential=credential,
        enforced_scopes={Scope.USERS_READ},
    ) as client:
        # Confirm which account the token belongs to.
        account = client.identity.me()
        print(account.user_id)
    # --8<-- [end:named_setup]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http)


def test_me_profile(nomad_http):
    nomad_http.respond = lambda request: httpx.Response(200, json={
        "user_id": "example-id", "username": "demo", "name": "Demo User",
        "affiliation": "Example institute",
    })

    # --8<-- [start:me_profile]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential) as client:
        # Load the profile once and read its local fields below.
        me = client.identity.me()

    print(me.user_id, me.name or me.username)
    profile = me.as_user()
    print(profile.affiliation)
    # --8<-- [end:me_profile]
    assert me.user_id == "example-id"
    assert profile.name == "Demo User"
    assert profile.affiliation == "Example institute"
    assert_account_request(nomad_http)


def test_configure_client_network_settings(nomad_http):
    # --8<-- [start:client_network_settings]
    import os

    from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # Tune the pool and timeouts for this client.
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(
        credential=credential,
        pool_limits=ConnectionLimits(max_connections=4, max_keepalive_connections=2),
        timeouts=NetworkTimeouts(pool=3, read=20),
    ) as client:
        account = client.identity.me()
    # --8<-- [end:client_network_settings]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http)
    options = nomad_http.client_options[0]
    assert options["limits"] == httpx.Limits(max_connections=4, max_keepalive_connections=2)
    assert options["timeout"].as_dict() == {"connect": 5, "pool": 3, "read": 20, "write": 10}


def test_basic_shared_transport(monkeypatch):
    def respond(request):
        assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
        return httpx.Response(200, json={"user_id": "example-id"})

    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond))

    # --8<-- [start:basic_shared_transport]
    import os

    from nomad_python_api import ConnectionLimits, NomadClient, NomadTransport
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    # Share one connection pool across both client lifetimes.
    with NomadTransport(pool_limits=ConnectionLimits(max_connections=4)) as transport:
        with NomadClient(credential=credential, transport=transport) as first:
            first_account = first.identity.me()
        with NomadClient(credential=credential, transport=transport) as second:
            second_account = second.identity.me()
    # --8<-- [end:basic_shared_transport]

    assert first_account.user_id == second_account.user_id == "example-id"
    assert transport.is_closed


def test_basic_borrowed_http_client(nomad_http):
    # --8<-- [start:basic_borrowed_http_client]
    import os

    import httpx

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    # Keep the caller-owned HTTP client open until all SDK calls finish.
    with httpx.Client(trust_env=False) as http_client:
        with NomadClient(credential=credential, http_client=http_client) as client:
            account = client.identity.me()
        http_client_is_open = not http_client.is_closed
    # --8<-- [end:basic_borrowed_http_client]

    assert account.user_id == "example-id"
    assert http_client_is_open
    assert_account_request(nomad_http)


def test_share_a_transport(monkeypatch):
    def respond(request):
        return httpx.Response(200, json={"user_id": request.headers["Authorization"].split()[-1]})

    monkeypatch.setenv("NOMAD_SECOND_PAT", "second-fixture-token")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond))

    # --8<-- [start:share_transport]
    import os

    from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient, NomadTransport
    from nomad_python_api.identity import BearerTokenCredential

    # Use the same deployment for both credentials and share one pool.
    endpoint = "prod"  # For an Oasis, use its full HTTPS API v1 URL.
    primary = BearerTokenCredential(os.environ["NOMAD_PAT"], endpoint=endpoint)
    secondary = BearerTokenCredential(os.environ["NOMAD_SECOND_PAT"], endpoint=endpoint)
    with NomadTransport(pool_limits=ConnectionLimits(max_connections=8)) as transport:
        with (
            NomadClient(
                credential=primary, transport=transport, timeouts=NetworkTimeouts(pool=3),
            ) as first,
            NomadClient(
                credential=secondary, transport=transport, timeouts=NetworkTimeouts(pool=10),
            ) as second,
        ):
            first_account = first.identity.me()
            second_account = second.identity.me()
    # --8<-- [end:share_transport]

    assert first_account.user_id == _TOKEN
    assert second_account.user_id == "second-fixture-token"
    assert transport.is_closed


def test_borrow_a_custom_http_client(monkeypatch, caplog):
    import httpx as test_httpx

    caplog.set_level("INFO", logger="research.nomad")
    requests = []

    def respond(request):
        requests.append(request)
        return test_httpx.Response(200, json={"user_id": "example-id"})

    def create_client(**options):
        assert options.pop("proxy") == "http://proxy.example.edu:8080"
        return original_client(transport=test_httpx.MockTransport(respond), **options)

    original_client = test_httpx.Client
    monkeypatch.setattr(test_httpx, "Client", create_client)

    # --8<-- [start:borrow_http_client]
    import logging
    import os

    import httpx

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    logger = logging.getLogger("research.nomad")

    def record_status(response: httpx.Response) -> None:
        logger.info("NOMAD response status %d", response.status_code)

    endpoint = "https://nomad-dev.example.org/api/v1"
    proxy_url = "http://proxy.example.edu:8080"
    credential = BearerTokenCredential(os.environ["NOMAD_PAT"], endpoint=endpoint)
    # Configure the external client before passing it to the SDK.
    with httpx.Client(
        proxy=proxy_url,
        limits=httpx.Limits(max_connections=8),
        timeout=httpx.Timeout(connect=5, pool=3, read=60, write=60),
        follow_redirects=False,
        trust_env=False,
        event_hooks={"response": [record_status]},
    ) as http_client:
        with NomadClient(credential=credential, http_client=http_client) as client:
            account = client.identity.me()
    # --8<-- [end:borrow_http_client]

    assert account.user_id == "example-id"
    assert [str(request.url) for request in requests] == [f"{_DEV_API}/users/me"]
    assert caplog.messages == ["NOMAD response status 200"]


def test_hpc_worker_setup(nomad_http):
    # --8<-- [start:hpc_worker]
    import os

    from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    # Construct the credential and client inside the worker process.
    def check_worker_access(endpoint):
        credential = BearerTokenCredential(
            os.environ["NOMAD_PAT"],
            endpoint=endpoint,
        )
        with NomadClient(
            credential=credential,
            enforced_scopes={Scope.USERS_READ},
            pool_limits=ConnectionLimits(max_connections=2, max_keepalive_connections=2),
            timeouts=NetworkTimeouts(pool=5, read=30),
        ) as client:
            return client.identity.me()

    endpoint = "prod"  # For an Oasis, use its full HTTPS API v1 URL.
    account = check_worker_access(endpoint)
    # --8<-- [end:hpc_worker]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http)
    assert nomad_http.client_options[0]["limits"].max_connections == 2


def test_dictionary_setup_and_local_discovery(nomad_http):
    # --8<-- [start:dictionary_setup]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    options = {
        "credential": BearerTokenCredential(os.environ["NOMAD_PAT"]),
        "enforced_scopes": {Scope.USERS_READ},
    }

    with NomadClient(**options) as client:
        # Inspect operation metadata locally before making the API call.
        info = client.identity.get_operation_info("me")
        print(info.description)
        print([scope.value for scope in info.required_scopes])
        print(client.enforced_scopes)
        account = client.identity.me()
    # --8<-- [end:dictionary_setup]

    assert info.required_scopes == {Scope.USERS_READ}
    assert account.user_id == "example-id"
    assert_account_request(nomad_http)


def test_inspect_and_read_account(nomad_http, capsys):
    # --8<-- [start:inspect_and_read_account]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential, enforced_scopes={Scope.USERS_READ}) as client:
        # Compare the client's policy with the operation's requirements.
        info = client.identity.get_operation_info("me")
        print("Enforced:", sorted(scope.value for scope in client.enforced_scopes or ()))
        print("Required:", sorted(scope.value for scope in info.required_scopes))

        account = client.identity.me()
        print("Account returned:", bool(account.user_id))
        print("Username available:", account.username is not None)
    # --8<-- [end:inspect_and_read_account]

    assert capsys.readouterr().out.splitlines() == [
        "Enforced: ['users:read']",
        "Required: ['users:read']",
        "Account returned: True",
        "Username available: True",
    ]
    assert_account_request(nomad_http)


@pytest.mark.parametrize("scenario", ["fixture", "custom_endpoint", "omitted", "empty", "invalid"])
def test_json_setup(nomad_http, tmp_path, monkeypatch, scenario):
    import json

    from nomad_python_api.exceptions import ScopeNotAllowedError

    settings_path = tmp_path / "nomad-settings.json"
    settings_text = _SETTINGS.read_text(encoding="utf-8")
    settings = json.loads(settings_text)
    assert set(settings) == {"enforced_scopes"}
    if scenario == "custom_endpoint":
        settings["endpoint"] = _DEV_API
    elif scenario == "omitted":
        settings.pop("enforced_scopes")
    elif scenario == "empty":
        settings["enforced_scopes"] = []
    elif scenario == "invalid":
        settings["enforced_scopes"] = ["unknown:read"]
    settings_path.write_text(settings_text if scenario == "fixture" else json.dumps(settings), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def use_json_settings():
        # --8<-- [start:json_setup]
        import json
        import os
        from pathlib import Path

        from nomad_python_api import NomadClient, Scope
        from nomad_python_api.identity import BearerTokenCredential

        settings = json.loads(Path("nomad-settings.json").read_text(encoding="utf-8"))
        endpoint = settings.get("endpoint", "prod")
        scope_names = settings.get("enforced_scopes")
        enforced_scopes = None if scope_names is None else {Scope(name) for name in scope_names}
        credential = BearerTokenCredential(os.environ["NOMAD_PAT"], endpoint=endpoint)

        with NomadClient(credential=credential, enforced_scopes=enforced_scopes) as client:
            account = client.identity.me()
        # --8<-- [end:json_setup]
        return account

    if scenario in {"empty", "invalid"}:
        with pytest.raises(ScopeNotAllowedError if scenario == "empty" else ValueError):
            use_json_settings()
        assert not nomad_http.requests
    else:
        assert use_json_settings().user_id == "example-id"
        assert_account_request(nomad_http, endpoint=settings.get("endpoint", _API))


def test_keycloak_setup(nomad_http, monkeypatch):
    monkeypatch.setenv("NOMAD_KEYCLOAK_ACCESS_TOKEN", _TOKEN)
    # --8<-- [start:keycloak_setup]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    # Use the access token obtained by your sign-in application.
    credential = BearerTokenCredential(os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"])
    with NomadClient(credential=credential) as client:
        account = client.identity.me()
    # --8<-- [end:keycloak_setup]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http)


def test_oasis_setup(nomad_http, monkeypatch):
    import ssl
    from unittest.mock import Mock

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    create_context = Mock(return_value=context)
    monkeypatch.setattr(ssl, "create_default_context", create_context)
    monkeypatch.setenv("OASIS_PAT", _TOKEN)
    # --8<-- [start:oasis_setup]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    endpoint = "https://oasis.example.org/nomad-oasis/api/v1"
    ca_bundle = "oasis-ca.pem"  # Use None when the API uses a publicly trusted CA.
    # Use a token issued by the same Oasis as the configured API URL.
    credential = BearerTokenCredential(os.environ["OASIS_PAT"], endpoint=endpoint)
    client = NomadClient(
        credential=credential,
        ca_bundle=ca_bundle,
    )
    try:
        account = client.identity.me()
    finally:
        client.close()
    # --8<-- [end:oasis_setup]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http, endpoint=endpoint)
    assert nomad_http.clients[0].is_closed
    create_context.assert_called_once_with(cafile="oasis-ca.pem")


@pytest.mark.parametrize("scenario, expected", [
    ("success", ""),
    ("401", "Check the token value"),
    ("403", "Check the token's NOMAD scopes"),
])
def test_error_recovery(nomad_http, scenario, expected, capsys):
    if scenario.isdigit():
        nomad_http.respond = lambda request: httpx.Response(int(scenario), text=_TOKEN)

    # --8<-- [start:error_recovery]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.exceptions import (
        AuthorizationError,
        ClientAuthenticationError,
        ScopeNotAllowedError,
    )
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"])
    with NomadClient(credential=credential, enforced_scopes={Scope.USERS_READ}) as client:
        # Report actionable errors without printing the token.
        try:
            account = client.identity.me()
        except ScopeNotAllowedError as error:
            missing = ", ".join(sorted(scope.value for scope in error.missing_scopes))
            print(f"This client blocks scopes required by {error.operation}: {missing}")
        except ClientAuthenticationError:
            print("Check the token value, expiration, and issuing deployment.")
        except AuthorizationError:
            print("Check the token's NOMAD scopes and resource access.")
    # --8<-- [end:error_recovery]
    assert len(nomad_http.requests) == 1
    output = capsys.readouterr().out
    assert output.startswith(expected)
    assert _TOKEN not in output
    if scenario == "success":
        assert account.user_id == "example-id"


def test_raw_rest_account(nomad_http):
    # --8<-- [start:rest_account]
    # Read the account directly with the same bearer authentication.
    import os

    import httpx

    base_url = "https://nomad-lab.eu/prod/v1/api/v1"
    with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False) as http:
        response = http.get(
            f"{base_url}/users/me",
            headers={"Authorization": f"Bearer {os.environ['NOMAD_PAT']}"},
        )
        response.raise_for_status()
        user = response.json()
    # --8<-- [end:rest_account]

    assert user["user_id"] == "example-id"
    assert_account_request(nomad_http)
