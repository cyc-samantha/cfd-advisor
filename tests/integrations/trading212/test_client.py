"""End-to-end tests for Trading212Client via a stub Transport (slice-c-client).

INV-5: no network here — every scenario is driven through `_StubTransport`,
never a real `UrllibTransport`/socket.
"""

import base64
import json
from pathlib import Path

import pytest

from advisor.integrations.trading212.client import Trading212Client
from advisor.integrations.trading212.errors import (
    Trading212AuthError,
    Trading212MalformedResponse,
    Trading212Unavailable,
)
from advisor.integrations.trading212.models import AccountSummary, Position
from advisor.integrations.trading212.transport import HttpResponse

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "trading212"
# Synthetic test-only value, not a real credential: base64("test-fixture-key:test-fixture-secret").
AUTH_HEADER = "Basic " + base64.b64encode(b"test-fixture-key:test-fixture-secret").decode("ascii")


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


class _StubTransport:
    def __init__(self, status: int, body: str) -> None:
        self._status = status
        self._body = body
        self.requested_paths: list[str] = []

    def get(self, path: str) -> HttpResponse:
        self.requested_paths.append(path)
        return HttpResponse(status=self._status, body=self._body)


def _client(status: int, body: str) -> Trading212Client:
    return Trading212Client(_StubTransport(status, body))


def test_positions_returns_typed_list_from_fixture() -> None:
    client = _client(200, _load_fixture("portfolio_ok.json"))
    positions = client.positions()
    assert len(positions) == 2
    assert all(isinstance(position, Position) for position in positions)
    assert positions[0].ticker == "AAPL_US_EQ"


def test_positions_empty_portfolio_returns_empty_list() -> None:
    client = _client(200, _load_fixture("portfolio_empty.json"))
    assert client.positions() == []


def test_account_summary_returns_typed_object() -> None:
    client = _client(200, _load_fixture("account_summary_ok.json"))
    summary = client.account_summary()
    assert isinstance(summary, AccountSummary)
    assert summary.total_value == 12450.75
    assert summary.cash_available_to_trade == 3200.50


def test_non_json_body_raises_malformed() -> None:
    client = _client(200, "<html>not json</html>")
    with pytest.raises(Trading212MalformedResponse):
        client.positions()


def test_malformed_fixture_raises_malformed() -> None:
    client = _client(200, _load_fixture("portfolio_malformed.json"))
    with pytest.raises(Trading212MalformedResponse):
        client.positions()


def test_malformed_account_summary_fixture_raises_malformed() -> None:
    client = _client(200, _load_fixture("account_summary_malformed.json"))
    with pytest.raises(Trading212MalformedResponse):
        client.account_summary()


@pytest.mark.parametrize("status", [401, 403])
def test_status_401_and_403_map_to_auth_error(status: int) -> None:
    client = _client(status, json.dumps({"reason": "unauthorized"}))
    with pytest.raises(Trading212AuthError):
        client.positions()


def test_status_429_maps_to_unavailable() -> None:
    client = _client(429, json.dumps({"reason": "rate limited"}))
    with pytest.raises(Trading212Unavailable):
        client.positions()


def test_status_500_maps_to_unavailable() -> None:
    client = _client(503, json.dumps({"reason": "server error"}))
    with pytest.raises(Trading212Unavailable):
        client.positions()


@pytest.mark.parametrize("status", [418, 301])
def test_unmapped_status_fails_closed_to_unavailable(status: int) -> None:
    client = _client(status, json.dumps({"reason": "unmapped"}))
    with pytest.raises(Trading212Unavailable):
        client.positions()


def test_client_error_paths_never_leak_credentials() -> None:
    client = _client(401, json.dumps({"authorization": AUTH_HEADER}))
    with pytest.raises(Trading212AuthError) as exc_info:
        client.positions()
    assert AUTH_HEADER not in str(exc_info.value)
    assert AUTH_HEADER not in repr(exc_info.value.args)


def test_client_repr_and_str_omit_credentials() -> None:
    client = _client(200, _load_fixture("portfolio_empty.json"))
    assert AUTH_HEADER not in repr(client)
    assert AUTH_HEADER not in str(client)
    assert "secret" not in repr(client).lower()


def test_client_positions_uses_expected_path() -> None:
    transport = _StubTransport(200, _load_fixture("portfolio_empty.json"))
    Trading212Client(transport).positions()
    assert transport.requested_paths == ["/api/v0/equity/portfolio"]


def test_client_account_summary_uses_expected_path() -> None:
    transport = _StubTransport(200, _load_fixture("account_summary_ok.json"))
    Trading212Client(transport).account_summary()
    assert transport.requested_paths == ["/api/v0/equity/account/summary"]


@pytest.mark.parametrize(
    "body",
    [
        json.dumps({"error": "not a list"}),
        json.dumps(5),
        json.dumps("scalar"),
    ],
)
def test_positions_wrong_top_level_container_raises_malformed(body: str) -> None:
    client = _client(200, body)
    with pytest.raises(Trading212MalformedResponse):
        client.positions()


@pytest.mark.parametrize(
    "body",
    [
        json.dumps([1, 2, 3]),
        json.dumps(5),
        json.dumps("scalar"),
    ],
)
def test_account_summary_wrong_top_level_container_raises_malformed(body: str) -> None:
    client = _client(200, body)
    with pytest.raises(Trading212MalformedResponse):
        client.account_summary()
