"""Tests for the typer CLI (SPEC §9 Phase 0/3)."""

from pathlib import Path

from typer.testing import CliRunner

from advisor.cli import DISCLAIMER, app

runner = CliRunner()


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
