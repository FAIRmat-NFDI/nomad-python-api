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
        allowed_scopes={Scope.USERS_READ},
    ) as client:
        account = client.identity.me()
    # --8<-- [end:named_setup]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http)


def test_configure_client_network_settings(nomad_http):
    # --8<-- [start:client_network_settings]
    import os

    from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient
    from nomad_python_api.identity import BearerTokenCredential

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

    endpoint = os.environ.get("NOMAD_API_URL", "prod")
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


@pytest.mark.parametrize("proxy", [None, "http://proxy.example.edu:8080"])
def test_borrow_a_custom_http_client(monkeypatch, caplog, proxy):
    import httpx as test_httpx

    monkeypatch.delenv("NOMAD_HTTPS_PROXY", raising=False)
    monkeypatch.setenv("NOMAD_API_URL", _DEV_API)
    if proxy is not None:
        monkeypatch.setenv("NOMAD_HTTPS_PROXY", proxy)
    caplog.set_level("INFO", logger="research.nomad")
    requests = []

    def respond(request):
        requests.append(request)
        return test_httpx.Response(200, json={"user_id": "example-id"})

    def create_client(**options):
        assert options.pop("proxy") == proxy
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

    credential = BearerTokenCredential(
        os.environ["NOMAD_PAT"],
        endpoint=os.environ.get("NOMAD_API_URL", "prod"),
    )
    with httpx.Client(
        proxy=os.environ.get("NOMAD_HTTPS_PROXY"),
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


@pytest.mark.parametrize("endpoint", [None, _DEV_API])
def test_hpc_worker_setup(monkeypatch, nomad_http, endpoint):
    monkeypatch.delenv("NOMAD_API_URL", raising=False)
    if endpoint is not None:
        monkeypatch.setenv("NOMAD_API_URL", endpoint)

    # --8<-- [start:hpc_worker]
    import os

    from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    def check_worker_access():
        credential = BearerTokenCredential(
            os.environ["NOMAD_PAT"],
            endpoint=os.environ.get("NOMAD_API_URL", "prod"),
        )
        with NomadClient(
            credential=credential,
            allowed_scopes={Scope.USERS_READ},
            pool_limits=ConnectionLimits(max_connections=2, max_keepalive_connections=2),
            timeouts=NetworkTimeouts(pool=5, read=30),
        ) as client:
            return client.identity.me()

    account = check_worker_access()
    # --8<-- [end:hpc_worker]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http, endpoint or _API)
    assert nomad_http.client_options[0]["limits"].max_connections == 2


def test_dictionary_setup_and_local_discovery(nomad_http):
    # --8<-- [start:dictionary_setup]
    import os

    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import BearerTokenCredential

    options = {
        "credential": BearerTokenCredential(os.environ["NOMAD_PAT"]),
        "allowed_scopes": {Scope.USERS_READ},
    }

    with NomadClient(**options) as client:
        info = client.identity.get_operation_info("me")
        print(info.description)
        print([scope.value for scope in info.required_scopes])
        print(client.allowed_scopes)
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
    with NomadClient(credential=credential, allowed_scopes={Scope.USERS_READ}) as client:
        info = client.identity.get_operation_info("me")
        print("Allowed:", sorted(scope.value for scope in client.allowed_scopes or ()))
        print("Required:", sorted(scope.value for scope in info.required_scopes))

        account = client.identity.me()
        print("Account returned:", bool(account.user_id))
        print("Username available:", account.username is not None)
    # --8<-- [end:inspect_and_read_account]

    assert capsys.readouterr().out.splitlines() == [
        "Allowed: ['users:read']",
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
    assert set(settings) == {"allowed_scopes"}
    if scenario == "custom_endpoint":
        settings["endpoint"] = _DEV_API
    elif scenario == "omitted":
        settings.pop("allowed_scopes")
    elif scenario == "empty":
        settings["allowed_scopes"] = []
    elif scenario == "invalid":
        settings["allowed_scopes"] = ["unknown:read"]
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
        scope_names = settings.get("allowed_scopes")
        allowed_scopes = None if scope_names is None else {Scope(name) for name in scope_names}
        credential = BearerTokenCredential(os.environ["NOMAD_PAT"], endpoint=endpoint)

        with NomadClient(credential=credential, allowed_scopes=allowed_scopes) as client:
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

    credential = BearerTokenCredential(os.environ["NOMAD_KEYCLOAK_ACCESS_TOKEN"])
    with NomadClient(credential=credential) as client:
        account = client.identity.me()
    # --8<-- [end:keycloak_setup]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http)


@pytest.mark.parametrize("with_private_ca", [False, True])
def test_oasis_setup(nomad_http, monkeypatch, tmp_path, with_private_ca):
    import ssl
    from unittest.mock import Mock

    ca_path = tmp_path / "oasis-ca.pem"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    create_context = Mock(return_value=context)
    monkeypatch.setattr(ssl, "create_default_context", create_context)
    monkeypatch.setenv("OASIS_PAT", _TOKEN)
    if with_private_ca:
        monkeypatch.setenv("NOMAD_CA_BUNDLE", str(ca_path))
    else:
        monkeypatch.delenv("NOMAD_CA_BUNDLE", raising=False)
    # --8<-- [start:oasis_setup]
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    endpoint = "https://oasis.example.org/nomad-oasis/api/v1"
    credential = BearerTokenCredential(os.environ["OASIS_PAT"], endpoint=endpoint)
    client = NomadClient(
        credential=credential,
        ca_bundle=os.environ.get("NOMAD_CA_BUNDLE"),
    )
    try:
        account = client.identity.me()
    finally:
        client.close()
    # --8<-- [end:oasis_setup]

    assert account.user_id == "example-id"
    assert_account_request(nomad_http, endpoint=endpoint)
    assert nomad_http.clients[0].is_closed
    if with_private_ca:
        create_context.assert_called_once_with(cafile=str(ca_path))
    else:
        create_context.assert_not_called()


@pytest.mark.parametrize("scenario, expected", [
    ("success", ""),
    ("blocked_scope", "This client blocks"),
    ("401", "Check the token value"),
    ("403", "Check the token's NOMAD scopes"),
])
def test_error_recovery(nomad_http, scenario, expected, capsys):
    import os

    from nomad_python_api import NomadClient
    from nomad_python_api.identity import BearerTokenCredential

    credential = BearerTokenCredential(os.environ["NOMAD_PAT"], endpoint="prod")
    allowed_scopes = set() if scenario == "blocked_scope" else None
    if scenario.isdigit():
        nomad_http.respond = lambda request: httpx.Response(int(scenario), text=_TOKEN)

    with NomadClient(credential=credential, allowed_scopes=allowed_scopes) as client:
        # --8<-- [start:error_recovery]
        from nomad_python_api.exceptions import (
            AuthorizationError,
            ClientAuthenticationError,
            ScopeNotAllowedError,
        )

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
    assert len(nomad_http.requests) == (0 if scenario == "blocked_scope" else 1)
    output = capsys.readouterr().out
    assert output.startswith(expected)
    assert _TOKEN not in output
    if scenario == "success":
        assert account.user_id == "example-id"


def test_raw_rest_account(nomad_http):
    # --8<-- [start:rest_account]
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
