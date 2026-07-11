"""Deterministic synthetic fixture generator (SPEC SS9 Phase 1).

Used when network/yfinance access is unavailable to capture real data.
Generates a seeded random walk of ~400 daily bars per ticker at
realistic price levels, written to ``tests/fixtures/{ticker}_daily.csv``
in the same schema as ``capture_fixtures.py``. Tests do not care whether
fixtures are real or synthetic -- see tests/fixtures/README.md.

Usage:
    uv run python scripts/generate_synthetic_fixtures.py
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
NUM_BARS = 400
SEED = 20260711

# ticker -> (starting price, daily volatility as a fraction of price)
STARTING_LEVELS = {
    "SPY": (560.0, 0.008),
    "GLD": (310.0, 0.010),
}


def _business_days_ending_today(count: int) -> list[date]:
    days: list[date] = []
    cursor = date.today()
    while len(days) < count:
        if cursor.weekday() < 5:  # Mon-Fri
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def _generate_bars(start_price: float, daily_vol: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    dates = _business_days_ending_today(NUM_BARS)

    bars: list[dict] = []
    close = start_price
    for day in dates:
        open_price = close * (1 + rng.gauss(0, daily_vol * 0.3))
        drift = rng.gauss(0.0002, daily_vol)
        close_price = open_price * (1 + drift)
        high = max(open_price, close_price) * (1 + abs(rng.gauss(0, daily_vol * 0.4)))
        low = min(open_price, close_price) * (1 - abs(rng.gauss(0, daily_vol * 0.4)))
        volume = int(rng.uniform(3_000_000, 9_000_000))

        bars.append(
            {
                "date": day.isoformat(),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close_price, 2),
                "volume": volume,
            }
        )
        close = close_price
    return bars


def generate(ticker: str, start_price: float, daily_vol: float) -> Path:
    bars = _generate_bars(start_price, daily_vol, seed=hash((SEED, ticker)) & 0xFFFFFFFF)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIXTURES_DIR / f"{ticker}_daily.csv"
    with out_path.open("w", newline="") as handle:
        fieldnames = ["date", "open", "high", "low", "close", "volume"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(bars)
    return out_path


def main() -> int:
    for ticker, (start_price, daily_vol) in STARTING_LEVELS.items():
        path = generate(ticker, start_price, daily_vol)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
