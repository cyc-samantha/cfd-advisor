"""Confluence scoring engine (SPEC §5, Phase 2).

Six binary gates decide LONG / SHORT / no-signal on daily bars. Gate 5
("event clear") is a seam for Phase 3's event-calendar check: callers may
pass an already-computed ``event_gate`` GateResult; absent that, a
placeholder gate that always passes is used so Phase 2 can be built and
tested without the event calendar.
"""

from pydantic import BaseModel

from advisor.analysis.indicators import atr, atr_median, rsi, sma, swing_high, swing_low
from advisor.strategy.models import Confidence, Direction, GateResult, Signal

_PLACEHOLDER_EVENT_GATE = GateResult(
    name="event clear",
    passed=True,
    detail="event check deferred to Phase 3",
)


class SignalConfig(BaseModel):
    """Thresholds and lookback windows for the six-gate scorer."""

    sma_pullback: int = 20
    sma_trend_fast: int = 50
    sma_trend_slow: int = 200
    rsi_period: int = 14
    rsi_threshold: float = 45.0
    atr_period: int = 14
    atr_median_window: int = 100
    atr_vol_multiplier: float = 1.5
    swing_lookback: int = 10
    room_r_multiple: float = 1.5
    allow_short: bool = True


def score_gates(
    bars: list,
    direction: Direction,
    config: SignalConfig,
    event_gate: GateResult | None = None,
) -> list[GateResult]:
    """Evaluate the six SPEC §5 gates for ``direction`` on ``bars``."""
    closes = [bar.close for bar in bars]
    sma_pullback = sma(closes, config.sma_pullback)
    sma_fast = sma(closes, config.sma_trend_fast)
    sma_slow = sma(closes, config.sma_trend_slow)
    rsi_series = rsi(closes, config.rsi_period)
    atr_series = atr(bars, config.atr_period)

    last_close = closes[-1]
    latest_sma_pullback = sma_pullback[-1]
    latest_sma_fast = sma_fast[-1]
    latest_sma_slow = sma_slow[-1]
    latest_atr = atr_series[-1]
    median_atr = atr_median(bars, config.atr_median_window)
    # Exclude the current (potential entry) bar from the pivot window: a
    # fresh breakout bar's own high/low is not "recent resistance/support",
    # it is the entry trigger itself (see gate 3 "turn").
    prior_bars = bars[:-1]
    high_swing = swing_high(prior_bars, config.swing_lookback)
    low_swing = swing_low(prior_bars, config.swing_lookback)

    is_long = direction is Direction.LONG

    gates = [
        _trend_gate(is_long, last_close, latest_sma_fast, latest_sma_slow),
        _pullback_gate(is_long, bars, latest_sma_pullback, rsi_series, config.rsi_threshold),
        _turn_gate(is_long, bars),
        _volatility_gate(latest_atr, median_atr, config.atr_vol_multiplier),
        event_gate if event_gate is not None else _PLACEHOLDER_EVENT_GATE,
        _room_gate(is_long, bars, last_close, latest_atr, high_swing, low_swing, config),
    ]
    return gates


def _trend_gate(
    is_long: bool, last_close: float, sma_fast: float, sma_slow: float
) -> GateResult:
    if is_long:
        passed = last_close > sma_slow and sma_fast > sma_slow
        detail = f"close ({last_close:.2f}) vs 200SMA ({sma_slow:.2f}), 50SMA vs 200SMA"
    else:
        passed = last_close < sma_slow and sma_fast < sma_slow
        detail = f"close ({last_close:.2f}) vs 200SMA ({sma_slow:.2f}), 50SMA vs 200SMA"
    return GateResult(name="trend", passed=passed, detail=detail)


def _pullback_gate(
    is_long: bool,
    bars: list,
    latest_sma_pullback: float,
    rsi_series: list[float],
    rsi_threshold: float,
) -> GateResult:
    recent_rsi = [value for value in rsi_series[-5:] if value == value]  # drop NaN
    if is_long:
        touched = min(bar.low for bar in bars[-3:]) <= latest_sma_pullback
        rsi_dipped = any(value < rsi_threshold for value in recent_rsi)
        passed = touched or rsi_dipped
        detail = (
            f"lows touched 20SMA ({latest_sma_pullback:.2f})={touched}, "
            f"RSI dipped below {rsi_threshold}={rsi_dipped}"
        )
    else:
        touched = max(bar.high for bar in bars[-3:]) >= latest_sma_pullback
        rsi_rose = any(value > (100 - rsi_threshold) for value in recent_rsi)
        passed = touched or rsi_rose
        detail = (
            f"highs touched 20SMA ({latest_sma_pullback:.2f})={touched}, "
            f"RSI rose above {100 - rsi_threshold}={rsi_rose}"
        )
    return GateResult(name="pullback", passed=passed, detail=detail)


def _turn_gate(is_long: bool, bars: list) -> GateResult:
    last, prev = bars[-1], bars[-2]
    if is_long:
        passed = last.close > prev.high
        detail = f"close ({last.close:.2f}) vs previous high ({prev.high:.2f})"
    else:
        passed = last.close < prev.low
        detail = f"close ({last.close:.2f}) vs previous low ({prev.low:.2f})"
    return GateResult(name="turn", passed=passed, detail=detail)


def _volatility_gate(latest_atr: float, median_atr: float, multiplier: float) -> GateResult:
    threshold = multiplier * median_atr
    passed = latest_atr < threshold
    detail = f"ATR ({latest_atr:.3f}) vs {multiplier}x median ATR ({threshold:.3f})"
    return GateResult(name="volatility", passed=passed, detail=detail)


def _room_gate(
    is_long: bool,
    bars: list,
    last_close: float,
    latest_atr: float,
    high_swing: float,
    low_swing: float,
    config: SignalConfig,
) -> GateResult:
    if is_long:
        stop = low_swing - 0.5 * latest_atr
        stop_distance = last_close - stop
        room = high_swing - last_close
    else:
        stop = high_swing + 0.5 * latest_atr
        stop_distance = stop - last_close
        room = last_close - low_swing
    required_room = config.room_r_multiple * stop_distance
    passed = room >= required_room
    detail = f"room to swing ({room:.2f}) vs {config.room_r_multiple}R ({required_room:.2f})"
    return GateResult(name="room", passed=passed, detail=detail)


def evaluate(
    bars: list,
    config: SignalConfig,
    event_gate: GateResult | None = None,
) -> Signal | None:
    """Score both directions and return the winning Signal, if any (SPEC §5).

    LONG wins at >=5/6 (6/6 HIGH, 5/6 MODERATE); SHORT only wins at 6/6 HIGH.
    LONG is checked first since its trend gate is mutually exclusive with
    SHORT's.
    """
    long_gates = score_gates(bars, Direction.LONG, config, event_gate)
    long_score = sum(gate.passed for gate in long_gates)
    if long_score == 6:
        return Signal(
            direction=Direction.LONG, score=6, gates=long_gates, confidence=Confidence.HIGH
        )
    if long_score == 5:
        return Signal(
            direction=Direction.LONG, score=5, gates=long_gates, confidence=Confidence.MODERATE
        )

    if config.allow_short:
        short_gates = score_gates(bars, Direction.SHORT, config, event_gate)
        short_score = sum(gate.passed for gate in short_gates)
        if short_score == 6:
            return Signal(
                direction=Direction.SHORT, score=6, gates=short_gates, confidence=Confidence.HIGH
            )

    return None
