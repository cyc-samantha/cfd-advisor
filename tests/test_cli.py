"""Tests for the typer CLI (SPEC §9 Phase 0/3)."""

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import advisor.cli as cli_module
from advisor.cli import DISCLAIMER, app
from advisor.datasource.base import MarketDataProvider
from advisor.strategy.models import Bar
from conftest import qualifying_bars

runner = CliRunner()


class _QualifyingProvider(MarketDataProvider):
    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        return qualifying_bars()

    def spot(self, ticker: str) -> float:
        return qualifying_bars()[-1].close


@pytest.fixture
def qualifying_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the CLI's fixture provider seam to return an always-qualifying signal.

    Real fixture data rarely produces a qualifying signal on any given day,
    which would make the INV-3-reachability tests below flaky/no-op. This
    only replaces the market-data seam (`build_provider`) -- CLI arg parsing,
    `AdviseOptions` construction, and `advise()` all still run for real.
    """
    monkeypatch.setattr(cli_module, "build_provider", lambda offline: _QualifyingProvider())


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_help_carries_inv6_disclaimer() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # INV-6: the disclaimer must be discoverable from the CLI.
    assert "not financial advice" in DISCLAIMER


def test_analyze_offline_prints_a_card_and_disclaimer(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(app, ["analyze", "SPY", "--offline", "--db", str(db_path)])
    assert result.exit_code == 0
    assert DISCLAIMER in result.stdout
    assert "SPY" in result.stdout


def test_analyze_offline_journals_before_printing(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    runner.invoke(app, ["analyze", "SPY", "--offline", "--db", str(db_path)])
    assert db_path.exists()


def test_journal_empty_db_reports_no_suggestions(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(app, ["journal", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "No suggestions recorded yet." in result.stdout


def test_journal_shows_disclaimer(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(app, ["journal", "--db", str(db_path)])
    assert result.exit_code == 0
    assert DISCLAIMER in result.stdout


def test_journal_after_analyze_lists_the_suggestion(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    runner.invoke(app, ["analyze", "SPY", "--offline", "--db", str(db_path)])
    result = runner.invoke(app, ["journal", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "SPY" in result.stdout


# --- INV-3 reachable via real CLI flags (not just an internal override) ------------


def test_analyze_with_two_open_positions_forces_no_trade(
    tmp_path: Path, qualifying_provider: None
) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(
        app,
        ["analyze", "SPY", "--offline", "--db", str(db_path), "--open-positions", "2",
         "--open-risk-pct", "0.0"],
    )
    assert result.exit_code == 0
    assert "NO TRADE" in result.stdout.upper()
    assert "limit" in result.stdout


def test_analyze_with_open_risk_at_limit_forces_no_trade(
    tmp_path: Path, qualifying_provider: None
) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(
        app,
        ["analyze", "SPY", "--offline", "--db", str(db_path), "--open-positions", "0",
         "--open-risk-pct", "0.02"],
    )
    assert result.exit_code == 0
    assert "NO TRADE" in result.stdout.upper()
    assert "limit" in result.stdout


def test_analyze_without_open_exposure_flags_can_reach_a_trade_plan(
    tmp_path: Path, qualifying_provider: None
) -> None:
    """Without --open-positions/--open-risk-pct, a qualifying signal produces a TradePlan."""
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(app, ["analyze", "SPY", "--offline", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "NO TRADE" not in result.stdout.upper()


def test_analyze_with_explicit_flags_below_threshold_reaches_a_trade_plan(
    tmp_path: Path, qualifying_provider: None
) -> None:
    """Real CLI flags set (not omitted) below both INV-3 thresholds must still reach
    a TradePlan -- the earlier at-limit/over-limit tests only prove the veto side of
    this branch; this proves explicit sub-threshold flags aren't misread as a veto.
    """
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(
        app,
        ["analyze", "SPY", "--offline", "--db", str(db_path), "--open-positions", "1",
         "--open-risk-pct", "0.01"],
    )
    assert result.exit_code == 0
    assert "NO TRADE" not in result.stdout.upper()


# --- lone --open-positions/--open-risk-pct flag errors instead of silent drop ------


def test_analyze_with_only_open_positions_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(
        app,
        ["analyze", "SPY", "--offline", "--db", str(db_path), "--open-positions", "2"],
    )
    assert result.exit_code != 0
    assert "--open-positions" in result.output
    assert "--open-risk-pct" in result.output


def test_analyze_with_only_open_risk_pct_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(
        app,
        ["analyze", "SPY", "--offline", "--db", str(db_path), "--open-risk-pct", "0.01"],
    )
    assert result.exit_code != 0
    assert "--open-positions" in result.output
    assert "--open-risk-pct" in result.output


# --- event note anchors to the analysis as_of, not wall-clock date.today() ---------


def test_analyze_event_note_anchors_to_analysis_as_of(
    tmp_path: Path, qualifying_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A high-impact event just after the fixture's last bar date must surface a gap-risk
    note, even though it is nowhere near wall-clock `date.today()` -- the note must be
    anchored to the same `as_of` the trade plan itself was analysed against.
    """
    from advisor.analysis.events import EventCalendar, MacroEvent

    last_bar_date = qualifying_bars()[-1].date
    event_date = last_bar_date + timedelta(days=5)  # past blackout_days=2, within 14-day hold
    calendar = EventCalendar(
        last_updated=last_bar_date,
        events=[MacroEvent(date=event_date, type="FOMC", impact="high", note="")],
    )
    monkeypatch.setattr(cli_module, "load_events", lambda: calendar)
    db_path = tmp_path / "advisor.sqlite"
    result = runner.invoke(app, ["analyze", "SPY", "--offline", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "NO TRADE" not in result.stdout.upper()
    assert "Gap risk" in result.stdout
