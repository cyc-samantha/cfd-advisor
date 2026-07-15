"""Application config loader (SPEC §2, §3 config.yaml, Phase 3).

``config.yaml`` at the repo root is the single source of truth for target
instruments, risk budget, and blackout policy; this module is the only
place that parses it into typed values.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class Target(BaseModel):
    """One analysed instrument: the ETF proxy and its Trading212 CFD symbol."""

    symbol: str
    cfd_symbol: str
    name: str


class AppConfig(BaseModel):
    """Typed view of ``config.yaml`` (SPEC §2)."""

    targets: list[Target]
    risk_pct: float
    risk_pct_min: float
    risk_pct_max: float
    tp_r_multiple: float
    blackout_days: int
    allow_short: bool
    capital_default: float
    max_open_positions: int
    max_open_risk_pct: float

    @model_validator(mode="after")
    def _risk_pct_within_bounds(self) -> "AppConfig":
        # SPEC A4: risk_pct must stay within the configured 0.25%-2% band.
        if not (self.risk_pct_min <= self.risk_pct <= self.risk_pct_max):
            raise ValueError(
                f"risk_pct {self.risk_pct} outside [{self.risk_pct_min}, {self.risk_pct_max}]"
            )
        return self

    def cfd_symbol_for(self, target: str) -> str:
        """Trading212 CFD symbol for ``target``, or ``target`` itself if unknown."""
        return next((t.cfd_symbol for t in self.targets if t.symbol == target), target)


def _read_yaml(path: Path, missing_message: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(missing_message)
    with path.open() as handle:
        return yaml.safe_load(handle)


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate ``config.yaml``, defaulting to the repo-root file."""
    config_path = path or DEFAULT_CONFIG_PATH
    raw = _read_yaml(config_path, f"config file not found: {config_path}")
    return AppConfig(**raw)
