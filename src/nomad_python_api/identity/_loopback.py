"""Receive one OAuth authorization response over the IPv4 loopback interface."""

import socket
import webbrowser
from collections.abc import Callable
from hmac import compare_digest
from threading import Event, Thread
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from ..exceptions import BrowserAuthenticationError
from ._credential import _is_token

_HOST = "127.0.0.1"
_MAX_HEADERS = 8192


def _open_browser(url: str, failed: Event) -> None:
    try:
        if webbrowser.open(url):
            return
    except Exception:
        # Browser launchers are platform-specific. Their errors can include the URL.
        pass
    failed.set()


def _read_headers(connection: socket.socket, deadline: float) -> bytes:
    headers = bytearray()
    deadline = min(deadline, monotonic() + 2)
    while b"\r\n\r\n" not in headers and len(headers) < _MAX_HEADERS:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        connection.settimeout(remaining)
        chunk = connection.recv(_MAX_HEADERS - len(headers))
        if not chunk:
            break
        headers.extend(chunk)
    head, separator, _ = headers.partition(b"\r\n\r\n")
    return bytes(head) if separator else b""


def _callback(
    headers: bytes, authority: str, path: str, state: str, issuer: str
) -> tuple[str | None, bool]:
    try:
        request, *fields = headers.decode("ascii").split("\r\n")
        method, target, version = request.split(" ")
        hosts = [
            value.strip()
            for name, _, value in (line.partition(":") for line in fields)
            if name.lower() == "host"
        ]
        if (method != "GET" or version not in ("HTTP/1.0", "HTTP/1.1")
                or hosts != [authority] or not _is_token(target)):
            return None, False
        parsed = urlsplit(target)
        if parsed.netloc or parsed.scheme or parsed.path != path or parsed.fragment:
            return None, False
        args = parse_qs(
            parsed.query, keep_blank_values=True, strict_parsing=True,
            errors="strict", max_num_fields=16,
        )
    except ValueError:
        return None, False
    states = args.get("state", [])
    if len(states) != 1 or not compare_digest(states[0].encode(), state.encode()):
        return None, False
    if "iss" in args and args["iss"] != [issuer]:
        return None, False
    if "error" in args:
        return None, "code" not in args and len(args["error"]) == 1 and bool(args["error"][0])
    codes = args.get("code", [])
    if len(codes) == 1 and _is_token(codes[0]):
        return codes[0], True
    return None, False


def _respond(connection: socket.socket, accepted: bool) -> None:
    status = b"200 OK" if accepted else b"400 Bad Request"
    body = (b"Sign-in response received. Return to Python." if accepted
            else b"Invalid sign-in response.")
    connection.settimeout(0.2)
    connection.sendall(
        b"HTTP/1.1 " + status + b"\r\nConnection: close\r\nCache-Control: no-store\r\n"
        b"Referrer-Policy: no-referrer\r\nContent-Type: text/plain; charset=utf-8\r\n"
        b"Content-Security-Policy: default-src 'none'\r\nContent-Length: "
        + str(len(body)).encode() + b"\r\n\r\n" + body
    )


def authorize(
    make_url: Callable[[str], str], *, port: int, path: str, state: str,
    issuer: str, timeout: float,
) -> tuple[str, str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind((_HOST, port))
            listener.listen(4)
            authority = f"{_HOST}:{listener.getsockname()[1]}"
            redirect_uri = f"http://{authority}{path}"
            failed = Event()
            deadline = monotonic() + timeout
            Thread(target=_open_browser, args=(make_url(redirect_uri), failed), daemon=True).start()
            while (remaining := deadline - monotonic()) > 0 and not failed.is_set():
                listener.settimeout(min(remaining, 0.2))
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    try:
                        headers = _read_headers(connection, deadline)
                    except OSError:
                        continue
                    code, accepted = _callback(headers, authority, path, state, issuer)
                    accepted = accepted and monotonic() < deadline
                    try:
                        _respond(connection, accepted)
                    except OSError:
                        pass
                    if accepted:
                        if code is None:
                            raise BrowserAuthenticationError("The identity provider declined sign-in.")
                        return code, redirect_uri
            if failed.is_set():
                raise BrowserAuthenticationError("Could not open a browser for NOMAD sign-in.")
            raise BrowserAuthenticationError("Timed out waiting for NOMAD browser sign-in.")
    except (OSError, RuntimeError):
        pass
    raise BrowserAuthenticationError("Could not start or use the browser sign-in callback listener.")
