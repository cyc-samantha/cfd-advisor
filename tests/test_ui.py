"""Smoke tests for the Streamlit single-page UI (SPEC §4, §8 INV-5, Phase 3)."""

import os
from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

import advisor.datasource.base as ds_base
from advisor.render import DISCLAIMER
from advisor.strategy.models import Bar

APP_PATH = "src/advisor/ui/app.py"


def _offline_app() -> AppTest:
    os.environ["ADVISOR_OFFLINE"] = "1"
    return AppTest.from_file(APP_PATH)


def _bar(d, o, h, low_, c, v=1_000_000) -> Bar:
    return Bar(date=d, open=o, high=max(h, o, c), low=min(low_, o, c), close=c, volume=v)


def _qualifying_bars() -> list[Bar]:
    """220 all-pass-gate LONG bars (mirrors test_advise.py's baseline)."""
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
        bars[n - 1].date, prev_high + 0.1, final_close + 0.2, prev_high - 0.2,
        final_close, 1_500_000,
    )
    return bars


@pytest.fixture
def qualifying_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the fixture-provider seam to always return a qualifying signal.

    Patches the shared `CsvFixtureProvider` class object (same object AppTest's
    freshly-executed `ui/app.py` script imports) so real fixture staleness
    doesn't make the INV-3-reachability test below a no-op.
    """
    monkeypatch.setattr(
        ds_base.CsvFixtureProvider, "daily_history", lambda self, ticker, days: _qualifying_bars()
    )


def test_ui_renders_without_exception() -> None:
    at = _offline_app().run()
    assert not at.exception


def test_ui_shows_disclaimer() -> None:
    at = _offline_app().run()
    rendered = "\n".join(caption.value for caption in at.caption)
    assert DISCLAIMER in rendered


def test_ui_shows_calendar_last_updated() -> None:
    at = _offline_app().run()
    rendered = "\n".join(caption.value for caption in at.caption)
    assert "last updated" in rendered.lower()


def test_ui_target_dropdown_offers_all_four_targets() -> None:
    at = _offline_app().run()
    options = at.selectbox[0].options
    assert set(options) == {"SPY", "QQQ", "GLD", "SLV"}


# --- INV-3 reachable via real UI inputs (not just the internal override) ----------


def test_ui_exposes_open_positions_and_open_risk_inputs() -> None:
    at = _offline_app().run()
    labels = [ni.label for ni in at.number_input]
    assert any("Open positions" in label for label in labels)
    assert any("Open risk" in label for label in labels)


def test_ui_two_open_positions_forces_no_trade_on_analyze(qualifying_provider: None) -> None:
    at = _offline_app().run()
    open_positions_input = next(ni for ni in at.number_input if "Open positions" in ni.label)
    open_positions_input.set_value(2).run()
    at.button[0].click().run()
    assert not at.exception
    assert "NO TRADE" in at.text[0].value.upper()
    assert "limit" in at.text[0].value
