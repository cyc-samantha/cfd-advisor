"""Pure technical indicators over Bar series (SPEC §5, Phase 2).

All functions are stateless and side-effect free. ``sma``/``rsi``/``atr``
return full series aligned to the input length, padded with ``float("nan")``
wherever the window has not yet filled -- this lets callers inspect recent
history (e.g. "RSI dipped below 45 within the last 5 bars") rather than only
the latest value.
"""

import math
import statistics

from advisor.strategy.models import Bar


def sma(closes: list[float], n: int) -> list[float]:
    """Simple moving average of ``closes`` over a trailing window of ``n``."""
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    result: list[float] = []
    window_sum = 0.0
    for i, price in enumerate(closes):
        window_sum += price
        if i >= n:
            window_sum -= closes[i - n]
        if i < n - 1:
            result.append(math.nan)
        else:
            result.append(window_sum / n)
    return result


def rsi(closes: list[float], n: int = 14) -> list[float]:
    """Wilder's RSI(n) series, aligned to ``closes``.

    Uses Wilder's smoothing: the first average gain/loss is a simple mean of
    the first ``n`` deltas, and every subsequent average is smoothed as
    ``(prev_avg * (n - 1) + current) / n``.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    result: list[float] = [math.nan] * len(closes)
    if len(closes) <= n:
        return result

    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[1 : n + 1]) / n
    avg_loss = sum(losses[1 : n + 1]) / n
    result[n] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(n + 1, len(closes)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
        result[i] = _rsi_from_averages(avg_gain, avg_loss)

    return result


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def atr(bars: list[Bar], n: int = 14) -> list[float]:
    """Wilder's ATR(n) series, aligned to ``bars``."""
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    result: list[float] = [math.nan] * len(bars)
    if len(bars) < n:
        return result

    true_ranges = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        bar = bars[i]
        prev_close = bars[i - 1].close
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
        )

    avg_tr = sum(true_ranges[:n]) / n
    result[n - 1] = avg_tr
    for i in range(n, len(bars)):
        avg_tr = (avg_tr * (n - 1) + true_ranges[i]) / n
        result[i] = avg_tr

    return result


def swing_low(bars: list[Bar], lookback: int = 10) -> float:
    """Lowest low over the most recent ``lookback`` bars."""
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    if len(bars) < lookback:
        raise ValueError(f"need at least {lookback} bars, got {len(bars)}")
    return min(bar.low for bar in bars[-lookback:])


def swing_high(bars: list[Bar], lookback: int = 10) -> float:
    """Highest high over the most recent ``lookback`` bars."""
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    if len(bars) < lookback:
        raise ValueError(f"need at least {lookback} bars, got {len(bars)}")
    return max(bar.high for bar in bars[-lookback:])


def atr_median(bars: list[Bar], window: int = 100) -> float:
    """Median ATR(14) value over the trailing ``window`` bars.

    Used as the "normal volatility" baseline for the gate-4 vol-spike check.
    """
    if window <= 0:
        raise ValueError(f"window must be positive, got {window}")
    if len(bars) < window:
        raise ValueError(f"need at least {window} bars, got {len(bars)}")
    atr_series = atr(bars, n=14)
    recent = [value for value in atr_series[-window:] if not math.isnan(value)]
    if not recent:
        raise ValueError("not enough non-NaN ATR values to compute a median")
    return statistics.median(recent)
