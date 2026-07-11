"""Stop placement, sizing, and R-multiple math (SPEC §5, §8 INV-3, Phase 2).

Pure functions -- no rounding is applied inside the risk math itself
(rounding for display belongs to the presentation layer, Phase 3); this
keeps ``max_loss`` algebraically equal to the requested risk budget rather
than drifting from it via premature rounding of ``size_units``.
"""

from advisor.analysis.indicators import atr, swing_high, swing_low
from advisor.strategy.models import Direction, NoTrade, Signal, TradePlan

BREAKEVEN_R_MULTIPLE = 1.0
ENTRY_ZONE_ATR_FRACTION = 0.25
STOP_ATR_MULTIPLE = 0.5


def place_stop(
    bars: list, direction: Direction, atr_value: float, swing_lookback: int = 10
) -> float:
    """Stop below the recent swing low (long) / above the swing high (short).

    The current (entry) bar is excluded from the pivot window -- see
    ``analysis.signal`` for the same convention applied to the room gate.
    """
    prior_bars = bars[:-1]
    if direction is Direction.LONG:
        return swing_low(prior_bars, swing_lookback) - STOP_ATR_MULTIPLE * atr_value
    return swing_high(prior_bars, swing_lookback) + STOP_ATR_MULTIPLE * atr_value


def position_size(capital: float, risk_pct: float, entry: float, stop: float) -> float:
    """Units to trade so a stop-out loses exactly ``capital * risk_pct``."""
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        raise ValueError(f"stop_distance must be positive, got {stop_distance}")
    risk_dollars = capital * risk_pct
    return risk_dollars / stop_distance


def take_profit(entry: float, stop: float, r_multiple: float) -> float:
    """Take-profit at ``r_multiple`` times the stop distance from entry."""
    stop_distance = abs(entry - stop)
    if entry >= stop:
        return entry + r_multiple * stop_distance
    return entry - r_multiple * stop_distance


def max_loss(size: float, entry: float, stop: float) -> float:
    """Dollar loss if stopped out at ``stop`` with position ``size``."""
    return size * abs(entry - stop)


def build_trade_plan(
    target: str,
    bars: list,
    signal: Signal,
    capital: float,
    risk_pct: float,
    tp_r_multiple: float,
    open_positions: int,
    open_risk_pct: float,
    swing_lookback: int = 10,
    atr_period: int = 14,
) -> TradePlan | NoTrade:
    """Build a TradePlan from a cleared Signal, or refuse per INV-3."""
    if open_positions >= 2 or open_risk_pct >= 0.02:
        return NoTrade(
            target=target,
            reason=(
                f"open position/risk limit reached "
                f"({open_positions} positions, {open_risk_pct:.1%} open risk)"
            ),
            gates=signal.gates,
        )

    atr_value = atr(bars, n=atr_period)[-1]
    last_close = bars[-1].close
    stop = place_stop(bars, signal.direction, atr_value, swing_lookback)
    size = position_size(capital, risk_pct, last_close, stop)
    tp = take_profit(last_close, stop, tp_r_multiple)
    loss = max_loss(size, last_close, stop)
    stop_distance = abs(last_close - stop)

    if signal.direction is Direction.LONG:
        entry_low, entry_high = last_close, last_close + ENTRY_ZONE_ATR_FRACTION * atr_value
        breakeven_price = last_close + BREAKEVEN_R_MULTIPLE * stop_distance
    else:
        entry_low, entry_high = last_close - ENTRY_ZONE_ATR_FRACTION * atr_value, last_close
        breakeven_price = last_close - BREAKEVEN_R_MULTIPLE * stop_distance

    return TradePlan(
        target=target,
        direction=signal.direction,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop,
        take_profit=tp,
        size_units=size,
        max_loss_usd=loss,
        capital=capital,
        risk_pct=risk_pct,
        breakeven_move_note=(
            f"move stop to breakeven ({BREAKEVEN_R_MULTIPLE:.0f}R) at {breakeven_price:.2f}"
        ),
        gates=signal.gates,
    )
