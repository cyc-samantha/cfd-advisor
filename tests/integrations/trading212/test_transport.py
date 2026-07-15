"""Tests for UrllibTransport (slice-b-transport).

INV-5: no network anywhere here -- every call goes through an injected
`opener` stub, never the real `urllib.request.urlopen`.
"""

import base64
from urllib.error import HTTPError, URLError

import pytest

from advisor.integrations.trading212.errors import Trading212Unavailable
from advisor.integrations.trading212.transport import HttpResponse, UrllibTransport

# Synthetic test-only value, not a real credential: base64("test-fixture-key:test-fixture-secret").
AUTH_HEADER = "Basic " + base64.b64encode(b"test-fixture-key:test-fixture-secret").decode("ascii")


class _RecordingOpener:
    def __init__(self, body: str = "{}", status: int = 200) -> None:
        self.body = body
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, request, timeout):
        self.calls.append({"request": request, "timeout": timeout})
        return _FakeHttpHandle(self.body, self.status)


class _FakeHttpHandle:
    def __init__(self, body: str, status: int) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> "_FakeHttpHandle":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def close(self) -> None:
        return None


class _RaisingOpener:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, request, timeout):
        raise self._exc


class _HttpErrorOpener:
    def __init__(self, status: int, body: str = "error body") -> None:
        self._status = status
        self._body = body

    def __call__(self, request, timeout):
        raise HTTPError(
            url="https://demo.trading212.com/api/v0/equity/portfolio",
            code=self._status,
            msg="error",
            hdrs=None,
            fp=_FakeHttpHandle(self._body, self._status),
        )


def _transport(opener) -> UrllibTransport:
    return UrllibTransport(
        base_url="https://demo.trading212.com",
        authorization_header=AUTH_HEADER,
        opener=opener,
    )


def test_network_error_maps_to_unavailable() -> None:
    transport = _transport(_RaisingOpener(URLError("connection refused")))
    with pytest.raises(Trading212Unavailable):
        transport.get("/api/v0/equity/portfolio")


def test_timeout_error_maps_to_unavailable() -> None:
    transport = _transport(_RaisingOpener(TimeoutError("timed out")))
    with pytest.raises(Trading212Unavailable):
        transport.get("/api/v0/equity/portfolio")


def test_http_error_status_returned_not_raised() -> None:
    transport = _transport(_HttpErrorOpener(status=500))
    response = transport.get("/api/v0/equity/portfolio")
    assert isinstance(response, HttpResponse)
    assert response.status == 500


def test_get_sends_authorization_header() -> None:
    opener = _RecordingOpener()
    transport = _transport(opener)
    transport.get("/api/v0/equity/portfolio")
    sent_request = opener.calls[0]["request"]
    assert sent_request.get_header("Authorization") == AUTH_HEADER


def test_timeout_passed_to_opener() -> None:
    opener = _RecordingOpener()
    transport = UrllibTransport(
        base_url="https://demo.trading212.com",
        authorization_header=AUTH_HEADER,
        timeout=10.0,
        opener=opener,
    )
    transport.get("/api/v0/equity/portfolio")
    assert opener.calls[0]["timeout"] == 10.0


def test_transport_repr_and_str_omit_header() -> None:
    transport = _transport(_RecordingOpener())
    assert AUTH_HEADER not in repr(transport)
    assert AUTH_HEADER not in str(transport)
    assert "secret" not in repr(transport).lower()


def test_network_error_message_omits_header_and_secret() -> None:
    transport = _transport(_RaisingOpener(URLError("connection refused")))
    with pytest.raises(Trading212Unavailable) as exc_info:
        transport.get("/api/v0/equity/portfolio")
    assert AUTH_HEADER not in str(exc_info.value)
    assert AUTH_HEADER not in repr(exc_info.value.args)


def test_get_returns_response_body() -> None:
    opener = _RecordingOpener(body='{"ok": true}', status=200)
    transport = _transport(opener)
    response = transport.get("/api/v0/equity/portfolio")
    assert response.status == 200
    assert response.body == '{"ok": true}'
