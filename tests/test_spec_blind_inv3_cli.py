"""Spec-blind INV-3 (fix-cycle re-check): "New plan refused when open
positions >= 2 or open risk >= 2%" must be reachable via a real
`advisor analyze --open-positions N --open-risk-pct P` CLI invocation, not
just internal APIs.

Derived ONLY from SPEC.md SS8 (INV-3), pipeline.md's fix-cycle note ("INV-3
unreachable via real CLI/UI" was the round-1 code-review CRITICAL finding),
and `advisor analyze --help`'s documented --open-positions / --open-risk-pct
options. No src/advisor implementation was read.
"""

from __future__ import annotations

from _spec_blind_helpers import (
    QUALIFYING_CUTOFF,
    qualifying_qqq_fixture,
    run_cli,
)


def test_open_positions_and_open_risk_pct_must_be_given_together():
    """--help documents both flags; the CLI must reject one without the
    other rather than silently defaulting (a silent default would make
    INV-3 unreachable in one of the two dimensions)."""
    proc = run_cli(
        "analyze", "SPY", "--db", "/tmp/spec_blind_inv3_partial.sqlite", "--open-positions", "2"
    )
    assert proc.returncode != 0
    assert "--open-positions" in (proc.stdout + proc.stderr)
    assert "--open-risk-pct" in (proc.stdout + proc.stderr)


def test_two_open_positions_blocks_an_otherwise_qualifying_plan():
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF):
        baseline = run_cli(
            "analyze", "QQQ", "--db", "/tmp/spec_blind_inv3_baseline.sqlite"
        )
        blocked = run_cli(
            "analyze",
            "QQQ",
            "--db",
            "/tmp/spec_blind_inv3_two_positions.sqlite",
            "--open-positions",
            "2",
            "--open-risk-pct",
            "0.0",
        )

    # Baseline proves the signal genuinely qualifies absent the INV-3 gate.
    assert baseline.returncode == 0, baseline.stderr
    assert "LONG" in baseline.stdout or "SHORT" in baseline.stdout

    assert blocked.returncode == 0, blocked.stderr
    assert "NO TRADE" in blocked.stdout, blocked.stdout
    assert "LONG" not in blocked.stdout
    assert "SHORT" not in blocked.stdout


def test_open_risk_at_two_point_five_percent_blocks_an_otherwise_qualifying_plan():
    """2.5% open risk exceeds INV-3's 2% ceiling."""
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF):
        blocked = run_cli(
            "analyze",
            "QQQ",
            "--db",
            "/tmp/spec_blind_inv3_open_risk.sqlite",
            "--open-positions",
            "0",
            "--open-risk-pct",
            "0.025",
        )

    assert blocked.returncode == 0, blocked.stderr
    assert "NO TRADE" in blocked.stdout, blocked.stdout


def test_open_risk_just_under_two_percent_does_not_block():
    """Boundary check: open risk safely below the 2% ceiling with 0 open
    positions must NOT trigger INV-3."""
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF):
        proc = run_cli(
            "analyze",
            "QQQ",
            "--db",
            "/tmp/spec_blind_inv3_under_ceiling.sqlite",
            "--open-positions",
            "0",
            "--open-risk-pct",
            "0.01",
        )

    assert proc.returncode == 0, proc.stderr
    assert "LONG" in proc.stdout or "SHORT" in proc.stdout
