"""Pure candlestick chart helpers (SPEC §3/§4, Phase 3).

Kept side-effect-free so it can be unit-tested without a Streamlit runtime:
``bars_to_dataframe`` builds the plotting frame, ``candlestick_chart`` layers
an Altair wick (mark_rule) over an Altair body (mark_bar).
"""

import altair as alt
import pandas as pd

from advisor.strategy.models import Bar

CHART_DAYS = 63

_BULLISH_COLOR = "#26a69a"
_BEARISH_COLOR = "#ef5350"


def _price_columns(bars: list[Bar]) -> dict[str, list]:
    fields = ("open", "high", "low", "close")
    return {field: [getattr(bar, field) for bar in bars] for field in fields}


def _dataframe_columns(bars: list[Bar]) -> dict[str, list]:
    dates = {"date": pd.to_datetime([bar.date for bar in bars])}
    bullish = {"bullish": [bar.close >= bar.open for bar in bars]}
    return {**dates, **_price_columns(bars), **bullish}


def bars_to_dataframe(bars: list[Bar]) -> pd.DataFrame:
    """Convert bars into the flat frame the chart encodings consume."""
    if not bars:
        raise ValueError("no bars to plot")
    return pd.DataFrame(_dataframe_columns(bars))


def _price_y(field: str) -> alt.Y:
    return alt.Y(f"{field}:Q", title="Price", scale=alt.Scale(zero=False))


def _color_encoding() -> alt.Color:
    return alt.Color("bullish:N").scale(
        domain=[True, False], range=[_BULLISH_COLOR, _BEARISH_COLOR]
    ).legend(None)


def _wick_layer(frame: pd.DataFrame) -> alt.Chart:
    encoding = {"x": alt.X("date:T", title="Date"), "y": _price_y("low"), "y2": "high:Q"}
    return alt.Chart(frame).mark_rule().encode(color=_color_encoding(), **encoding)


def _body_layer(frame: pd.DataFrame) -> alt.Chart:
    encoding = {"x": alt.X("date:T", title="Date"), "y": _price_y("open"), "y2": "close:Q"}
    return alt.Chart(frame).mark_bar().encode(color=_color_encoding(), **encoding)


def candlestick_chart(bars: list[Bar]) -> alt.LayerChart:
    """Build a layered wick + body candlestick chart from ascending bars."""
    frame = bars_to_dataframe(bars)
    return alt.layer(_wick_layer(frame), _body_layer(frame))
