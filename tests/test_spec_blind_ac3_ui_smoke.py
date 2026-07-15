"""Spec-blind AC3: Streamlit smoke test -- ui/app.py imports and renders
without error against fixture data.

Derived ONLY from pipeline.md AC3 and SPEC.md SS3/SS9 ("Streamlit single
page" at src/advisor/ui/app.py). Uses Streamlit's own public AppTest
testing harness (streamlit.testing.v1.AppTest.from_file), which runs the
named script file as an isolated Streamlit app process and reports whether
it raised -- this is the standard black-box "does the entry-point script
run" smoke test, not a read of app.py's implementation.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "src" / "advisor" / "ui" / "app.py"


def test_ui_app_file_exists_at_documented_location():
    # SPEC.md SS3 and CLAUDE.md both document this exact path.
    assert APP_PATH.is_file()


def test_ui_app_imports_and_runs_without_raising():
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    assert not at.exception, [str(e) for e in at.exception]


def test_ui_app_renders_disclaimer_somewhere_on_the_page():
    """INV-6: every output carries the disclaimer -- the UI is an output
    surface too."""
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)

    assert not at.exception

    page_text = " ".join(
        [md.value for md in at.markdown]
        + [t.value for t in at.text]
        + [c.value for c in at.caption]
    )
    assert "not financial advice" in page_text.lower()
