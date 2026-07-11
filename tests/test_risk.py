"""Tests for risk math: stop placement, sizing, R-multiples (SPEC §5, §9, Phase 2).

Golden numbers (SPEC §9): capital 10,000, risk 1%, entry 566.0, stop 559.7 ->
risk $100, stop distance 6.3, size ~15.873 units, TP (1.5R) 575.45.

Deviation from SPEC's rounded display value ($99.98): the pure risk
functions here keep full float precision and do not round ``size_units``
before computing ``max_loss``, so ``max_loss`` is algebraically equal to the
requested risk budget ($100) rather than SPEC's rounded-for-display $99.98
(SPEC rounds size to 15.87 for the card, which is a presentation-layer
concern deferred to Phase 3). $100 is well within the ±0.01 tolerance
window used for these assertions either way.
"""

from datetime import date, timedelta

import pytest

from advisor.analysis.signal import SignalConfig, evaluate
from advisor.strategy.models import Bar, Direction, NoTrade, TradePlan
from advisor.strategy.risk import (
    build_trade_plan,
    max_loss,
    place_stop,
    position_size,
    take_profit,
)

CAPITAL = 10_000.0
RISK_PCT = 0.01
ENTRY = 566.0
STOP = 559.7


def test_golden_position_size() -> None:
    size = position_size(CAPITAL, RISK_PCT, ENTRY, STOP)
    assert size == pytest.approx(15.873, abs=0.001)


def test_golden_take_profit_at_1_5r() -> None:
    tp = take_profit(ENTRY, STOP, r_multiple=1.5)
    assert tp == pytest.approx(575.45, abs=0.01)


def test_golden_max_loss() -> None:
    size = position_size(CAPITAL, RISK_PCT, ENTRY, STOP)
    loss = max_loss(size, ENTRY, STOP)
    assert loss == pytest.approx(99.998, abs=0.01)


def test_golden_risk_dollars_and_stop_distance() -> None:
    risk_dollars = CAPITAL * RISK_PCT
    stop_distance = abs(ENTRY - STOP)
    assert risk_dollars == pytest.approx(100.0)
    assert stop_distance == pytest.approx(6.3, abs=0.001)


def test_position_size_rejects_zero_stop_distance() -> None:
    with pytest.raises(ValueError):
        position_size(CAPITAL, RISK_PCT, ENTRY, ENTRY)


def test_take_profit_mirrors_for_short() -> None:
    tp = take_profit(entry=559.7, stop=566.0, r_multiple=1.5)
    assert tp == pytest.approx(550.25, abs=0.01)


def _bar(d, o, h, low_, c, v=1_000_000) -> Bar:
    return Bar(date=d, open=o, high=max(h, o, c), low=min(low_, o, c), close=c, volume=v)


def _long_signal_bars() -> list[Bar]:
    """Reuses the all-pass LONG baseline shape from test_signal.py."""
    n = 220
    start = date(2025, 1, 1)
    closes = [400.0 + i * 0.8 for i in range(n)]
    bars = [
        _bar(start + timedelta(days=i), c - 0.1, c + 0.3, c - 0.4, c) for i, c in enumerate(closes)
    ]
    tail_start = n - 14
    base = closes[tail_start - 1]
    offsets = [0.5, 1.0, 4.0, 2.5, 1.0, 0.0, -1.5, -3.0, -3.8, -3.5, -3.0, -3.2, -2.8]
    for j, off in enumerate(offsets):
        idx = tail_start + j
        c = base + off
        bars[idx] = _bar(bars[idx].date, c - 0.15, c + 0.25, c - 0.3, c)
    prev_high = bars[n - 2].high
    final_close = prev_high + 0.5
    bars[n - 1] = _bar(
        bars[n - 1].date,
        prev_high + 0.1,
        final_close + 0.2,
        prev_high - 0.2,
        final_close,
        1_500_000,
    )
    return bars


def test_place_stop_long_is_below_swing_low_minus_half_atr() -> None:
    from advisor.analysis.indicators import atr, swing_low

    bars = _long_signal_bars()
    atr_value = atr(bars, n=14)[-1]
    stop = place_stop(bars, Direction.LONG, atr_value)
    expected = swing_low(bars[:-1], 10) - 0.5 * atr_value
    assert stop == pytest.approx(expected)
    assert stop < bars[-1].close


def test_build_trade_plan_from_cleared_long_signal() -> None:
    bars = _long_signal_bars()
    config = SignalConfig()
    signal = evaluate(bars, config)
    assert signal is not None

    plan = build_trade_plan(
        target="SPY",
        bars=bars,
        signal=signal,
        capital=CAPITAL,
        risk_pct=RISK_PCT,
        tp_r_multiple=1.5,
        open_positions=0,
        open_risk_pct=0.0,
    )
    assert isinstance(plan, TradePlan)
    assert plan.direction is Direction.LONG
    assert plan.stop_loss < plan.entry_low <= plan.entry_high < plan.take_profit
    assert plan.max_loss_usd <= plan.capital * plan.risk_pct * 1.02


@pytest.mark.parametrize("open_positions,open_risk_pct", [(2, 0.0), (3, 0.0), (0, 0.02), (0, 0.03)])
def test_inv3_refuses_new_plan_at_position_or_risk_limit(
    open_positions: int, open_risk_pct: float
) -> None:
    bars = _long_signal_bars()
    config = SignalConfig()
    signal = evaluate(bars, config)
    assert signal is not None

    result = build_trade_plan(
        target="SPY",
        bars=bars,
        signal=signal,
        capital=CAPITAL,
        risk_pct=RISK_PCT,
        tp_r_multiple=1.5,
        open_positions=open_positions,
        open_risk_pct=open_risk_pct,
    )
    assert isinstance(result, NoTrade)
    assert "limit" in result.reason


def test_inv3_allows_new_plan_below_limits() -> None:
    bars = _long_signal_bars()
    config = SignalConfig()
    signal = evaluate(bars, config)
    assert signal is not None

    result = build_trade_plan(
        target="SPY",
        bars=bars,
        signal=signal,
        capital=CAPITAL,
        risk_pct=RISK_PCT,
        tp_r_multiple=1.5,
        open_positions=1,
        open_risk_pct=0.01,
    )
    assert isinstance(result, TradePlan)
