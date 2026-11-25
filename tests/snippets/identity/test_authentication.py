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
