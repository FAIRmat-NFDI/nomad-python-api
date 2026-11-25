"""Offline identity and request-pipeline coverage."""

import pickle
import ssl
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import TIMEOUT_MAX, Event, Thread
from unittest.mock import Mock

import httpx
import pytest

from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient, NomadTransport, Scope
from nomad_python_api._core import _pipeline
from nomad_python_api.exceptions import (
    AuthorizationError,
    ClientAuthenticationError,
    CredentialEndpointMismatchError,
    HttpResponseError,
    InvalidResponseError,
    PoolTimeoutError,
    RateLimitError,
    ScopeNotAllowedError,
    TransportError,
)
from nomad_python_api.identity import Account, BearerTokenCredential

_PROD = "https://nomad-lab.eu/prod/v1/api/v1"
_TEST = "https://nomad-lab.eu/prod/v1/test/api/v1"
_TOKEN = "fake-secret-account-token"


def test_scope_snapshot_and_metadata(nomad_http, monkeypatch):
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    get_token = Mock(side_effect=AssertionError("unexpected credential access"))
    monkeypatch.setattr(credential, "_get_token", get_token)
    original_scopes = set()
    with NomadClient(credential=credential, allowed_scopes=original_scopes) as client:
        original_scopes.add(Scope.USERS_READ)
        assert client.allowed_scopes == frozenset()
        info = client.identity.get_operation_info("me")
        assert info.name == "identity.me"
        assert info.description
        assert info.required_scopes == {Scope.USERS_READ}
        with pytest.raises(KeyError):
            client.identity.get_operation_info("unknown")
        with pytest.raises(ScopeNotAllowedError) as caught:
            client.identity.me()
        assert caught.value.missing_scopes == info.required_scopes
        assert caught.value.operation == info.name
    get_token.assert_not_called()
    assert nomad_http.requests == []


def test_client_reuses_transport_and_closes_it(nomad_http):
    credential = BearerTokenCredential(_TOKEN, endpoint=f"{_PROD}/")
    with NomadClient(credential=credential) as client:
        assert nomad_http.requests == []
        assert client.allowed_scopes is None
        assert client.identity.me() == Account("example-id", "demo")
        assert client.identity.me() == Account("example-id", "demo")
    assert len(nomad_http.clients) == 1
    assert nomad_http.clients[0].is_closed
    assert len(nomad_http.requests) == 2
    request = nomad_http.requests[0]
    assert (request.method, str(request.url)) == ("GET", f"{_PROD}/users/me")
    assert request.headers["authorization"] == f"Bearer {_TOKEN}"
    assert request.content == b""
    with pytest.raises(RuntimeError, match="closed"):
        client.identity.me()


def test_untyped_scopes_and_unknown_keywords_fail_before_transport(nomad_http):
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    with pytest.raises(TypeError, match="Scope members"):
        NomadClient(credential=credential, allowed_scopes=[Scope.USERS_READ, "users:read"])
    with pytest.raises(TypeError, match="allowed_scope"):
        NomadClient(credential=credential, allowed_scope=set())
    with pytest.raises(TypeError, match="endpoint"):
        NomadClient(endpoint=_TEST, credential=credential)
    assert not nomad_http.clients


def test_client_uses_explicit_tls_and_safe_http_defaults(nomad_http, monkeypatch, tmp_path):
    ca_bundle = tmp_path / "ca.pem"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    create_context = Mock(return_value=context)
    monkeypatch.setattr(ssl, "create_default_context", create_context)
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    client = NomadClient(credential=credential, ca_bundle=ca_bundle)
    client.close()
    create_context.assert_called_once_with(cafile=str(ca_bundle))
    options = nomad_http.client_options[0]
    assert options["verify"] is context
    assert options["follow_redirects"] is False
    assert options["trust_env"] is False
    assert options["timeout"] == httpx.Timeout(connect=5, pool=10, read=10, write=10)
    assert options["limits"] == httpx.Limits(
        max_connections=10, max_keepalive_connections=5, keepalive_expiry=5,
    )
    assert nomad_http.clients[0].is_closed


def test_client_uses_explicit_pool_limits_and_timeouts(nomad_http):
    credential = BearerTokenCredential(_TOKEN)
    limits = ConnectionLimits(max_connections=2, max_keepalive_connections=3, keepalive_expiry=0)
    timeouts = NetworkTimeouts(**{"connect": 1, "pool": 2, "read": 3, "write": 4})
    with NomadClient(credential=credential, pool_limits=limits, timeouts=timeouts) as client:
        assert client.identity.me().user_id == "example-id"

    options = nomad_http.client_options[0]
    assert options["timeout"] == httpx.Timeout(connect=1, pool=2, read=3, write=4)
    assert options["limits"] == httpx.Limits(
        max_connections=2, max_keepalive_connections=2, keepalive_expiry=0,
    )


