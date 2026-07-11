"""Tests for pure technical indicators (SPEC §5, Phase 2)."""

import math
from datetime import date, timedelta

import pytest

from advisor.analysis.indicators import atr, atr_median, rsi, sma, swing_high, swing_low
from advisor.strategy.models import Bar


def _bars(highs, lows, closes, opens=None):
    opens = opens or closes
    start = date(2026, 1, 1)
    bars = []
    for i, (o, h, low_, c) in enumerate(zip(opens, highs, lows, closes, strict=True)):
        bars.append(
            Bar(
                date=start + timedelta(days=i),
                open=o,
                high=max(h, o, c),
                low=min(low_, o, c),
                close=c,
                volume=1_000,
            )
        )
    return bars


def test_sma_pads_with_nan_before_window_fills() -> None:
    result = sma([1.0, 2.0, 3.0, 4.0, 5.0], n=3)
    assert math.isnan(result[0])
    assert math.isnan(result[1])
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(3.0)
    assert result[4] == pytest.approx(4.0)


def test_sma_of_constant_series_equals_the_constant() -> None:
    result = sma([10.0] * 10, n=5)
    assert result[-1] == pytest.approx(10.0)


def test_rsi_all_gains_is_100() -> None:
    closes = [float(i) for i in range(1, 20)]  # strictly rising
    result = rsi(closes, n=14)
    assert result[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0() -> None:
    closes = [float(i) for i in range(20, 1, -1)]  # strictly falling
    result = rsi(closes, n=14)
    assert result[-1] == pytest.approx(0.0)


def test_rsi_pads_with_nan_before_period_elapses() -> None:
    closes = [float(i) for i in range(1, 10)]
    result = rsi(closes, n=14)
    assert all(math.isnan(value) for value in result)


def test_atr_of_flat_bars_with_no_gaps_equals_high_minus_low() -> None:
    highs = [110.0] * 20
    lows = [100.0] * 20
    closes = [105.0] * 20
    bars = _bars(highs, lows, closes)
    result = atr(bars, n=14)
    assert result[13] == pytest.approx(10.0)
    assert result[-1] == pytest.approx(10.0)


def test_atr_pads_with_nan_before_period_elapses() -> None:
    highs = [110.0] * 10
    lows = [100.0] * 10
    closes = [105.0] * 10
    bars = _bars(highs, lows, closes)
    result = atr(bars, n=14)
    assert all(math.isnan(value) for value in result)


def test_swing_low_returns_lowest_low_over_lookback() -> None:
    closes = [100.0] * 12
    highs = [105.0] * 12
    lows = [99.0] * 12
    lows[7] = 90.0  # the pivot low, within the last 10 bars
    bars = _bars(highs, lows, closes)
    assert swing_low(bars, lookback=10) == pytest.approx(90.0)


def test_swing_low_ignores_pivots_outside_lookback_window() -> None:
    closes = [100.0] * 12
    highs = [105.0] * 12
    lows = [99.0] * 12
    lows[0] = 50.0  # outside the last-10-bar lookback window
    bars = _bars(highs, lows, closes)
    assert swing_low(bars, lookback=10) == pytest.approx(99.0)


def test_swing_high_returns_highest_high_over_lookback() -> None:
    closes = [100.0] * 12
    highs = [105.0] * 12
    highs[9] = 130.0
    lows = [99.0] * 12
    bars = _bars(highs, lows, closes)
    assert swing_high(bars, lookback=10) == pytest.approx(130.0)


def test_atr_median_returns_median_of_atr_series() -> None:
    highs = [110.0] * 120
    lows = [100.0] * 120
    closes = [105.0] * 120
    bars = _bars(highs, lows, closes)
    assert atr_median(bars, window=100) == pytest.approx(10.0)
