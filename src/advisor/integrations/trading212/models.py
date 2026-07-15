"""Frozen typed models mapping Trading212's verified nested JSON shapes.

See the pipeline plan (t212-invest-readonly-adapter) § Verified API Contracts
for the source schema citations these mappings are derived from.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from advisor.integrations.trading212.errors import Trading212MalformedResponse


def _require_dict(raw: Any, what: str) -> dict:
    if not isinstance(raw, dict):
        raise Trading212MalformedResponse(f"expected object for {what}")
    return raw


def _build_or_malformed(model: type[BaseModel], **fields: object) -> Any:
    try:
        return model(**fields)
    except ValidationError as exc:
        raise Trading212MalformedResponse(f"malformed {model.__name__} payload") from exc


def _required_position_fields(instrument: dict, raw: dict) -> dict:
    return {
        "ticker": instrument.get("ticker"),
        "quantity": raw.get("quantity"),
        "average_price_paid": raw.get("averagePricePaid"),
        "current_price": raw.get("currentPrice"),
    }


def _optional_position_fields(raw: dict) -> dict:
    wallet_impact_raw = raw.get("walletImpact")
    wallet_impact = (
        {} if wallet_impact_raw is None else _require_dict(wallet_impact_raw, "walletImpact")
    )
    return {
        "unrealized_pl": wallet_impact.get("unrealizedProfitLoss"),
        "created_at": raw.get("createdAt"),
    }


def _position_fields(raw: dict) -> dict:
    instrument = _require_dict(raw.get("instrument"), "instrument")
    return {**_required_position_fields(instrument, raw), **_optional_position_fields(raw)}


def _required_account_summary_fields(cash: dict, raw: dict) -> dict:
    return {
        "total_value": raw.get("totalValue"),
        "cash_available_to_trade": cash.get("availableToTrade"),
    }


def _optional_account_summary_fields(cash: dict, raw: dict) -> dict:
    return {
        "currency": raw.get("currency"),
        "cash_reserved_for_orders": cash.get("reservedForOrders"),
        "cash_in_pies": cash.get("inPies"),
    }


def _account_summary_fields(raw: dict) -> dict:
    cash = _require_dict(raw.get("cash"), "cash")
    required = _required_account_summary_fields(cash, raw)
    return {**required, **_optional_account_summary_fields(cash, raw)}


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    quantity: float
    average_price_paid: float
    current_price: float
    unrealized_pl: float | None = None
    created_at: str | None = None

    @classmethod
    def from_api(cls, raw: dict) -> "Position":
        """Build a `Position` from one raw `/equity/portfolio` array element."""
        raw = _require_dict(raw, "position")
        return _build_or_malformed(cls, **_position_fields(raw))


class AccountSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_value: float
    cash_available_to_trade: float
    currency: str | None = None
    cash_reserved_for_orders: float | None = None
    cash_in_pies: float | None = None

    @classmethod
    def from_api(cls, raw: dict) -> "AccountSummary":
        """Build an `AccountSummary` from the raw `/equity/account/summary` object."""
        raw = _require_dict(raw, "account summary")
        return _build_or_malformed(cls, **_account_summary_fields(raw))
