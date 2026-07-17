"""Tests for advise() orchestration (SPEC §3/§6/§8 INV-3/INV-4, Phase 3)."""

from datetime import date, timedelta

import pytest

from advisor.advise import AdviseOptions, advise, build_provider
from advisor.analysis.events import EventCalendar, MacroEvent
from advisor.config import load_config
from advisor.datasource.base import CsvFixtureProvider, DataUnavailable, MarketDataProvider
from advisor.datasource.yfinance_provider import YFinanceProvider
from advisor.journal.store import JournalStore
from advisor.strategy.models import Bar, NoTrade, TradePlan
from conftest import qualifying_bars as _long_baseline_bars

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
    assert isinstance(result.plan, NoTrade)
    assert "data unavailable" in result.plan.reason
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
    assert isinstance(result.plan, NoTrade)
    assert "stale" in result.plan.reason


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
        options=AdviseOptions(open_positions=0, open_risk_pct=0.0),
    )
    assert isinstance(result.plan, NoTrade)
    assert "CPI" in result.plan.reason
    row = store.list_suggestions()[0]
    assert row["kind"] == "no_trade"


def test_advise_can_skip_calendar_blackout_when_explicitly_disabled() -> None:
    bars = _long_baseline_bars()
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_blackout_calendar(bars[-1].date),
        store=JournalStore(path=":memory:"),
        config=CONFIG,
        capital=CAPITAL,
        options=AdviseOptions(
            open_positions=0,
            open_risk_pct=0.0,
            calendar_check=False,
        ),
    )

    assert isinstance(result.plan, TradePlan)
    assert result.calendar_checked is False
    event_gate_result = next(gate for gate in result.plan.gates if gate.name == "event clear")
    assert event_gate_result.passed is True
    assert event_gate_result.detail == "calendar check disabled"


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
        options=AdviseOptions(open_positions=0, open_risk_pct=0.0),
    )
    assert isinstance(result.plan, TradePlan)
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
        options=AdviseOptions(open_positions=2, open_risk_pct=0.0),
    )
    assert isinstance(result.plan, NoTrade)
    assert "limit" in result.plan.reason


def test_advise_explicit_override_below_threshold_reaches_trade_plan() -> None:
    """A non-zero explicit override that is still below both INV-3 thresholds
    (1 position < 2, 1.9% risk < 2%) must size a plan, not just the all-zero
    case already covered elsewhere -- proves the override branch itself
    (not merely the store-fallback branch) can produce a TradePlan.
    """
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_clear_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
        options=AdviseOptions(open_positions=1, open_risk_pct=0.019),
    )
    assert isinstance(result.plan, TradePlan)


def test_advise_partial_options_falls_back_to_store_open_exposure() -> None:
    """Only one of open_positions/open_risk_pct set (bypassing the CLI's paired-flag
    guard, e.g. a direct library caller) is documented `advise()`-layer behaviour: it
    falls back to `store.open_exposure()` rather than raising -- the CLI/UI are
    responsible for rejecting a lone flag before calling `advise()` at all.
    """
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_clear_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
        options=AdviseOptions(open_positions=2),
    )
    assert isinstance(result.plan, TradePlan)


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
    assert isinstance(result.plan, TradePlan)


# --- as_of anchor: resolved value, not wall-clock date.today() -------------------


def test_advise_result_as_of_matches_last_bar_date_not_wall_clock() -> None:
    """The as_of used to journal/score must be the one callers render notes against.

    Regression guard: the fixture's last bar date and `date.today()` diverge in
    offline mode, so a caller anchoring a second artefact (e.g. the event/gap-risk
    note) to `date.today()` would be inconsistent with the analysed trade.
    """
    bars = _long_baseline_bars()
    store = JournalStore(path=":memory:")
    result = advise(
        "SPY",
        provider=_FakeProvider(bars),
        calendar=_clear_calendar(bars[-1].date),
        store=store,
        config=CONFIG,
        capital=CAPITAL,
        options=AdviseOptions(open_positions=0, open_risk_pct=0.0),
    )
    assert result.as_of == bars[-1].date
    assert result.as_of != date.today()


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
            options=AdviseOptions(open_positions=0, open_risk_pct=0.0),
        )


# --- build_provider --------------------------------------------------------------


def test_build_provider_offline_returns_fixture_provider() -> None:
    assert isinstance(build_provider(offline=True), CsvFixtureProvider)


def test_build_provider_online_returns_yfinance_provider() -> None:
    assert isinstance(build_provider(offline=False), YFinanceProvider)


# --- AdviseOptions is typed, not a **overrides dict --------------------------------


def test_advise_options_rejects_misspelled_field() -> None:
    with pytest.raises(TypeError):
        AdviseOptions(open_position=2)  # type: ignore[call-arg]
