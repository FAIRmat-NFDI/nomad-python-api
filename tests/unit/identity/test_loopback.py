from http.client import HTTPConnection
from threading import Event
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from nomad_python_api.exceptions import BrowserAuthenticationError
from nomad_python_api.identity import _loopback

ISSUER = "https://identity.example/realms/materials"
STATE = "example-state"


def test_loopback_accepts_only_matching_callback(monkeypatch):
    statuses = []
    redirects = []
    replies_read = Event()

    def open_browser(url):
        redirect = urlsplit(parse_qs(urlsplit(url).query)["redirect_uri"][0])
        redirects.append(redirect.geturl())
        for path, params, headers in [
            ("/other", {"code": "bad", "state": STATE}, {}),
            (redirect.path, {"code": "bad", "state": "wrong"}, {}),
            (redirect.path, {"code": "bad", "state": STATE}, {"Host": "other.example"}),
            (redirect.path, {"code": "bad", "state": STATE, "iss": ISSUER + "/other"}, {}),
            (redirect.path, {"code": "example-code", "state": STATE, "iss": ISSUER}, {}),
        ]:
            connection = HTTPConnection(redirect.hostname, redirect.port, timeout=2)
            try:
                connection.request("GET", path + "?" + urlencode(params), headers=headers)
                response = connection.getresponse()
                statuses.append((response.status, response.read(), response.headers["Cache-Control"]))
            finally:
                connection.close()
        replies_read.set()
        return True

    monkeypatch.setattr(_loopback.webbrowser, "open", open_browser)
    code, redirect_uri = _loopback.authorize(
        lambda uri: ISSUER + "/auth?" + urlencode({"redirect_uri": uri}),
        port=0, path="/callback", state=STATE, issuer=ISSUER, timeout=5,
    )
    assert replies_read.wait(2)
    parsed = urlsplit(redirect_uri)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=1)
    try:
        with pytest.raises(OSError):
            connection.connect()
    finally:
        connection.close()
    assert code == "example-code"
    assert redirects == [redirect_uri]
    assert redirect_uri.startswith("http://127.0.0.1:")
    assert statuses[:4] == [(400, b"Invalid sign-in response.", "no-store")] * 4
    assert statuses[-1] == (200, b"Sign-in response received. Return to Python.", "no-store")


@pytest.mark.parametrize("query", [
    "?code=a&state=example-state&state=extra",
    "?code=a&code=b&state=example-state",
    "?code=a&error=access_denied&state=example-state",
    "?code=&state=example-state",
    "?code=a&state=%FF",
])
def test_loopback_rejects_ambiguous_or_malformed_queries(query):
    head = f"GET /{query} HTTP/1.1\r\nHost: 127.0.0.1:54321".encode()
    assert _loopback._callback(head, "127.0.0.1:54321", "/", STATE, ISSUER) == (None, False)


def test_provider_denial_is_redacted(monkeypatch):
    def open_browser(callback):
        redirect = urlsplit(callback)
        connection = HTTPConnection(redirect.hostname, redirect.port, timeout=2)
        try:
            connection.request("GET", "/?state=example-state&error=access_denied&error_description=private")
            connection.getresponse().read()
        finally:
            connection.close()
        return True

    monkeypatch.setattr(_loopback.webbrowser, "open", open_browser)
    with pytest.raises(BrowserAuthenticationError, match="declined") as caught:
        _loopback.authorize(lambda uri: uri, port=0, path="/", state=STATE, issuer=ISSUER, timeout=3)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("browser_opened,expected", [(True, "Timed out"), (False, "Could not open")])
def test_loopback_closes_after_timeout_or_launch_failure(monkeypatch, browser_opened, expected):
    redirects = []

    def open_browser(uri):
        redirects.append(urlsplit(uri))
        return browser_opened

    monkeypatch.setattr(_loopback.webbrowser, "open", open_browser)
    with pytest.raises(BrowserAuthenticationError, match=expected):
        _loopback.authorize(lambda uri: uri, port=0, path="/", state=STATE, issuer=ISSUER, timeout=0.5)
    assert len(redirects) == 1
    connection = HTTPConnection(redirects[0].hostname, redirects[0].port, timeout=1)
    try:
        with pytest.raises(OSError):
            connection.connect()
    finally:
        connection.close()
