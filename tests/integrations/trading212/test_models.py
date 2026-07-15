"""Tests for Trading212 typed response models (slice-a-foundation)."""

import pytest

from advisor.integrations.trading212.errors import Trading212MalformedResponse
from advisor.integrations.trading212.models import AccountSummary, Position

POSITION_PAYLOAD = {
    "quantity": 10.0,
    "averagePricePaid": 100.5,
    "currentPrice": 105.25,
    "instrument": {"ticker": "AAPL_US_EQ", "currency": "USD", "isin": "US0378331005"},
    "walletImpact": {"unrealizedProfitLoss": 47.5},
    "createdAt": "2026-01-02T10:00:00Z",
}

ACCOUNT_SUMMARY_PAYLOAD = {
    "totalValue": 10_000.0,
    "currency": "USD",
    "cash": {
        "availableToTrade": 2_500.0,
        "reservedForOrders": 100.0,
        "inPies": 500.0,
    },
}


def test_position_from_api_maps_verified_nested_payload() -> None:
    position = Position.from_api(POSITION_PAYLOAD)
    assert position.ticker == "AAPL_US_EQ"
    assert position.quantity == 10.0
    assert position.average_price_paid == 100.5
    assert position.current_price == 105.25
    assert position.unrealized_pl == 47.5
    assert position.created_at == "2026-01-02T10:00:00Z"


def test_account_summary_from_api_maps_nested_cash() -> None:
    summary = AccountSummary.from_api(ACCOUNT_SUMMARY_PAYLOAD)
    assert summary.total_value == 10_000.0
    assert summary.cash_available_to_trade == 2_500.0
    assert summary.currency == "USD"
    assert summary.cash_reserved_for_orders == 100.0
    assert summary.cash_in_pies == 500.0


def test_position_from_api_missing_required_nested_key_raises_malformed() -> None:
    payload = {
        "quantity": 10.0,
        "averagePricePaid": 100.5,
        "currentPrice": 105.25,
        "instrument": {"currency": "USD"},  # missing ticker
    }
    with pytest.raises(Trading212MalformedResponse):
        Position.from_api(payload)


def test_account_summary_from_api_missing_required_nested_key_raises_malformed() -> None:
    # missing required cash.availableToTrade
    payload = {"totalValue": 10_000.0, "cash": {"reservedForOrders": 100.0}}
    with pytest.raises(Trading212MalformedResponse):
        AccountSummary.from_api(payload)


def test_position_optional_fields_default_none_when_absent() -> None:
    payload = {
        "quantity": 10.0,
        "averagePricePaid": 100.5,
        "currentPrice": 105.25,
        "instrument": {"ticker": "AAPL_US_EQ"},
    }
    position = Position.from_api(payload)
    assert position.unrealized_pl is None
    assert position.created_at is None


def test_account_summary_optional_fields_default_none_when_absent() -> None:
    payload = {"totalValue": 10_000.0, "cash": {"availableToTrade": 2_500.0}}
    summary = AccountSummary.from_api(payload)
    assert summary.currency is None
    assert summary.cash_reserved_for_orders is None
    assert summary.cash_in_pies is None


def test_position_from_api_wrong_type_raises_malformed() -> None:
    payload = {
        "quantity": "not-a-number",
        "averagePricePaid": 100.5,
        "currentPrice": 105.25,
        "instrument": {"ticker": "AAPL_US_EQ"},
    }
    with pytest.raises(Trading212MalformedResponse):
        Position.from_api(payload)


def test_models_are_frozen() -> None:
    position = Position.from_api(
        {
            "quantity": 10.0,
            "averagePricePaid": 100.5,
            "currentPrice": 105.25,
            "instrument": {"ticker": "AAPL_US_EQ"},
        }
    )
    with pytest.raises(Exception):  # noqa: B017, PT011 - pydantic ValidationError on frozen model
        position.quantity = 20.0
