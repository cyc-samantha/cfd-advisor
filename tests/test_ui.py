"""Smoke tests for the Streamlit single-page UI (SPEC §4, §8 INV-5, Phase 3)."""

import os

from streamlit.testing.v1 import AppTest

from advisor.render import DISCLAIMER

APP_PATH = "src/advisor/ui/app.py"


def _offline_app() -> AppTest:
    os.environ["ADVISOR_OFFLINE"] = "1"
    return AppTest.from_file(APP_PATH)


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