@pytest.mark.parametrize(("settings", "field", "value"), [
    (ConnectionLimits, "max_connections", 0),
    (ConnectionLimits, "max_connections", True),
    (ConnectionLimits, "max_keepalive_connections", -1),
    (ConnectionLimits, "max_keepalive_connections", 2.5),
    (ConnectionLimits, "keepalive_expiry", float("inf")),
    (NetworkTimeouts, "connect", float("nan")),
    (NetworkTimeouts, "pool", 0),
    (NetworkTimeouts, "pool", TIMEOUT_MAX * 2),
    (NetworkTimeouts, "read", "10"),
    (NetworkTimeouts, "write", -1),
])
def test_invalid_network_settings(settings, field, value):
    with pytest.raises(ValueError, match=field):
        settings(**{field: value})


def test_invalid_network_setting_types_fail_before_transport(nomad_http):
    credential = BearerTokenCredential(_TOKEN)
    with pytest.raises(TypeError, match="ConnectionLimits"):
        NomadClient(credential=credential, pool_limits={})
    with pytest.raises(TypeError, match="NetworkTimeouts"):
        NomadClient(credential=credential, timeouts={})
    assert not nomad_http.clients


@pytest.mark.parametrize("share_pool", [False, True])
def test_saturated_pool_times_out_before_sending_a_request(monkeypatch, share_pool):
    request_started = Event()
    release_request = Event()
    received_paths = []
    body = b'{"user_id":"example-id"}'

    class AccountHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            received_paths.append(self.path)
            request_started.set()
            if not release_request.wait(timeout=10):
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), AccountHandler) as server:
        # Exercise real HTTPX pooling against plaintext loopback using a test-only token.
        endpoint = f"http://127.0.0.1:{server.server_port}/api/v1"
        credential = BearerTokenCredential(_TOKEN)
        monkeypatch.setattr(credential, "_endpoint", endpoint)
        monkeypatch.setattr(_pipeline, "normalize_endpoint", lambda _: endpoint)
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.start()
        try:
            with ExitStack() as stack:
                limits = ConnectionLimits(max_connections=1)
                timeouts = NetworkTimeouts(pool=0.25)
                if share_pool:
                    transport = stack.enter_context(NomadTransport(pool_limits=limits))
                    client = stack.enter_context(NomadClient(
                        credential=credential, transport=transport, timeouts=timeouts,
                    ))
                    second = stack.enter_context(NomadClient(
                        credential=credential, transport=transport, timeouts=timeouts,
                    ))
                else:
                    client = second = stack.enter_context(NomadClient(
                        credential=credential, pool_limits=limits, timeouts=timeouts,
                    ))
                executor = stack.enter_context(ThreadPoolExecutor(max_workers=1))
                first = executor.submit(client.identity.me)
                try:
                    assert request_started.wait(timeout=5)
                    with pytest.raises(PoolTimeoutError, match="before sending") as caught:
                        second.identity.me()
                    assert isinstance(caught.value, TransportError)
                    assert caught.value.__context__ is None
                    assert received_paths == ["/api/v1/users/me"]
                finally:
                    release_request.set()
                assert first.result(timeout=5).user_id == "example-id"
                if share_pool:
                    client.close()
                assert second.identity.me().user_id == "example-id"
                assert received_paths == ["/api/v1/users/me"] * 2
        finally:
            server.shutdown()
            thread.join()


def test_injected_http_client_keeps_ownership_and_nomad_request_rules():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/"})

    credential = BearerTokenCredential(_TOKEN)
    with httpx.Client(
        transport=httpx.MockTransport(respond),
        auth=("wrong-user", "wrong-password"),
        headers={"Host": "other.example"},
        params={"page_size": 20},
        follow_redirects=True,
    ) as external:
        with NomadClient(credential=credential, http_client=external) as client:
            with pytest.raises(HttpResponseError) as caught:
                client.identity.me()
            assert caught.value.status_code == 302
        assert not external.is_closed
        with pytest.raises(RuntimeError, match="closed"):
            client.identity.me()

    assert len(requests) == 1
    assert str(requests[0].url) == f"{_PROD}/users/me"
    assert requests[0].headers["Host"] == "nomad-lab.eu"
    assert requests[0].headers["Authorization"] == f"Bearer {_TOKEN}"


@pytest.mark.parametrize("hook_error", [RuntimeError, httpx.PoolTimeout, httpx.HTTPStatusError])
def test_response_hook_failures_report_unknown_request_outcome(hook_error):
    requests = []

    def respond(request):
        requests.append(request)
        status = 503 if hook_error is httpx.HTTPStatusError else 200
        return httpx.Response(status)

    def inspect_response(response):
        if hook_error is httpx.HTTPStatusError:
            response.raise_for_status()
        raise hook_error(_TOKEN)

    with httpx.Client(
        transport=httpx.MockTransport(respond),
        event_hooks={"response": [inspect_response]},
    ) as external:
        with NomadClient(credential=BearerTokenCredential(_TOKEN), http_client=external) as client:
            with pytest.raises(TransportError, match="may have reached NOMAD") as caught:
                client.identity.me()

    assert type(caught.value) is TransportError
    assert caught.value.__context__ is None
    assert _TOKEN not in str(caught.value)
    assert len(requests) == 1


