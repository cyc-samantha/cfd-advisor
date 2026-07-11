"""Tests for the datasource layer (SPEC SS3, SS8 INV-5, Phase 1).

No network calls anywhere in this file: CsvFixtureProvider reads local
CSVs, and YFinanceProvider is exercised with a stubbed ticker factory.
"""

from datetime import date

import pytest

from advisor.datasource.base import CsvFixtureProvider, DataUnavailable
from advisor.datasource.yfinance_provider import YFinanceProvider
from advisor.strategy.models import Bar

FIXTURES_DIR = None  # resolved via default tests/fixtures path


@pytest.fixture
def provider() -> CsvFixtureProvider:
    return CsvFixtureProvider()


@pytest.mark.parametrize("ticker", ["SPY", "GLD"])
def test_fixture_loads_as_typed_bars_ascending(provider: CsvFixtureProvider, ticker: str) -> None:
    bars = provider.daily_history(ticker, days=400)
    assert len(bars) == 400
    assert all(isinstance(bar, Bar) for bar in bars)
    dates = [bar.date for bar in bars]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


def test_fixture_spot_returns_latest_close(provider: CsvFixtureProvider) -> None:
    bars = provider.daily_history("SPY", days=400)
    assert provider.spot("SPY") == bars[-1].close


def test_missing_fixture_raises_data_unavailable(provider: CsvFixtureProvider) -> None:
    with pytest.raises(DataUnavailable):
        provider.daily_history("NOSUCHTICKER", days=10)


def test_requesting_more_days_than_available_raises_data_unavailable(
    provider: CsvFixtureProvider,
) -> None:
    with pytest.raises(DataUnavailable):
        provider.daily_history("SPY", days=100_000)


def test_empty_fixture_raises_data_unavailable(tmp_path) -> None:
    (tmp_path / "EMPTY_daily.csv").write_text("date,open,high,low,close,volume\n")
    provider = CsvFixtureProvider(fixtures_dir=tmp_path)
    with pytest.raises(DataUnavailable):
        provider.daily_history("EMPTY", days=1)


def test_malformed_fixture_raises_data_unavailable(tmp_path) -> None:
    (tmp_path / "BAD_daily.csv").write_text(
        "date,open,high,low,close,volume\n2026-01-02,100,90,99,102,1000\n"
    )
    provider = CsvFixtureProvider(fixtures_dir=tmp_path)
    with pytest.raises(DataUnavailable):
        provider.daily_history("BAD", days=1)


class _StubHistory:
    def __init__(self, frame) -> None:
        self._frame = frame

    def history(self, period: str, interval: str):
        return self._frame


class _StubTickerFactory:
    def __init__(self, frame) -> None:
        self._frame = frame

    def __call__(self, ticker: str) -> _StubHistory:
        return _StubHistory(self._frame)


def test_yfinance_provider_maps_frame_to_bars() -> None:
    import pandas as pd

    index = pd.to_datetime(["2026-01-02", "2026-01-05"])
    frame = pd.DataFrame(
        {
            "Open": [560.0, 561.0],
            "High": [562.0, 563.0],
            "Low": [559.0, 560.0],
            "Close": [561.5, 562.5],
            "Volume": [1_000_000, 1_100_000],
        },
        index=index,
    )
    provider = YFinanceProvider(downloader=_StubTickerFactory(frame))
    bars = provider.daily_history("SPY", days=2)
    assert bars == [
        Bar(
            date=date(2026, 1, 2), open=560.0, high=562.0, low=559.0, close=561.5, volume=1_000_000
        ),
        Bar(
            date=date(2026, 1, 5), open=561.0, high=563.0, low=560.0, close=562.5, volume=1_100_000
        ),
    ]
    assert provider.spot("SPY") == 562.5


def test_yfinance_provider_empty_frame_raises_data_unavailable() -> None:
    import pandas as pd

    provider = YFinanceProvider(downloader=_StubTickerFactory(pd.DataFrame()))
    with pytest.raises(DataUnavailable):
        provider.daily_history("SPY", days=2)


def test_yfinance_provider_all_nan_rows_raise_data_unavailable() -> None:
    import pandas as pd

    index = pd.to_datetime(["2026-01-02"])
    frame = pd.DataFrame(
        {
            "Open": [float("nan")],
            "High": [float("nan")],
            "Low": [float("nan")],
            "Close": [float("nan")],
            "Volume": [float("nan")],
        },
        index=index,
    )
    provider = YFinanceProvider(downloader=_StubTickerFactory(frame))
    with pytest.raises(DataUnavailable):
        provider.daily_history("SPY", days=1)


def test_yfinance_provider_wraps_downloader_exception() -> None:
    class _BoomFactory:
        def __call__(self, ticker: str):
            raise RuntimeError("network exploded")

    provider = YFinanceProvider(downloader=_BoomFactory())
    with pytest.raises(DataUnavailable):
        provider.daily_history("SPY", days=1)
