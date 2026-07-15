"""Spec-blind AC2: blackout window blocks a new entry when analysis date
falls within blackout_days of a high-impact event (e.g. pre-CPI).

Derived ONLY from pipeline.md AC2, SPEC.md SS6 (Event Calendar) and SS8
(no gate internals were read -- analysis/events.py is denied source).
Approach: differential black-box test against the real, documented,
user-editable data/events.yaml (SPEC SS6: "manually maintained... CPI /
FOMC / NFP"). A fixture date/config combination independently discovered
(by black-box probing of the public CLI, not by reading source) to produce
a qualifying LONG signal is held constant; only the event calendar is
varied, isolating the blackout gate's effect.
"""

from __future__ import annotations

from _spec_blind_helpers import (
    QUALIFYING_CUTOFF,
    qualifying_qqq_fixture,
    run_cli,
    temporary_event,
)

# The qualifying fixture's last bar is dated 2026-03-27 (SPY_daily.csv
# truncated to QUALIFYING_CUTOFF=325 rows). config.yaml's blackout_days is 2.
LAST_BAR_DATE = "2026-03-27"
WITHIN_BLACKOUT_EVENT_DATE = "2026-03-28"  # 1 day after last bar -- inside window
OUTSIDE_BLACKOUT_EVENT_DATE = "2026-04-10"  # 14 days after last bar -- outside window


def test_baseline_qualifying_signal_is_not_blocked_with_no_nearby_event():
    """Sanity baseline: with the real, unmodified events.yaml (no event
    anywhere near 2026-03-27), the qualifying fixture produces a real
    Trade Plan, not a blackout block."""
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF):
        proc = run_cli("analyze", "QQQ", "--db", "/tmp/spec_blind_ac2_baseline.sqlite")

    assert proc.returncode == 0, proc.stderr
    assert "LONG" in proc.stdout or "SHORT" in proc.stdout
    assert "blackout" not in proc.stdout.lower()


def test_event_one_day_after_analysis_date_blocks_new_entry():
    """AC2: analysis date (2026-03-27) is 1 day before an injected
    high-impact CPI event (2026-03-28), well within blackout_days=2 ->
    the same signal that qualified in the baseline must now be blocked."""
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF), temporary_event(
        WITHIN_BLACKOUT_EVENT_DATE
    ):
        proc = run_cli("analyze", "QQQ", "--db", "/tmp/spec_blind_ac2_blocked.sqlite")

    assert proc.returncode == 0, proc.stderr
    assert "NO TRADE" in proc.stdout, proc.stdout
    assert "LONG" not in proc.stdout
    assert "SHORT" not in proc.stdout
    # The reason should name the blackout condition, not a generic miss.
    assert "blackout" in proc.stdout.lower() or "CPI" in proc.stdout


def test_event_well_outside_blackout_window_does_not_block():
    """Differential control: an event far outside blackout_days must NOT
    suppress the same otherwise-qualifying signal -- isolates that it is
    specifically event *proximity*, not merely event *existence*, that
    triggers the block."""
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF), temporary_event(
        OUTSIDE_BLACKOUT_EVENT_DATE
    ):
        proc = run_cli("analyze", "QQQ", "--db", "/tmp/spec_blind_ac2_unblocked.sqlite")

    assert proc.returncode == 0, proc.stderr
    assert "LONG" in proc.stdout or "SHORT" in proc.stdout
