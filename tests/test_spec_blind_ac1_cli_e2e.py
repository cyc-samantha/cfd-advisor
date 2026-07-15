"""Spec-blind AC1: `advisor analyze SPY` E2E on fixtures prints a valid
trade-plan/no-trade card and journals it before display.

Derived ONLY from pipeline.md AC1, SPEC.md SS4 (card rules) / SS8 (INV-4, INV-6),
and the public CLI surface (`advisor --help`, `advisor analyze --help`,
`advisor journal --help`). No src/advisor implementation was read.
"""

from __future__ import annotations

from _spec_blind_helpers import (
    QUALIFYING_CUTOFF,
    qualifying_qqq_fixture,
    run_cli,
)

DISCLAIMER = (
    "Analysis tool, not financial advice. CFDs are leveraged; stops are not "
    "guaranteed through gaps. Data delayed. Verify prices in Trading212 "
    "before ordering."
)


def test_analyze_spy_on_shipped_fixture_succeeds_and_prints_disclaimer(tmp_path):
    db = tmp_path / "journal.sqlite"
    proc = run_cli("analyze", "SPY", "--db", str(db))

    assert proc.returncode == 0, proc.stderr
    assert "SPY" in proc.stdout
    # INV-6: disclaimer present on every output, verbatim per SPEC SS8.
    assert DISCLAIMER in proc.stdout


def test_analyze_spy_card_is_either_no_trade_or_trade_plan_shaped(tmp_path):
    """SPEC SS4: output is one of exactly two card shapes -- a No-Trade card
    naming the failed gate, or a Trade Plan card carrying stop/TP/size/max-loss
    (INV-1: unconstructible without them)."""
    db = tmp_path / "journal.sqlite"
    proc = run_cli("analyze", "SPY", "--db", str(db))

    assert proc.returncode == 0, proc.stderr
    if "NO TRADE" in proc.stdout:
        assert "Reason:" in proc.stdout
    else:
        for required_field in ("Stop loss", "Take profit", "Size", "Max loss"):
            assert required_field in proc.stdout, proc.stdout


def test_analyze_journals_before_display_entry_is_queryable_after(tmp_path):
    """Black-box proxy for INV-4 (journal before display): after `analyze`
    returns, the same database's `journal` command must show the suggestion
    that was just displayed."""
    db = tmp_path / "journal.sqlite"
    analyze_proc = run_cli("analyze", "SPY", "--db", str(db))
    assert analyze_proc.returncode == 0, analyze_proc.stderr

    journal_proc = run_cli("journal", "--db", str(db), "--limit", "5")
    assert journal_proc.returncode == 0, journal_proc.stderr
    assert "SPY" in journal_proc.stdout


def test_analyze_qualifying_signal_prints_full_trade_plan_card(tmp_path):
    """Exercises the genuine Trade Plan branch (not just No-Trade) on real
    market-shaped fixture data (SPY_daily.csv replayed at the QQQ slot,
    truncated to a cutoff independently discovered to qualify under default
    config -- see _spec_blind_helpers.qualifying_qqq_fixture)."""
    db = tmp_path / "journal.sqlite"
    with qualifying_qqq_fixture(QUALIFYING_CUTOFF):
        proc = run_cli("analyze", "QQQ", "--db", str(db))

    assert proc.returncode == 0, proc.stderr
    assert "LONG" in proc.stdout or "SHORT" in proc.stdout
    for required_field in ("Entry zone", "Stop loss", "Take profit", "Size", "Max loss"):
        assert required_field in proc.stdout, proc.stdout
    assert DISCLAIMER in proc.stdout
