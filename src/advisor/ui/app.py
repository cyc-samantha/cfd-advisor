"""Streamlit single-page UI (SPEC §3, §4, §7, §8 INV-5/INV-6, Phase 3).

Mirrors the CLI: both call the same ``advise()`` so there is exactly one
place the analysis/veto/sizing policy lives. Provider selection is gated on
``ADVISOR_OFFLINE`` (single seam) so ``AppTest`` never touches the network.
"""

import os

import streamlit as st

from advisor.advise import advise, build_provider
from advisor.analysis.events import EventCalendar, load_events
from advisor.config import AppConfig, load_config
from advisor.journal.store import JournalStore
from advisor.render import DISCLAIMER, render_card

DB_PATH = "data/advisor.sqlite"


def _is_offline() -> bool:
    return os.environ.get("ADVISOR_OFFLINE", "1") != "0"


def _cfd_symbol(config: AppConfig, target: str) -> str:
    return next((t.cfd_symbol for t in config.targets if t.symbol == target), target)


def _show_result(target: str, config: AppConfig, calendar: EventCalendar, capital: float) -> None:
    store = JournalStore(path=DB_PATH)
    provider = build_provider(offline=_is_offline())
    result = advise(
        target, provider=provider, calendar=calendar, store=store, config=config, capital=capital
    )
    st.text(render_card(result, cfd_symbol=_cfd_symbol(config, target)))


def _render_footer(calendar: EventCalendar) -> None:
    st.caption(f"Calendar last updated: {calendar.last_updated.isoformat()}")
    st.caption(DISCLAIMER)


def _render_inputs(config: AppConfig) -> tuple[str, float]:
    target = st.selectbox("Target", [t.symbol for t in config.targets])
    capital = st.number_input("Account capital (USD)", value=float(config.capital_default))
    return target, capital


def _render_page() -> None:
    config = load_config()
    calendar = load_events()
    target, capital = _render_inputs(config)
    if st.button("Analyze"):
        _show_result(target, config, calendar, capital)
    _render_footer(calendar)


_render_page()
