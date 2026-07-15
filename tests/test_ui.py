"""Smoke tests for the Streamlit single-page UI (SPEC §4, §8 INV-5, Phase 3)."""

import os

import pytest
from streamlit.testing.v1 import AppTest

import advisor.datasource.base as ds_base
from advisor.render import DISCLAIMER
from conftest import qualifying_bars

APP_PATH = "src/advisor/ui/app.py"


def _offline_app() -> AppTest:
    os.environ["ADVISOR_OFFLINE"] = "1"
    return AppTest.from_file(APP_PATH)


@pytest.fixture
def qualifying_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the fixture-provider seam to always return a qualifying signal.

    Patches the shared `CsvFixtureProvider` class object (same object AppTest's
    freshly-executed `ui/app.py` script imports) so real fixture staleness
    doesn't make the INV-3-reachability test below a no-op.
    """
    monkeypatch.setattr(
        ds_base.CsvFixtureProvider, "daily_history", lambda self, ticker, days: qualifying_bars()
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
