"""Pydantic domain models for the strategy layer (SPEC §3, Phases 1-2).

Phase 1 scope: ``Bar``. Phase 2 adds the signal/plan models: ``Direction``,
``Confidence``, ``GateResult``, ``Signal``, ``TradePlan``, ``NoTrade``.
"""

import math
from datetime import date as date_
from enum import StrEnum

from pydantic import BaseModel, model_validator


class Bar(BaseModel):
    """A single daily OHLCV bar.

    Validated so that malformed data never silently flows into indicators:
    ``high`` must be at least the max of open/close, ``low`` must be at
    most the min of open/close, and ``volume`` cannot be negative.
    """

    date: date_
    open: float
    high: float
    low: float
    close: float
    volume: int

    @model_validator(mode="after")
    def _check_ohlc_consistency(self) -> "Bar":
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"high ({self.high}) must be >= max(open, close) "
                f"({max(self.open, self.close)})"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"low ({self.low}) must be <= min(open, close) "
                f"({min(self.open, self.close)})"
            )
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        if self.volume < 0:
            raise ValueError(f"volume ({self.volume}) must be >= 0")
        return self


class Direction(StrEnum):
    """Trade direction (SPEC §5)."""

    LONG = "LONG"
    SHORT = "SHORT"


class Confidence(StrEnum):
    """Confidence label attached to a Signal (SPEC §5)."""

    HIGH = "HIGH"
    MODERATE = "MODERATE"


class GateResult(BaseModel):
    """Outcome of a single confluence-scoring gate (SPEC §5)."""

    name: str
    passed: bool
    detail: str


class Signal(BaseModel):
    """A directional confluence signal that cleared the scoring threshold.

    ``score`` is the count of passed gates out of 6; ``confidence`` reflects
    the SPEC §5 thresholds (LONG: 6/6 HIGH, 5/6 MODERATE; SHORT: 6/6 HIGH
    only).
    """

    direction: Direction
    score: int
    gates: list[GateResult]
    confidence: Confidence


def _is_finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0


class TradePlan(BaseModel):
    """A fully-specified trade suggestion (SPEC §4, §8 INV-1/INV-2).

    Every field required at construction -- there is no "plan without a
    stop" (INV-1). ``max_loss_usd`` is checked against the configured risk
    budget (INV-2), and entry/stop/take-profit are checked for basic
    geometric sanity given the direction.
    """

    target: str
    direction: Direction
    entry_low: float
    entry_high: float
    stop_loss: float
    take_profit: float
    size_units: float
    max_loss_usd: float
    capital: float
    risk_pct: float
    breakeven_move_note: str
    gates: list[GateResult]

    @model_validator(mode="after")
    def _check_finite_positive_fields(self) -> "TradePlan":
        for field_name in (
            "entry_low",
            "entry_high",
            "stop_loss",
            "take_profit",
            "size_units",
            "max_loss_usd",
            "capital",
        ):
            value = getattr(self, field_name)
            if not _is_finite_positive(value):
                raise ValueError(f"{field_name} must be a finite positive number, got {value!r}")
        if not (math.isfinite(self.risk_pct) and self.risk_pct > 0):
            raise ValueError(f"risk_pct must be a finite positive number, got {self.risk_pct!r}")
        return self

    @model_validator(mode="after")
    def _check_max_loss_within_risk_budget(self) -> "TradePlan":
        # INV-2, with a small tolerance for rounding.
        budget = self.capital * self.risk_pct * 1.02
        if self.max_loss_usd > budget:
            raise ValueError(
                f"max_loss_usd ({self.max_loss_usd}) exceeds risk budget "
                f"({budget}) = capital ({self.capital}) x risk_pct ({self.risk_pct}) x 1.02"
            )
        return self

    @model_validator(mode="after")
    def _check_geometry(self) -> "TradePlan":
        if self.direction is Direction.LONG:
            if not (self.stop_loss < self.entry_low <= self.entry_high < self.take_profit):
                raise ValueError(
                    "LONG geometry invalid: expected "
                    f"stop_loss ({self.stop_loss}) < entry_low ({self.entry_low}) "
                    f"<= entry_high ({self.entry_high}) < take_profit ({self.take_profit})"
                )
        else:
            if not (self.take_profit < self.entry_low <= self.entry_high < self.stop_loss):
                raise ValueError(
                    "SHORT geometry invalid: expected "
                    f"take_profit ({self.take_profit}) < entry_low ({self.entry_low}) "
                    f"<= entry_high ({self.entry_high}) < stop_loss ({self.stop_loss})"
                )
        return self


class NoTrade(BaseModel):
    """No-trade outcome: the concrete failed gate(s) that blocked a signal."""

    target: str
    reason: str
    gates: list[GateResult]