def test_injected_transport_options_fail_before_a_request():
    credential = BearerTokenCredential(_TOKEN)
    with NomadTransport() as transport, httpx.Client() as external:
        with pytest.raises(ValueError, match="http_client supplies"):
            NomadClient(credential=credential, http_client=external, transport=transport)
        with pytest.raises(ValueError, match="http_client supplies"):
            NomadClient(credential=credential, http_client=external, timeouts=NetworkTimeouts())
        with pytest.raises(ValueError, match="Configure CA trust and pool limits"):
            NomadClient(credential=credential, transport=transport, pool_limits=ConnectionLimits())
    with pytest.raises(ValueError, match="transport is closed"):
        NomadClient(credential=credential, transport=transport)
    with pytest.raises(ValueError, match="http_client is closed"):
        NomadClient(credential=credential, http_client=external)


def test_rejects_credential_on_same_host_different_deployment(nomad_http):
    credential = BearerTokenCredential(_TOKEN)
    with pytest.raises(CredentialEndpointMismatchError):
        credential._get_token(endpoint=_TEST, scopes=frozenset())
    assert nomad_http.requests == []


@pytest.mark.parametrize("endpoint", [
    "http://oasis.example.org/api/v1",
    "https://user:secret@oasis.example.org/api/v1",
    "https://oasis.example.org/api/v1?token=secret",
    "https://oasis.example.org/api/v1#secret",
    "https://oasis.example.org/sub/../api/v1",
    "https://oasis.example.org/%2e%2e/api/v1",
    "https://oasis.example.org:0/api/v1",
    "https://oasis.example.org:65536/api/v1",
])
def test_invalid_endpoint_does_not_expose_input(endpoint):
    with pytest.raises(ValueError) as caught:
        BearerTokenCredential(_TOKEN, endpoint=endpoint)
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("token", ["", "Bearer test", "token\r\nInjected: 1", "nonascii-\u00e9"])
def test_invalid_bearer_tokens_are_rejected(token):
    with pytest.raises(ValueError, match="bearer token"):
        BearerTokenCredential(token, endpoint="prod")


@pytest.mark.parametrize("status, error", [
    (302, HttpResponseError),
    (401, ClientAuthenticationError),
    (403, AuthorizationError),
    (429, RateLimitError),
    (500, HttpResponseError),
])
def test_http_errors_never_replay_or_leak_server_payload(nomad_http, caplog, status, error):
    nomad_http.respond = lambda request: httpx.Response(
        status, text=_TOKEN, headers={"Location": "https://other.example.org/api/v1"}
    )
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    with NomadClient(credential=credential) as client:
        with pytest.raises(error) as caught:
            client.identity.me()
    assert caught.value.status_code == status
    assert caught.value.operation == "identity.me"
    assert _TOKEN not in str(caught.value) + repr(caught.value) + caplog.text
    assert len(nomad_http.requests) == 1
    assert str(nomad_http.requests[0].url) == f"{_PROD}/users/me"


@pytest.mark.parametrize("content", [
    b"not-json",
    b"[]",
    b'{"user_id": 17}',
    b'{"user_id":"example","username":32}',
    b" " * (256 * 1024 + 1),
])
def test_invalid_account_response(nomad_http, content):
    nomad_http.respond = lambda request: httpx.Response(200, content=content)
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    with NomadClient(credential=credential) as client:
        with pytest.raises(InvalidResponseError):
            client.identity.me()
    assert len(nomad_http.requests) == 1


def test_does_not_read_a_compressed_account_response(nomad_http):
    class UnreadableBody(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("Unexpected read of compressed payload")

    nomad_http.respond = lambda request: httpx.Response(
        200, headers={"Content-Encoding": "gzip"}, stream=UnreadableBody()
    )
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    with NomadClient(credential=credential) as client:
        with pytest.raises(InvalidResponseError, match="content encoding"):
            client.identity.me()
    assert nomad_http.requests[0].headers["accept-encoding"] == "identity"


def test_timeout_does_not_retry_or_expose_transport_error(nomad_http):
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(_TOKEN, request=request)

    nomad_http.respond = timeout
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    with NomadClient(credential=credential) as client:
        with pytest.raises(TransportError, match="timeout") as caught:
            client.identity.me()
    assert caught.value.__context__ is None
    assert _TOKEN not in str(caught.value)
    assert len(nomad_http.requests) == 1


def test_secret_objects_do_not_display_or_serialize_credentials(nomad_http):
    credential = BearerTokenCredential(_TOKEN, endpoint="prod")
    with NomadClient(credential=credential) as client:
        assert _TOKEN not in repr(credential) + repr(client)
        for value in (credential, client):
            with pytest.raises(TypeError, match="cannot be pickled"):
                pickle.dumps(value)
    assert "private-account-id" not in repr(Account("private-account-id"))
