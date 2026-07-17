"""Shared helpers for the spec-blind validator's black-box test suite.

These tests are authored from the AC plan (pipeline-state/build-cfd-advisor/
pipeline.md), SPEC.md SS4/SS6/SS8/SS9 Phase 3, and the CLI's own --help output
ONLY. No implementation source under src/advisor was read to derive these
tests -- see harness protocols/spec-blind-validate skill.

Not named test_*.py so pytest does not try to collect it as a test module.
"""

from __future__ import annotations

import contextlib
import csv
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPY_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "SPY_daily.csv"
QQQ_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "QQQ_daily.csv"
EVENTS_FILE = REPO_ROOT / "data" / "events.yaml"

# Discovered by black-box probing (SPY_daily.csv truncated to 325 rows, i.e.
# through row date 2026-03-27): the real shipped SPY fixture data, replayed
# under the QQQ target slot, produces a genuine qualifying LONG signal under
# the project's default config.yaml (risk_pct 1%, tp_r_multiple 1.5,
# blackout_days 2). This lets black-box tests exercise the *qualifying*
# branch (TradePlan) rather than only the No-Trade branch, without any
# knowledge of indicator/gate internals.
QUALIFYING_CUTOFF = 325


def run_cli(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Invoke the public `advisor` CLI entry point exactly as a user would.

    WHY: `analyze` now defaults to live yfinance data, but these black-box
    tests are keyed to the shipped/patched fixture CSVs (INV-5: no network
    in tests) -- so every `analyze` invocation must force `--offline`
    unless the caller already asked for a specific data source.
    """
    if "analyze" in args and "--offline" not in args and "--no-offline" not in args:
        args = (*args, "--offline")
    return subprocess.run(
        ["uv", "run", "advisor", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@contextlib.contextmanager
def qualifying_qqq_fixture(cutoff: int = QUALIFYING_CUTOFF):
    """Temporarily install a QQQ fixture (from real SPY data) known to
    produce a qualifying LONG signal under default config, at the target
    slot QQQ (which ships with no fixture of its own). Cleans up after."""
    with SPY_FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]
    pre_existing = QQQ_FIXTURE.exists()
    if pre_existing:
        original = QQQ_FIXTURE.read_bytes()
    try:
        with QQQ_FIXTURE.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(data[:cutoff])
        yield
    finally:
        if pre_existing:
            QQQ_FIXTURE.write_bytes(original)
        else:
            QQQ_FIXTURE.unlink(missing_ok=True)


@contextlib.contextmanager
def temporary_event(date: str, event_type: str = "CPI", impact: str = "high"):
    """Temporarily append one event to the real data/events.yaml (the
    documented, user-editable macro calendar per SPEC SS6) and restore the
    original file content afterwards."""
    original = EVENTS_FILE.read_text()
    injected = original + (
        "\n  # TEMP-PROBE (spec-blind-validator, restored after test)\n"
        f"  - date: {date}\n"
        f"    type: {event_type}\n"
        f"    impact: {impact}\n"
        '    note: "TEMP-PROBE"\n'
    )
    try:
        EVENTS_FILE.write_text(injected)
        yield
    finally:
        EVENTS_FILE.write_text(original)
