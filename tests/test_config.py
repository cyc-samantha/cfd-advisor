"""Tests for the AppConfig loader (SPEC §2, §3 config.yaml, Phase 3)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from advisor.config import AppConfig, Target, load_config

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


def test_load_config_reads_repo_root_config_by_default() -> None:
    config = load_config()
    assert isinstance(config, AppConfig)
    assert config.capital_default == 10000
    assert config.risk_pct == pytest.approx(0.01)


def test_load_config_reads_market_proxies_and_dow_30() -> None:
    config = load_config()
    symbols = [t.symbol for t in config.targets]
    assert symbols[:4] == ["SPY", "QQQ", "GLD", "SLV"]
    assert len(symbols) == 34
    assert len(set(symbols)) == 34
    assert all(isinstance(t, Target) for t in config.targets)


def test_load_config_target_carries_cfd_symbol_and_name() -> None:
    config = load_config()
    spy = next(t for t in config.targets if t.symbol == "SPY")
    assert spy.cfd_symbol == "US500"
    assert spy.name == "S&P 500"


def test_load_config_reads_risk_and_blackout_fields() -> None:
    config = load_config()
    assert config.risk_pct_min == pytest.approx(0.0025)
    assert config.risk_pct_max == pytest.approx(0.02)
    assert config.tp_r_multiple == pytest.approx(1.5)
    assert config.blackout_days == 2
    assert config.allow_short is True
    assert config.max_open_positions == 2
    assert config.max_open_risk_pct == pytest.approx(0.02)


def test_load_config_accepts_explicit_path() -> None:
    config = load_config(REPO_CONFIG)
    assert config.capital_default == 10000


def test_load_config_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "no_such_config.yaml")


def test_cfd_symbol_for_returns_configured_symbol() -> None:
    config = load_config()
    assert config.cfd_symbol_for("SPY") == "US500"


def test_cfd_symbol_for_falls_back_to_target_when_unknown() -> None:
    config = load_config()
    assert config.cfd_symbol_for("UNKNOWN") == "UNKNOWN"


def test_risk_pct_outside_min_max_is_rejected() -> None:
    raw = {**load_config().model_dump(), "risk_pct": 0.05}
    with pytest.raises(ValidationError):
        AppConfig(**raw)
