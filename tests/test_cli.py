"""Tests for the typer CLI (SPEC §9 Phase 0/3)."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import advisor.cli as cli_module
from advisor.cli import DISCLAIMER, app
from advisor.datasource.base import MarketDataProvider
from advisor.strategy.models import Bar

runner = CliRunner()


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


class _QualifyingProvider(MarketDataProvider):
    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        return _qualifying_bars()

    def spot(self, ticker: str) -> float:
        return _qualifying_bars()[-1].close


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
