"""Pydantic domain models for the strategy layer (SPEC SS3, Phase 1).

Phase 1 scope: only ``Bar``. Signal/TradePlan/NoTrade land in Phase 2.
"""

from datetime import date as date_

from pydantic import BaseModel, model_validator


class Bar(BaseModel):
    """A single daily OHLCV bar.

    Validated so that malformed data never silently flows into indicators:
    ``high`` must be at least the max of open/close, ``low`` must be at
    most the min of open/close, and ``volume`` cannot be negative.
    """

    date: date_
    open: float
    high: float
    low: float
    close: float
    volume: int

    @model_validator(mode="after")
    def _check_ohlc_consistency(self) -> "Bar":
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"high ({self.high}) must be >= max(open, close) "
                f"({max(self.open, self.close)})"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"low ({self.low}) must be <= min(open, close) "
                f"({min(self.open, self.close)})"
            )
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        if self.volume < 0:
            raise ValueError(f"volume ({self.volume}) must be >= 0")
        return self
