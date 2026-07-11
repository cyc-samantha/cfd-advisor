"""Tests for Bar model (SPEC SS3, Phase 1)."""

from datetime import date

import pytest
from pydantic import ValidationError

from advisor.strategy.models import Bar


def _bar(**overrides: object) -> dict:
    base = dict(
        date=date(2026, 1, 2),
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        volume=1_000_000,
    )
    base.update(overrides)
    return base


def test_valid_bar_constructs() -> None:
    bar = Bar(**_bar())
    assert bar.date == date(2026, 1, 2)
    assert bar.high == 105.0
    assert bar.volume == 1_000_000


def test_high_less_than_low_rejected() -> None:
    with pytest.raises(ValidationError):
        Bar(**_bar(high=98.0, low=99.0))


def test_high_less_than_open_or_close_rejected() -> None:
    with pytest.raises(ValidationError):
        Bar(**_bar(high=100.5, open=101.0))


def test_low_greater_than_open_or_close_rejected() -> None:
    with pytest.raises(ValidationError):
        Bar(**_bar(low=101.0, close=100.5))


def test_negative_volume_rejected() -> None:
    with pytest.raises(ValidationError):
        Bar(**_bar(volume=-1))
