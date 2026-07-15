"""Tests for the macro event calendar and blackout gate (SPEC §6, Phase 3)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from advisor.analysis.events import (
    HOLDING_WINDOW_DAYS,
    EventCalendar,
    MacroEvent,
    StaleCalendar,
    blackout_reason,
    event_gate,
    holding_event_note,
    is_blackout,
    load_events,
)

REPO_EVENTS = Path(__file__).resolve().parents[1] / "data" / "events.yaml"

HIGH_IMPACT_EVENT = MacroEvent(date=date(2026, 7, 15), type="CPI", impact="high", note="")
LOW_IMPACT_EVENT = MacroEvent(date=date(2026, 7, 15), type="PCE", impact="low", note="")


def _calendar(*events: MacroEvent, last_updated: date = date(2026, 7, 1)) -> EventCalendar:
    return EventCalendar(last_updated=last_updated, events=list(events))


# --- load_events --------------------------------------------------------------


def test_load_events_reads_repo_root_events_yaml_by_default() -> None:
    calendar = load_events()
    assert isinstance(calendar, EventCalendar)
    assert calendar.last_updated == date(2026, 7, 11)
    assert len(calendar.events) == 3


def test_load_events_parses_event_fields() -> None:
    calendar = load_events()
    cpi = next(e for e in calendar.events if e.type == "CPI")
    assert cpi.date == date(2026, 7, 15)
    assert cpi.impact == "high"
    assert "CPI" in cpi.note


def test_load_events_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_events(tmp_path / "no_such_events.yaml")


# --- EventCalendar.is_stale -----------------------------------------------------


def test_calendar_is_stale_when_no_future_events() -> None:
    calendar = _calendar(MacroEvent(date=date(2026, 7, 1), type="CPI", impact="high", note=""))
    assert calendar.is_stale(as_of=date(2026, 7, 15)) is True


def test_calendar_not_stale_when_a_future_event_exists() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    assert calendar.is_stale(as_of=date(2026, 7, 1)) is False


def test_calendar_not_stale_when_event_is_today() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    assert calendar.is_stale(as_of=date(2026, 7, 15)) is False


def test_calendar_empty_events_is_stale() -> None:
    calendar = _calendar()
    assert calendar.is_stale(as_of=date(2026, 7, 15)) is True


# --- is_blackout boundary tests --------------------------------------------------


@pytest.mark.parametrize(
    "days_before,expected",
    [(0, True), (1, True), (2, True), (3, False)],
)
def test_is_blackout_boundary_inclusive_both_ends(days_before: int, expected: bool) -> None:
    as_of = HIGH_IMPACT_EVENT.date - timedelta(days=days_before)
    calendar = _calendar(HIGH_IMPACT_EVENT)
    assert is_blackout(as_of, calendar.events, blackout_days=2) is expected


def test_is_blackout_true_on_the_event_date_itself() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    assert is_blackout(HIGH_IMPACT_EVENT.date, calendar.events, blackout_days=2) is True


def test_is_blackout_false_after_event_has_passed() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    as_of = HIGH_IMPACT_EVENT.date + timedelta(days=1)
    assert is_blackout(as_of, calendar.events, blackout_days=2) is False


def test_is_blackout_ignores_low_impact_events() -> None:
    calendar = _calendar(LOW_IMPACT_EVENT)
    assert is_blackout(LOW_IMPACT_EVENT.date, calendar.events, blackout_days=2) is False


def test_is_blackout_false_with_no_events() -> None:
    assert is_blackout(date(2026, 7, 15), [], blackout_days=2) is False


# --- blackout_reason --------------------------------------------------------------


def test_blackout_reason_none_when_not_in_blackout() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    as_of = HIGH_IMPACT_EVENT.date + timedelta(days=1)
    assert blackout_reason(as_of, calendar.events, blackout_days=2) is None


def test_blackout_reason_names_the_event_type_and_date() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    reason = blackout_reason(HIGH_IMPACT_EVENT.date, calendar.events, blackout_days=2)
    assert reason is not None
    assert "CPI" in reason
    assert "2026-07-15" in reason


# --- event_gate --------------------------------------------------------------------


def test_event_gate_fails_in_blackout_with_matching_gate_result_shape() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    gate = event_gate(HIGH_IMPACT_EVENT.date, calendar.events, blackout_days=2)
    assert gate.name == "event clear"
    assert gate.passed is False
    assert "CPI" in gate.detail


def test_event_gate_passes_outside_blackout() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    as_of = HIGH_IMPACT_EVENT.date + timedelta(days=1)
    gate = event_gate(as_of, calendar.events, blackout_days=2)
    assert gate.name == "event clear"
    assert gate.passed is True


# --- StaleCalendar is a usable exception type -------------------------------------


def test_stale_calendar_is_an_exception() -> None:
    assert issubclass(StaleCalendar, Exception)


# --- holding_event_note (SPEC §6 gap-risk warning) --------------------------------


def test_holding_event_note_none_when_no_event_in_window() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    as_of = HIGH_IMPACT_EVENT.date - timedelta(days=HOLDING_WINDOW_DAYS + 5)
    assert holding_event_note(as_of, calendar.events) is None


def test_holding_event_note_present_when_event_inside_window() -> None:
    calendar = _calendar(HIGH_IMPACT_EVENT)
    as_of = HIGH_IMPACT_EVENT.date - timedelta(days=HOLDING_WINDOW_DAYS - 1)
    note = holding_event_note(as_of, calendar.events)
    assert note is not None
    assert "CPI" in note
    assert "2026-07-15" in note


def test_holding_event_note_ignores_low_impact_events() -> None:
    calendar = _calendar(LOW_IMPACT_EVENT)
    assert holding_event_note(LOW_IMPACT_EVENT.date, calendar.events) is None
