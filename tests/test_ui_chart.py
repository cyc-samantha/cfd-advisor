"""Tests for the pure candlestick chart helpers (SPEC §3/§4, Phase 3).

Pure-function tests only: no Streamlit runtime, no network. Bars are
hand-built so INV-5 (no network in tests) holds trivially.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from advisor.strategy.models import Bar
from advisor.ui.chart import CHART_DAYS, bars_to_dataframe, candlestick_chart


def _bar(d: date, o: float, h: float, low_: float, c: float) -> Bar:
    return Bar(date=d, open=o, high=h, low=low_, close=c, volume=1_000_000)


def _bars(n: int) -> list[Bar]:
    start = date(2026, 1, 1)
    return [_bar(start + timedelta(days=i), 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(n)]


def test_chart_days_constant_is_63() -> None:
    assert CHART_DAYS == 63


def test_bars_to_dataframe_has_expected_columns_and_row_count() -> None:
    frame = bars_to_dataframe(_bars(5))
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "bullish"]
    assert len(frame) == 5


def test_bars_to_dataframe_date_column_is_datetime() -> None:
    frame = bars_to_dataframe(_bars(3))
    assert pd.api.types.is_datetime64_any_dtype(frame["date"])


def test_bars_to_dataframe_marks_bullish_when_close_gte_open() -> None:
    up = _bar(date(2026, 1, 1), 100, 102, 99, 101)
    down = _bar(date(2026, 1, 2), 101, 102, 98, 99)
    flat = _bar(date(2026, 1, 3), 100, 101, 99, 100)
    frame = bars_to_dataframe([up, down, flat])
    assert frame["bullish"].tolist() == [True, False, True]


def test_bars_to_dataframe_empty_list_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no bars"):
        bars_to_dataframe([])


def test_candlestick_chart_returns_altair_layer_chart() -> None:
    import altair as alt

    chart = candlestick_chart(_bars(10))
    assert isinstance(chart, alt.LayerChart)


def _mark_type(layer) -> str:
    return layer.mark if isinstance(layer.mark, str) else layer.mark.type


def test_candlestick_chart_layers_are_rule_and_bar_marks() -> None:
    chart = candlestick_chart(_bars(10))
    mark_types = {_mark_type(layer) for layer in chart.layer}
    assert mark_types == {"rule", "bar"}


def test_candlestick_chart_y_scale_does_not_zero() -> None:
    chart = candlestick_chart(_bars(10))
    bar_layer = next(layer for layer in chart.layer if _mark_type(layer) == "bar")
    y_encoding = bar_layer.encoding.y.to_dict()
    assert y_encoding["scale"]["zero"] is False


def test_candlestick_chart_empty_bars_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no bars"):
        candlestick_chart([])
