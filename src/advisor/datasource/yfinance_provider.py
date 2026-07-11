"""yfinance-backed MarketDataProvider (SPEC SS3, A1, Phase 1).

All yfinance/network errors, empty frames, and NaN rows are translated
into :class:`DataUnavailable` -- callers never see raw yfinance/pandas
exceptions.
"""

from datetime import date as date_

import pandas as pd
import yfinance as yf

from advisor.datasource.base import DataUnavailable, MarketDataProvider
from advisor.strategy.models import Bar


class YFinanceProvider(MarketDataProvider):
    """Fetches daily OHLCV bars and spot price from Yahoo Finance via yfinance."""

    def __init__(self, downloader: object = None) -> None:
        """``downloader`` is an injection seam for tests; defaults to ``yf.Ticker``."""
        self._ticker_factory = downloader or yf.Ticker

    def daily_history(self, ticker: str, days: int) -> list[Bar]:
        frame = self._fetch_history(ticker, days)
        bars = self._frame_to_bars(ticker, frame)
        bars.sort(key=lambda bar: bar.date)
        if len(bars) < days:
            raise DataUnavailable(
                f"only {len(bars)} bars available for {ticker!r}, requested {days}"
            )
        return bars[-days:]

    def spot(self, ticker: str) -> float:
        bars = self.daily_history(ticker, days=1)
        return bars[-1].close

    def _fetch_history(self, ticker: str, days: int) -> pd.DataFrame:
        try:
            handle = self._ticker_factory(ticker)
            # Pad the request window: weekends/holidays mean the naive
            # trading-day count needs headroom to reliably yield `days` bars.
            frame = handle.history(period=f"{max(days * 2, days + 10)}d", interval="1d")
        except Exception as exc:  # noqa: BLE001 - yfinance/network failures are opaque
            raise DataUnavailable(f"yfinance request failed for {ticker!r}: {exc}") from exc

        if frame is None or frame.empty:
            raise DataUnavailable(f"yfinance returned no data for {ticker!r}")
        return frame

    def _frame_to_bars(self, ticker: str, frame: pd.DataFrame) -> list[Bar]:
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(frame.columns)
        if missing:
            raise DataUnavailable(f"yfinance data for {ticker!r} missing columns: {missing}")

        clean = frame.dropna(subset=list(required))
        if clean.empty:
            raise DataUnavailable(f"yfinance data for {ticker!r} is all-NaN")

        bars: list[Bar] = []
        for index, row in clean.iterrows():
            try:
                bar_date = (
                    index.date() if hasattr(index, "date") else date_.fromisoformat(str(index))
                )
                bars.append(
                    Bar(
                        date=bar_date,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
            except (ValueError, TypeError) as exc:
                raise DataUnavailable(
                    f"malformed row in yfinance data for {ticker!r}: {exc}"
                ) from exc
        return bars
