"""Smoke test: the typer CLI app exposes a working --help (SPEC §9 Phase 0)."""

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
