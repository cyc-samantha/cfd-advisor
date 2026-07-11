"""MarketDataProvider seam (SPEC SS3, SS8 INV-5, Phase 1).

Every provider implementation must raise :class:`DataUnavailable` for any
missing, malformed, or empty data instead of leaking raw exceptions
(FileNotFoundError, KeyError, network errors, etc.) to callers.
"""

import csv
from abc import ABC, abstractmethod
from datetime import date as date_
from pathlib import Path

from advisor.strategy.models import Bar

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


class DataUnavailable(Exception):
    """Raised whenever market data cannot be produced.

    This is the ONLY error type callers of a :class:`MarketDataProvider`
    should ever need to catch — implementations must translate all
    lower-level failures (missing files, network errors, malformed rows,
    empty responses, NaNs) into this type.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class MarketDataProvider(ABC):
    """Abstract seam between the analysis layer and a market data source.

    Contract for every implementation:
    - ``daily_history`` returns bars sorted ascending by date, with no NaN
      values anywhere; if fewer than ``days`` bars are available or none
      at all, raise :class:`DataUnavailable` rather than returning a short
      or empty list.
    - ``spot`` returns the latest known price as a plain float; if it
      cannot be determined, raise :class:`DataUnavailable`.
    """

    @abstractmethod
    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        """Return the last ``days`` daily bars for ``ticker``, ascending by date."""

    @abstractmethod
    def spot(self, ticker: str) -> float:
        """Return the latest known price for ``ticker``."""


class CsvFixtureProvider(MarketDataProvider):
    """Reads frozen OHLCV fixtures from ``tests/fixtures/{ticker}_daily.csv``.

    Used by tests and offline/demo mode (SPEC INV-5: no network in tests).
    """

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or DEFAULT_FIXTURES_DIR

    def _fixture_path(self, ticker: str) -> Path:
        return self._fixtures_dir / f"{ticker}_daily.csv"

    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        path = self._fixture_path(ticker)
        if not path.exists():
            raise DataUnavailable(f"no fixture file for {ticker!r} at {path}")

        try:
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            raise DataUnavailable(f"could not read fixture for {ticker!r}: {exc}") from exc

        if not rows:
            raise DataUnavailable(f"fixture for {ticker!r} is empty")

        bars: list[Bar] = []
        for row in rows:
            try:
                bars.append(
                    Bar(
                        date=date_.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(float(row["volume"])),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise DataUnavailable(
                    f"malformed row in fixture for {ticker!r}: {row!r} ({exc})"
                ) from exc

        bars.sort(key=lambda bar: bar.date)
        if len(bars) < days:
            raise DataUnavailable(
                f"only {len(bars)} bars available for {ticker!r}, requested {days}"
            )
        return bars[-days:]

    def spot(self, ticker: str) -> float:
        bars = self.daily_history(ticker, days=1)
        return bars[-1].close
