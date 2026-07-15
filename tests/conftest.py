"""Shared test helpers (SPEC Phase 3): bar construction, deduped across CLI/UI/advise tests."""

from datetime import date, timedelta

from advisor.strategy.models import Bar


def make_bar(d, o, h, low_, c, v=1_000_000) -> Bar:
    """Build one OHLCV Bar with high/low clamped to include open/close."""
    return Bar(date=d, open=o, high=max(h, o, c), low=min(low_, o, c), close=c, volume=v)


def qualifying_bars() -> list[Bar]:
    """220 all-pass-gate LONG bars (shared baseline for test_cli/test_ui/test_advise)."""
    n = 220
    start = date(2025, 1, 1)
    closes = [400.0 + i * 0.8 for i in range(n)]
    bars = [
        make_bar(start + timedelta(days=i), c - 0.1, c + 0.3, c - 0.4, c)
        for i, c in enumerate(closes)
    ]
    tail_start = n - 14
    base = closes[tail_start - 1]
    offsets = [0.5, 1.0, 4.0, 2.5, 1.0, 0.0, -1.5, -3.0, -3.8, -3.5, -3.0, -3.2, -2.8]
    for j, off in enumerate(offsets):
        idx = tail_start + j
        c = base + off
        bars[idx] = make_bar(bars[idx].date, c - 0.15, c + 0.25, c - 0.3, c)
    prev_high = bars[n - 2].high
    final_close = prev_high + 0.5
    bars[n - 1] = make_bar(
        bars[n - 1].date, prev_high + 0.1, final_close + 0.2, prev_high - 0.2,
        final_close, 1_500_000,
    )
    return bars
