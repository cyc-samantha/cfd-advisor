"""Table-driven tests for the six-gate confluence scorer (SPEC §5, Phase 2).

Each fixture is built from a clean uptrend/downtrend baseline where all six
gates pass; individual tests mutate exactly one structural feature to flip
exactly one gate (or, where a gate is mechanically coupled to another -- see
comments below -- the smallest set of gates the mutation actually touches).
"""

from datetime import date, timedelta

import pytest

from advisor.analysis.signal import SignalConfig, evaluate, score_gates
from advisor.strategy.models import Bar, Confidence, Direction, GateResult

CONFIG = SignalConfig()

_LONG_TAIL_OFFSETS = [0.5, 1.0, 4.0, 2.5, 1.0, 0.0, -1.5, -3.0, -3.8, -3.5, -3.0, -3.2, -2.8]
_SHORT_TAIL_OFFSETS = [-0.5, -1.0, -4.0, -2.5, -1.0, 0.0, 1.5, 3.0, 3.8, 3.5, 3.0, 3.2, 2.8]


def _bar(d, o, h, low_, c, v=1_000_000) -> Bar:
    return Bar(date=d, open=o, high=max(h, o, c), low=min(low_, o, c), close=c, volume=v)


def _apply_offsets(bars: list[Bar], start_index: int, base: float, offsets: list[float]) -> None:
    for j, off in enumerate(offsets):
        idx = start_index + j
        c = base + off
        bars[idx] = _bar(bars[idx].date, c - 0.15, c + 0.25, c - 0.3, c)


def _long_baseline() -> list[Bar]:
    """220 bars: clean uptrend, pullback to 20SMA, breakout, all 6 gates pass."""
    n = 220
    start = date(2025, 1, 1)
    closes = [400.0 + i * 0.8 for i in range(n)]
    bars = [
        _bar(start + timedelta(days=i), c - 0.1, c + 0.3, c - 0.4, c) for i, c in enumerate(closes)
    ]

    tail_start = n - 14
    _apply_offsets(bars, tail_start, closes[tail_start - 1], _LONG_TAIL_OFFSETS)

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


def _short_baseline() -> list[Bar]:
    """220 bars: clean downtrend, bounce to 20SMA, breakdown, all 6 gates pass."""
    n = 220
    start = date(2025, 1, 1)
    closes = [700.0 - i * 0.8 for i in range(n)]
    bars = [
        _bar(start + timedelta(days=i), c + 0.1, c + 0.4, c - 0.3, c) for i, c in enumerate(closes)
    ]

    tail_start = n - 14
    _apply_offsets(bars, tail_start, closes[tail_start - 1], _SHORT_TAIL_OFFSETS)

    prev_low = bars[n - 2].low
    final_close = prev_low - 0.5
    bars[n - 1] = _bar(
        bars[n - 1].date,
        prev_low - 0.1,
        prev_low + 0.2,
        final_close - 0.2,
        final_close,
        1_500_000,
    )
    return bars


def _gate(gates: list[GateResult], name: str) -> GateResult:
    return next(g for g in gates if g.name == name)


# --- All-pass baselines -----------------------------------------------------


def test_long_all_six_gates_pass_yields_high_confidence() -> None:
    bars = _long_baseline()
    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert all(g.passed for g in gates)
    signal = evaluate(bars, CONFIG)
    assert signal is not None
    assert signal.direction is Direction.LONG
    assert signal.score == 6
    assert signal.confidence is Confidence.HIGH


def test_short_all_six_gates_pass_yields_high_confidence() -> None:
    bars = _short_baseline()
    gates = score_gates(bars, Direction.SHORT, CONFIG)
    assert all(g.passed for g in gates)
    signal = evaluate(bars, CONFIG)
    assert signal is not None
    assert signal.direction is Direction.SHORT
    assert signal.score == 6
    assert signal.confidence is Confidence.HIGH


# --- Gate 1: trend -----------------------------------------------------------


def test_long_trend_gate_fails_when_price_below_flat_history() -> None:
    n_prefix = 206
    start = date(2025, 1, 1)
    flat_val = 700.0
    bars = [
        _bar(start + timedelta(days=i), flat_val - 0.1, flat_val + 0.3, flat_val - 0.4, flat_val)
        for i in range(n_prefix)
    ]
    for _ in range(14):
        bars.append(bars[-1])  # placeholder, overwritten by _apply_offsets below
    dates = [bars[n_prefix - 1].date + timedelta(days=j + 1) for j in range(14)]
    for j, d in enumerate(dates):
        bars[n_prefix + j] = _bar(d, flat_val, flat_val, flat_val, flat_val)
    _apply_offsets(bars, n_prefix, flat_val, _LONG_TAIL_OFFSETS)

    prev_high = bars[-2].high
    final_close = prev_high + 0.5
    bars[-1] = _bar(
        bars[-1].date, prev_high + 0.1, final_close + 0.2, prev_high - 0.2, final_close, 1_500_000
    )

    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert _gate(gates, "trend").passed is False
    signal = evaluate(bars, CONFIG)
    # Only the trend gate is broken here -- score is exactly 5, still MODERATE
    # per SPEC §5's literal threshold (>=5/6), even though trend failed.
    assert signal is not None
    assert signal.score == 5
    assert signal.confidence is Confidence.MODERATE


# --- Gate 2: pullback --------------------------------------------------------


