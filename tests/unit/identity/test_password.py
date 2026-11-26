from concurrent.futures import ThreadPoolExecutor
from pickle import dumps
from threading import Barrier
from urllib.parse import parse_qs

import httpx
import pytest

from nomad_python_api import NomadClient
from nomad_python_api.exceptions import (
    ClientAuthenticationError,
    CredentialEndpointMismatchError,
    PasswordAuthenticationError,
    ScopeNotAllowedError,
)
from nomad_python_api.identity import PasswordCredential, _token

CENTRAL = "https://nomad-lab.eu/prod/v1/api/v1"
OASIS = "https://oasis.example.edu/nomad-oasis/api/v1"
USERNAME = "user+test@example.edu"
PASSWORD = " sample +/& password "


def token_response(access="example-access-token"):
    return httpx.Response(200, json={
        "access_token": access, "token_type": "Bearer", "expires_in": 120,
        "refresh_token": "example-unused-refresh-token",
    })


def test_explicit_password_credentials_target_central(nomad_http, monkeypatch):
    monkeypatch.setenv("NOMAD_USERNAME", "unused-env-user")
    monkeypatch.setenv("NOMAD_PASSWORD", "unused-env-password")
    credential = PasswordCredential(username=USERNAME, password=PASSWORD)

    def respond(request):
        if request.method == "POST":
            return token_response()
        return httpx.Response(200, json={"user_id": "account"})

    nomad_http.respond = respond
    with NomadClient(credential=credential) as client:
        assert not nomad_http.requests
        assert client.identity.me().user_id == "account"
        client.identity.me()
    exchange, *calls = nomad_http.requests
    assert str(exchange.url) == CENTRAL + "/auth/token"
    assert exchange.method == "POST"
    assert exchange.headers["content-type"] == "application/x-www-form-urlencoded"
    assert "Authorization" not in exchange.headers
    assert parse_qs(exchange.content.decode()) == {
        "grant_type": ["password"], "username": [USERNAME], "password": [PASSWORD],
    }
    assert len(calls) == 2
    for request in calls:
        assert str(request.url) == CENTRAL + "/users/me"
        assert request.headers["authorization"] == "Bearer example-access-token"
        assert not request.content
    assert all(client.is_closed for client in nomad_http.clients)


@pytest.mark.parametrize("username,password,env_user,env_password", [
    (USERNAME, None, USERNAME, PASSWORD), (None, PASSWORD, USERNAME, PASSWORD),
    (None, None, USERNAME, None), (None, None, None, PASSWORD), (USERNAME, "", None, None),
])
def test_incomplete_password_pairs_are_rejected(monkeypatch, username, password, env_user, env_password):
    for name, value in (("NOMAD_USERNAME", env_user), ("NOMAD_PASSWORD", env_password)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="Provide both") as caught:
        PasswordCredential(username=username, password=password)
    assert USERNAME not in str(caught.value) and PASSWORD not in str(caught.value)


def test_password_scope_and_deployment_checks_precede_login(nomad_http):
    credential = PasswordCredential(username=USERNAME, password=PASSWORD, endpoint=OASIS)
    with NomadClient(credential=credential, enforced_scopes=set()) as client:
        with pytest.raises(ScopeNotAllowedError):
            client.identity.me()
    with pytest.raises(CredentialEndpointMismatchError):
        credential._get_token(endpoint=CENTRAL, scopes=frozenset())
    assert not nomad_http.requests


def test_concurrent_password_acquisition_and_renewal_share_each_exchange(nomad_http, monkeypatch):
    now = 100.0
    monkeypatch.setattr(_token, "monotonic", lambda: now)
    replies = iter([token_response("access-first"), token_response("access-second")])
    nomad_http.respond = lambda request: next(replies)
    credential = PasswordCredential(username=USERNAME, password=PASSWORD, endpoint=OASIS)

    def call(_):
        ready.wait()
        return credential._get_token(endpoint=OASIS, scopes=frozenset())

    ready = Barrier(4, timeout=5)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(call, range(4))) == ["access-first"] * 4
        now += 89
        assert credential._get_token(endpoint=OASIS, scopes=frozenset()) == "access-first"
        now += 1
        assert list(pool.map(call, range(4))) == ["access-second"] * 4

    assert [str(request.url) for request in nomad_http.requests] == [OASIS + "/auth/token"] * 2
    assert all(parse_qs(request.content.decode())["grant_type"] == ["password"]
               for request in nomad_http.requests)


def test_rejected_password_stops_automatic_attempts_until_explicit_sign_in(nomad_http, caplog):
    credential = PasswordCredential(username=USERNAME, password=PASSWORD)
    nomad_http.respond = lambda request: httpx.Response(401, text=USERNAME + PASSWORD)
    with NomadClient(credential=credential) as client:
        for _ in range(2):
            with pytest.raises(PasswordAuthenticationError, match="rejected password") as caught:
                client.identity.me()
            assert caught.value.__context__ is None
            assert USERNAME not in str(caught.value) + repr(caught.value) + caplog.text
            assert PASSWORD not in str(caught.value) + repr(caught.value) + caplog.text
        assert len(nomad_http.requests) == 1

        nomad_http.respond = lambda request: (
            token_response() if request.method == "POST" else httpx.Response(401)
        )
        credential.authenticate()
        with pytest.raises(ClientAuthenticationError):
            client.identity.me()
    assert [item.method for item in nomad_http.requests] == ["POST", "POST", "GET"]
    assert USERNAME not in repr(credential) and PASSWORD not in repr(credential)
    with pytest.raises(TypeError, match="cannot be pickled"):
        dumps(credential)


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"access_token": "example-token", "token_type": "Bearer"}),
    httpx.Response(200, json={"access_token": "example-token", "token_type": "Bearer", "expires_in": -1}),
    httpx.Response(200, json={"access_token": "example-token", "token_type": "Bearer", "expires_in": True}),
    httpx.Response(200, json={"access_token": "bad token", "token_type": "Bearer", "expires_in": 30}),
    httpx.Response(200, content=b" " * (64 * 1024 + 1)),
    httpx.Response(200, headers={"Content-Encoding": "identity, gzip"}),
    httpx.Response(302, headers={"Location": "https://elsewhere.example.edu/auth/token"}),
    httpx.Response(404),
])
def test_invalid_password_exchange_stops_before_api_request(nomad_http, response):
    nomad_http.respond = lambda request: response
    credential = PasswordCredential(username=USERNAME, password=PASSWORD)
    with NomadClient(credential=credential) as client:
        with pytest.raises(PasswordAuthenticationError):
            client.identity.me()
    assert [str(item.url) for item in nomad_http.requests] == [CENTRAL + "/auth/token"]


def test_password_exchange_transport_error_drops_request_context(nomad_http):
    def timeout(request):
        raise httpx.ReadTimeout(PASSWORD, request=request)

    nomad_http.respond = timeout
    credential = PasswordCredential(username=USERNAME, password=PASSWORD)
    with pytest.raises(PasswordAuthenticationError, match="Could not reach") as caught:
        credential.authenticate()
    assert caught.value.__context__ is None
    assert PASSWORD not in str(caught.value)
