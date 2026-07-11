"""Tests for Signal/TradePlan/NoTrade models and INV-1/INV-2 (SPEC §8, Phase 2)."""

import math

import pytest
from pydantic import ValidationError

from advisor.strategy.models import (
    Confidence,
    Direction,
    GateResult,
    NoTrade,
    Signal,
    TradePlan,
)

PASSING_GATES = [GateResult(name=f"gate{i}", passed=True, detail="ok") for i in range(6)]


def _long_plan(**overrides: object) -> dict:
    base = dict(
        target="SPY",
        direction=Direction.LONG,
        entry_low=566.0,
        entry_high=566.5,
        stop_loss=559.7,
        take_profit=575.45,
        size_units=15.873,
        max_loss_usd=99.98,
        capital=10_000.0,
        risk_pct=0.01,
        breakeven_move_note="move stop to breakeven (1R) at 572.3",
        gates=PASSING_GATES,
    )
    base.update(overrides)
    return base


def test_valid_long_trade_plan_constructs() -> None:
    plan = TradePlan(**_long_plan())
    assert plan.direction is Direction.LONG
    assert plan.stop_loss == pytest.approx(559.7)


def test_valid_short_trade_plan_constructs() -> None:
    plan = TradePlan(
        **_long_plan(
            direction=Direction.SHORT,
            entry_low=559.5,
            entry_high=560.0,
            stop_loss=566.3,
            take_profit=550.55,
        )
    )
    assert plan.direction is Direction.SHORT


@pytest.mark.parametrize("field", ["stop_loss", "take_profit", "size_units", "max_loss_usd"])
def test_trade_plan_missing_required_field_rejected(field: str) -> None:
    values = _long_plan()
    del values[field]
    with pytest.raises(ValidationError):
        TradePlan(**values)


@pytest.mark.parametrize("field", ["stop_loss", "take_profit", "size_units", "max_loss_usd"])
@pytest.mark.parametrize("bad_value", [math.inf, math.nan, 0.0, -1.0])
def test_trade_plan_non_finite_or_non_positive_field_rejected(field: str, bad_value: float) -> None:
    with pytest.raises(ValidationError):
        TradePlan(**_long_plan(**{field: bad_value}))


def test_inv2_max_loss_exceeding_risk_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        TradePlan(**_long_plan(max_loss_usd=500.0))  # far beyond 1% of $10,000


def test_inv2_max_loss_within_tolerance_accepted() -> None:
    # capital * risk_pct * 1.02 = 102.0; 101.5 is within tolerance.
    plan = TradePlan(**_long_plan(max_loss_usd=101.5))
    assert plan.max_loss_usd == pytest.approx(101.5)


def test_long_geometry_requires_stop_below_entry_below_take_profit() -> None:
    with pytest.raises(ValidationError):
        TradePlan(**_long_plan(stop_loss=570.0))  # stop above entry_low


def test_short_geometry_requires_take_profit_below_entry_below_stop() -> None:
    with pytest.raises(ValidationError):
        TradePlan(
            **_long_plan(
                direction=Direction.SHORT,
                entry_low=559.5,
                entry_high=560.0,
                stop_loss=550.0,  # stop below entry: invalid for SHORT
                take_profit=545.0,
            )
        )


def test_signal_holds_direction_score_and_confidence() -> None:
    signal = Signal(
        direction=Direction.LONG, score=6, gates=PASSING_GATES, confidence=Confidence.HIGH
    )
    assert signal.score == 6
    assert signal.confidence is Confidence.HIGH


def test_no_trade_holds_target_reason_and_gates() -> None:
    no_trade = NoTrade(target="QQQ", reason="downtrend (longs blocked)", gates=PASSING_GATES)
    assert no_trade.target == "QQQ"
    assert no_trade.reason == "downtrend (longs blocked)"
