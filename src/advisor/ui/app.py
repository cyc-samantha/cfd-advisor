"""Streamlit single-page UI (SPEC §3, §4, §7, §8 INV-5/INV-6, Phase 3).

Mirrors the CLI: both call the same ``advise()`` so there is exactly one
place the analysis/veto/sizing policy lives. Provider selection is gated on
``ADVISOR_OFFLINE`` (single seam) so ``AppTest`` never touches the network.
"""

import os
from dataclasses import dataclass

import streamlit as st

from advisor.advise import AdviseOptions, AdviseResult, advise, build_provider
from advisor.analysis.events import EventCalendar, holding_event_note, load_events
from advisor.config import AppConfig, load_config
from advisor.datasource.base import DataUnavailable
from advisor.journal.store import JournalStore
from advisor.render import DISCLAIMER, render_card
from advisor.strategy.models import Bar, TradePlan
from advisor.ui.chart import CHART_DAYS, candlestick_chart

DB_PATH = "data/advisor.sqlite"


def _is_offline() -> bool:
    return os.environ.get("ADVISOR_OFFLINE", "0") == "1"


@dataclass(frozen=True)
class _Inputs:
    target: str
    capital: float
    open_positions: int
    open_risk_pct: float


def _advise_options(inputs: _Inputs) -> AdviseOptions:
    return AdviseOptions(open_positions=inputs.open_positions, open_risk_pct=inputs.open_risk_pct)


def _run_advise(inputs: _Inputs, config: AppConfig, calendar: EventCalendar) -> AdviseResult:
    store = JournalStore(path=DB_PATH)
    provider = build_provider(offline=_is_offline())
    return advise(
        inputs.target, provider=provider, calendar=calendar, store=store,
        config=config, capital=inputs.capital, options=_advise_options(inputs),
    )


def _show_result(inputs: _Inputs, config: AppConfig, calendar: EventCalendar) -> None:
    result = _run_advise(inputs, config, calendar)
    is_trade = isinstance(result.plan, TradePlan)
    event_note = holding_event_note(result.as_of, calendar.events) if is_trade else None
    cfd_symbol = config.cfd_symbol_for(inputs.target)
    st.text(render_card(result.plan, cfd_symbol=cfd_symbol, event_note=event_note))


def _source_label() -> str:
    return "offline fixture (ADVISOR_OFFLINE=1)" if _is_offline() else "live yfinance"


def _render_chart_caption(target: str, latest: Bar) -> None:
    st.caption(
        f"{target} latest close {latest.close:.2f} on {latest.date.isoformat()} "
        f"— {_source_label()}"
    )


@st.cache_data(ttl=300)
def _cached_chart_bars(target: str, offline: bool) -> list[Bar]:
    """Cached fetch so widget-only reruns don't re-hit yfinance for the same target.

    A short TTL keeps "live" honest -- data goes stale for at most 5 minutes.
    """
    provider = build_provider(offline=offline)
    return provider.daily_history(target, days=CHART_DAYS)


def _fetch_chart_bars(target: str) -> list[Bar] | None:
    try:
        return _cached_chart_bars(target, _is_offline())
    except DataUnavailable as exc:
        st.warning(f"Chart unavailable for {target}: {exc.reason}")
        return None


def _render_chart(target: str) -> None:
    bars = _fetch_chart_bars(target)
    if bars is None:
        return
    _render_chart_caption(target, bars[-1])
    st.altair_chart(candlestick_chart(bars), width="stretch")


def _render_footer(calendar: EventCalendar) -> None:
    st.caption(f"Calendar last updated: {calendar.last_updated.isoformat()}")
    st.caption(DISCLAIMER)


def _render_inputs(config: AppConfig) -> _Inputs:
    target = st.selectbox("Target", [t.symbol for t in config.targets])
    capital = st.number_input("Account capital (USD)", value=float(config.capital_default))
    open_positions = st.number_input("Open positions (INV-3)", min_value=0, value=0, step=1)
    open_risk_pct = st.number_input("Open risk % (INV-3)", min_value=0.0, value=0.0, step=0.1) / 100
    return _Inputs(target, capital, open_positions, open_risk_pct)


def _render_page() -> None:
    config = load_config()
    calendar = load_events()
    inputs = _render_inputs(config)
    _render_chart(inputs.target)
    if st.button("Analyze"):
        _show_result(inputs, config, calendar)
    _render_footer(calendar)


_render_page()
