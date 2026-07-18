from advisor.analysis.indicators import latest_snapshot
from conftest import qualifying_bars


def test_latest_snapshot_exposes_strategy_indicator_values() -> None:
    bars = qualifying_bars()
    snapshot = latest_snapshot(bars)

    assert snapshot.close == bars[-1].close
    assert snapshot.sma_20 > 0
    assert snapshot.sma_50 > 0
    assert snapshot.sma_200 > 0
    assert 0 <= snapshot.rsi_14 <= 100
    assert snapshot.atr_14 > 0
    assert snapshot.median_atr_100 > 0
