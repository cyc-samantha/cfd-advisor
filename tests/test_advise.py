"""Tests for advise() orchestration (SPEC §3/§6/§8 INV-3/INV-4, Phase 3)."""

from datetime import date, timedelta

import pytest

from advisor.advise import advise, build_provider
from advisor.analysis.events import EventCalendar, MacroEvent
from advisor.config import load_config
from advisor.datasource.base import CsvFixtureProvider, DataUnavailable, MarketDataProvider
from advisor.datasource.yfinance_provider import YFinanceProvider
from advisor.journal.store import JournalStore
from advisor.strategy.models import Bar, NoTrade, TradePlan

CONFIG = load_config()
CAPITAL = 10_000.0


class _FakeProvider(MarketDataProvider):
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        return self._bars

    def spot(self, ticker: str) -> float:
        return self._bars[-1].close


class _BrokenProvider(MarketDataProvider):
    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        raise DataUnavailable("fixture missing")

    def spot(self, ticker: str) -> float:
        raise DataUnavailable("fixture missing")


class _RaisingStore:
    def record(self, result, *, as_of, cfd_symbol):  # noqa: ANN001, ANN201
        raise RuntimeError("disk full")

    def open_exposure(self) -> tuple[int, float]:
        return (0, 0.0)


def _bar(d, o, h, low_, c, v=1_000_000) -> Bar:
    return Bar(date=d, open=o, high=max(h, o, c), low=min(low_, o, c), close=c, volume=v)


def _long_baseline_bars() -> list[Bar]:
    """220 all-pass-gate LONG bars (mirrors test_signal.py's baseline)."""
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
        bars[n - 1].date, prev_high + 0.1, final_close + 0.2, prev_high - 0.2, final_close, 1_500_000
    )
    return bars


def _clear_calendar(as_of: date) -> EventCalendar:
    future_event = MacroEvent(date=as_of + timedelta(days=30), type="FOMC", impact="high", note="")
    return EventCalendar(last_updated=as_of, events=[future_event])


def _stale_calendar(as_of: date) -> EventCalendar:
    past_event = MacroEvent(date=as_of - timedelta(days=30), type="FOMC", impact="high", note="")
    return EventCalendar(last_updated=as_of, events=[past_event])


def _blackout_calendar(as_of: date) -> EventCalendar:
    blocking_event = MacroEvent(date=as_of, type="CPI", impact="high", note="")
    return EventCalendar(last_updated=as_of, events=[blocking_event])


# --- data unavailable ---------------------------------------------------------


def test_advise_data_unavailable_returns_no_trade_and_journals() -> None:
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_BrokenProvider(),
        calendar=_clear_calendar(date(2026, 7, 15)),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
    )
    assert isinstance(result, NoTrade)
    assert "data unavailable" in result.reason
    assert len(store.list_suggestions()) == 1


# --- stale calendar ------------------------------------------------------------


def test_advise_stale_calendar_blocks_trade() -> None:
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_stale_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
    )
    assert isinstance(result, NoTrade)
    assert "stale" in result.reason


# --- blackout hard veto (AC 2) --------------------------------------------------


def test_advise_blackout_vetoes_even_when_signal_would_pass() -> None:
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_blackout_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
        open_positions=0,
        open_risk_pct=0.0,
    )
    assert isinstance(result, NoTrade)
    assert "CPI" in result.reason
    row = store.list_suggestions()[0]
    assert row["kind"] == "no_trade"


# --- clear conditions -> trade plan ----------------------------------------------


def test_advise_returns_trade_plan_when_clear_and_scored_high() -> None:
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_clear_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
        open_positions=0,
        open_risk_pct=0.0,
    )
    assert isinstance(result, TradePlan)
    row = store.list_suggestions()[0]
    assert row["kind"] == "trade"
    assert row["target"] == "SPY"


def test_advise_uses_explicit_open_positions_override_for_inv3() -> None:
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_clear_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
        open_positions=2,
        open_risk_pct=0.0,
    )
    assert isinstance(result, NoTrade)
    assert "limit" in result.reason


def test_advise_falls_back_to_store_open_exposure_when_not_given() -> None:
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_clear_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
    )
    assert isinstance(result, TradePlan)


# --- INV-4: journal-before-return is not bypassable on write failure -----------


def test_advise_propagates_when_journal_write_fails() -> None:
    bars = _long_baseline_bars()
    with pytest.raises(RuntimeError):
        advise(
            "SPY",
            provider=_FakeProvider(bars),
            calendar=_blackout_calendar(bars[-1].date),
            store=_RaisingStore(),
            config=CONFIG,
            capital=CAPITAL,
            open_positions=0,
            open_risk_pct=0.0,
        )


# --- build_provider --------------------------------------------------------------


def test_build_provider_offline_returns_fixture_provider() -> None:
    assert isinstance(build_provider(offline=True), CsvFixtureProvider)


def test_build_provider_online_returns_yfinance_provider() -> None:
    assert isinstance(build_provider(offline=False), YFinanceProvider)
