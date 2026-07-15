"""Spec-blind black-box tests for the Trading212 read-only adapter.

Authored ONLY from pipeline-state/t212-invest-readonly-adapter/plan.md
(AC list + public Data Models signatures) and the package's own public
surface (`__init__.py` exports). No implementation source (client.py,
config.py, models.py, transport.py bodies) was read to author these tests
-- only the documented signatures in plan.md.

Focus areas (per orchestrator instruction):
  1. Credential fail-closed behaviour (load_credentials).
  2. Fail-closed status-code mapping (401/403/429/5xx/unmapped).
  3. Isolation guarantee (never a MarketDataProvider, no price methods).
"""
import json

import pytest

from advisor.integrations.trading212 import (
    AccountSummary,
    Position,
    Trading212AuthError,
    Trading212Client,
    Trading212Credentials,
    Trading212MalformedResponse,
    Trading212Unavailable,
    load_credentials,
)
from advisor.integrations.trading212.transport import HttpResponse

FIXTURES = "tests/fixtures/trading212"


def _read_fixture(name: str):
    with open(f"{FIXTURES}/{name}") as fh:
        return json.load(fh)


class StubTransport:
    """Minimal Transport implementation for client-level status tests."""

    def __init__(self, status: int, body: str):
        self._status = status
        self._body = body

    def get(self, path: str) -> HttpResponse:
        return HttpResponse(status=self._status, body=self._body)


# --- Credential fail-closed behaviour -------------------------------------


def test_missing_both_credentials_raises_auth_error():
    with pytest.raises(Trading212AuthError):
        load_credentials({})


def test_missing_secret_only_raises_auth_error():
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_KEY": "abc"})


def test_missing_key_only_raises_auth_error():
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_SECRET": "xyz"})


def test_empty_string_credential_raises_auth_error():
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_KEY": "", "T212_API_SECRET": "xyz"})


def test_whitespace_only_credential_raises_auth_error():
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_KEY": "   ", "T212_API_SECRET": "xyz"})


def test_valid_credentials_load_successfully():
    creds = load_credentials({"T212_API_KEY": "abc", "T212_API_SECRET": "xyz"})
    assert isinstance(creds, Trading212Credentials)


def test_credentials_repr_never_leaks_secret_values():
    creds = load_credentials(
        {"T212_API_KEY": "supersecretkey", "T212_API_SECRET": "supersecretpass"}
    )
    rendered = repr(creds) + str(creds)
    assert "supersecretkey" not in rendered
    assert "supersecretpass" not in rendered


# --- Fail-closed status-code mapping (client-level) -----------------------


@pytest.mark.parametrize("status", [401, 403])
def test_401_403_map_to_auth_error(status):
    client = Trading212Client(transport=StubTransport(status=status, body="{}"))
    with pytest.raises(Trading212AuthError):
        client.positions()


def test_429_maps_to_unavailable():
    client = Trading212Client(transport=StubTransport(status=429, body="{}"))
    with pytest.raises(Trading212Unavailable):
        client.positions()


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_maps_to_unavailable(status):
    client = Trading212Client(transport=StubTransport(status=status, body="{}"))
    with pytest.raises(Trading212Unavailable):
        client.account_summary()


@pytest.mark.parametrize("status", [418, 301, 999])
def test_unmapped_status_fails_closed_to_unavailable(status):
    client = Trading212Client(transport=StubTransport(status=status, body="{}"))
    with pytest.raises(Trading212Unavailable):
        client.positions()


def test_non_json_body_raises_malformed_not_unavailable():
    client = Trading212Client(transport=StubTransport(status=200, body="<html>oops</html>"))
    with pytest.raises(Trading212MalformedResponse):
        client.positions()


def test_client_error_reason_never_leaks_credentials():
    secret_marker = "leak-marker-secret-value"
    client = Trading212Client(
        transport=StubTransport(status=401, body=f"unauthorized {secret_marker}")
    )
    try:
        client.positions()
        pytest.fail("expected Trading212AuthError")
    except Trading212AuthError as exc:
        assert secret_marker not in str(exc)
        assert secret_marker not in str(exc.args)


# --- Positive path from verified fixtures ---------------------------------


def test_positions_returns_typed_list_from_verified_fixture():
    raw = _read_fixture("portfolio_ok.json")
    positions = [Position.from_api(item) for item in raw]
    assert all(isinstance(p, Position) for p in positions)
    by_ticker = {p.ticker: p for p in positions}
    assert by_ticker["AAPL_US_EQ"].quantity == 10.0


def test_positions_empty_portfolio_returns_empty_list():
    raw = _read_fixture("portfolio_empty.json")
    assert [Position.from_api(item) for item in raw] == []


def test_account_summary_maps_nested_cash_from_verified_fixture():
    raw = _read_fixture("account_summary_ok.json")
    summary = AccountSummary.from_api(raw)
    assert isinstance(summary, AccountSummary)
    assert summary.total_value == 12450.75
    assert summary.cash_available_to_trade == 3200.50


def test_malformed_portfolio_fixture_raises_malformed_response():
    raw = _read_fixture("portfolio_malformed.json")
    with pytest.raises(Trading212MalformedResponse):
        Position.from_api(raw[0])


def test_malformed_account_summary_fixture_raises_malformed_response():
    raw = _read_fixture("account_summary_malformed.json")
    with pytest.raises(Trading212MalformedResponse):
        AccountSummary.from_api(raw)


# --- Isolation guarantee ---------------------------------------------------


def test_client_is_never_a_market_data_provider():
    from advisor.datasource.base import MarketDataProvider

    assert not issubclass(Trading212Client, MarketDataProvider)


def test_client_defines_no_price_history_methods():
    for attr in ("daily_history", "spot"):
        assert not hasattr(Trading212Client, attr)


def test_position_and_account_summary_define_no_price_history_methods():
    for model in (Position, AccountSummary):
        for attr in ("daily_history", "spot"):
            assert not hasattr(model, attr)


def test_positions_are_frozen():
    raw = _read_fixture("portfolio_ok.json")
    position = Position.from_api(raw[0])
    with pytest.raises(Exception):
        position.quantity = 999.0
