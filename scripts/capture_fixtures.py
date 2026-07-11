"""Fixture-capture script (SPEC SS9 Phase 1).

Fetches ~400 daily bars per ticker via YFinanceProvider and writes
``tests/fixtures/{ticker}_daily.csv``. Requires network access.

Usage:
    uv run python scripts/capture_fixtures.py SPY GLD
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.datasource.base import DataUnavailable  # noqa: E402
from advisor.datasource.yfinance_provider import YFinanceProvider  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DEFAULT_DAYS = 400


def capture(ticker: str, days: int = DEFAULT_DAYS) -> Path:
    provider = YFinanceProvider()
    bars = provider.daily_history(ticker, days=days)

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIXTURES_DIR / f"{ticker}_daily.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "open", "high", "low", "close", "volume"])
        for bar in bars:
            writer.writerow(
                [bar.date.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
            )
    return out_path


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: capture_fixtures.py TICKER [TICKER ...]", file=sys.stderr)
        return 2

    for ticker in argv:
        try:
            path = capture(ticker)
        except DataUnavailable as exc:
            print(f"FAILED {ticker}: {exc.reason}", file=sys.stderr)
            return 1
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