def test_long_pullback_gate_fails_with_no_dip_before_breakout() -> None:
    n = 220
    start = date(2025, 1, 1)
    closes = [400.0 + i * 0.8 for i in range(n)]
    bars = [
        _bar(start + timedelta(days=i), c - 0.1, c + 0.3, c - 0.4, c) for i, c in enumerate(closes)
    ]
    monotonic_start = n - 5
    for j in range(monotonic_start, n - 1):
        c = closes[j] + 0.2
        bars[j] = _bar(bars[j].date, c - 0.1, c + 0.3, c - 0.4, c)
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

    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert _gate(gates, "pullback").passed is False
    assert evaluate(bars, CONFIG) is None


# --- Gate 3: turn -------------------------------------------------------------


def test_long_turn_gate_fails_when_close_does_not_clear_previous_high() -> None:
    bars = _long_baseline()
    prev_high = bars[-2].high
    final_close = prev_high - 1.0
    bars[-1] = _bar(
        bars[-1].date, prev_high - 0.5, prev_high - 0.2, prev_high - 1.3, final_close, 1_500_000
    )

    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert _gate(gates, "turn").passed is False
    signal = evaluate(bars, CONFIG)
    assert signal is not None
    assert signal.score == 5
    assert signal.confidence is Confidence.MODERATE


def test_short_turn_gate_fails_below_six_of_six_yields_no_signal() -> None:
    bars = _short_baseline()
    prev_low = bars[-2].low
    final_close = prev_low + 1.0
    bars[-1] = _bar(
        bars[-1].date, prev_low + 0.5, prev_low + 1.3, prev_low + 0.2, final_close, 1_500_000
    )

    gates = score_gates(bars, Direction.SHORT, CONFIG)
    assert _gate(gates, "turn").passed is False
    # SHORT requires 6/6 exactly: any single failed gate means no signal at all.
    assert evaluate(bars, CONFIG) is None


# --- Gate 4: volatility --------------------------------------------------------


def test_long_volatility_gate_fails_on_atr_spike() -> None:
    bars = _long_baseline()
    prev_high = bars[-2].high
    final_close = prev_high + 0.5
    bars[-1] = _bar(
        bars[-1].date, prev_high + 0.1, final_close + 15.0, prev_high - 15.0, final_close, 1_500_000
    )

    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert _gate(gates, "volatility").passed is False
    # The same ATR spike also widens the required room-to-swing threshold
    # (gate 6's stop distance is ATR-dependent), dropping the score to 4/6
    # here -- below even the LONG (>=5/6) threshold.
    assert evaluate(bars, CONFIG) is None


# --- Gate 5: event clear (Phase 3 seam) -----------------------------------------


def test_event_gate_placeholder_passes_when_not_supplied() -> None:
    bars = _long_baseline()
    gates = score_gates(bars, Direction.LONG, CONFIG)
    event_gate = _gate(gates, "event clear")
    assert event_gate.passed is True
    assert "Phase 3" in event_gate.detail


def test_event_gate_uses_supplied_gate_result_when_given() -> None:
    bars = _long_baseline()
    blackout = GateResult(name="event clear", passed=False, detail="FOMC tomorrow")
    gates = score_gates(bars, Direction.LONG, CONFIG, event_gate=blackout)
    assert _gate(gates, "event clear").passed is False
    signal = evaluate(bars, CONFIG, event_gate=blackout)
    assert signal is not None  # still 5/6 -> MODERATE
    assert signal.confidence is Confidence.MODERATE


# --- Gate 6: room --------------------------------------------------------------


def test_long_room_gate_fails_when_resistance_is_too_close() -> None:
    bars = _long_baseline()
    n = len(bars)
    idx = n - 11  # the bar that sets the recent swing high in the baseline
    old = bars[idx]
    new_close = old.close - 5.0
    bars[idx] = _bar(
        old.date, new_close - 0.15, new_close + 0.25, new_close - 0.3, new_close, old.volume
    )

    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert _gate(gates, "room").passed is False
    signal = evaluate(bars, CONFIG)
    assert signal is not None
    assert signal.score == 5
    assert signal.confidence is Confidence.MODERATE


# --- Confidence thresholds -----------------------------------------------------


def test_long_below_five_of_six_yields_no_signal() -> None:
    # Combine the pullback-break (no dip) fixture with a broken turn gate to
    # push the LONG score to 4/6, below the >=5/6 threshold.
    n = 220
    start = date(2025, 1, 1)
    closes = [400.0 + i * 0.8 for i in range(n)]
    bars = [
        _bar(start + timedelta(days=i), c - 0.1, c + 0.3, c - 0.4, c) for i, c in enumerate(closes)
    ]
    monotonic_start = n - 5
    for j in range(monotonic_start, n - 1):
        c = closes[j] + 0.2
        bars[j] = _bar(bars[j].date, c - 0.1, c + 0.3, c - 0.4, c)
    prev_high = bars[n - 2].high
    bars[n - 1] = _bar(
        bars[n - 1].date,
        prev_high - 0.5,
        prev_high - 0.2,
        prev_high - 1.3,
        prev_high - 1.0,
        1_500_000,
    )

    gates = score_gates(bars, Direction.LONG, CONFIG)
    score = sum(g.passed for g in gates)
    assert score <= 4
    assert evaluate(bars, CONFIG) is None


@pytest.mark.parametrize("score_threshold", [6, 5])
def test_long_score_at_or_above_threshold_always_yields_a_signal(score_threshold: int) -> None:
    bars = _long_baseline()
    if score_threshold == 5:
        prev_high = bars[-2].high
        final_close = prev_high - 1.0
        bars[-1] = _bar(
            bars[-1].date, prev_high - 0.5, prev_high - 0.2, prev_high - 1.3, final_close, 1_500_000
        )
    gates = score_gates(bars, Direction.LONG, CONFIG)
    assert sum(g.passed for g in gates) == score_threshold
    assert evaluate(bars, CONFIG) is not None
