from collections.abc import Callable

import httpx
import pytest


class MockNomad:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.clients: list[httpx.Client] = []
        self.client_options: list[dict[str, object]] = []
        self.respond: Callable[[httpx.Request], httpx.Response] = lambda request: httpx.Response(
            200, json={"user_id": "example-id", "username": "demo"}
        )

    def send(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)


@pytest.fixture
def nomad_http(monkeypatch: pytest.MonkeyPatch) -> MockNomad:
    nomad = MockNomad()
    original_client = httpx.Client

    def create_client(**options: object) -> httpx.Client:
        nomad.client_options.append(options)
        client = original_client(transport=httpx.MockTransport(nomad.send), **options)
        nomad.clients.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", create_client)
    return nomad


@pytest.fixture
def browser_sign_in(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from nomad_python_api.identity import _loopback

    urls: list[str] = []

    def authorize(make_url, *, port, path, state, issuer, timeout):
        redirect_uri = f"http://127.0.0.1:{port or 54321}{path}"
        urls.append(make_url(redirect_uri))
        return "example-code", redirect_uri

    monkeypatch.setattr(_loopback, "authorize", authorize)
    return urls
