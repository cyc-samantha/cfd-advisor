"""Macro event calendar: loading, staleness, and the blackout gate (SPEC §6, Phase 3).

Gate 5 of the confluence scorer ("event clear") is a seam that Phase 2's
``signal.py`` accepts but does not itself enforce as a hard veto (a failed
event gate alone still allows a 5/6 MODERATE signal through). The blackout
check here is therefore applied as an independent hard veto by ``advise()``,
not relied upon via the scorer alone.
"""

from datetime import date as date_
from datetime import timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel

from advisor.strategy.models import GateResult

DEFAULT_EVENTS_PATH = Path(__file__).resolve().parents[3] / "data" / "events.yaml"

HIGH_IMPACT = "high"

# SPEC §6: swing trades are held "days to a few weeks" (§1 non-goals); no
# config field exists for the hold length, so this is a documented estimate
# used only for the card's advisory gap-risk note (not a hard veto).
HOLDING_WINDOW_DAYS = 14


class MacroEvent(BaseModel):
    """One macro calendar entry (SPEC §6 schema)."""

    date: date_
    type: str
    impact: str
    note: str = ""


class StaleCalendar(Exception):
    """Raised when an event calendar has no future events left (SPEC §6)."""


class EventCalendar(BaseModel):
    """The full macro calendar, with its last-maintained date (SPEC §6)."""

    last_updated: date_
    events: list[MacroEvent]

    def is_stale(self, as_of: date_) -> bool:
        """True when no event on or after ``as_of`` remains in the calendar."""
        return not any(event.date >= as_of for event in self.events)


def _read_yaml(path: Path, missing_message: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(missing_message)
    with path.open() as handle:
        return yaml.safe_load(handle)


def load_events(path: Path | None = None) -> EventCalendar:
    """Load and validate ``data/events.yaml``, defaulting to the repo-root file."""
    events_path = path or DEFAULT_EVENTS_PATH
    raw = _read_yaml(events_path, f"events file not found: {events_path}")
    return EventCalendar(**raw)


def _blocking_event(
    as_of: date_, events: list[MacroEvent], blackout_days: int
) -> MacroEvent | None:
    window_end = as_of + timedelta(days=blackout_days)
    for event in events:
        if event.impact == HIGH_IMPACT and as_of <= event.date <= window_end:
            return event
    return None


def is_blackout(as_of: date_, events: list[MacroEvent], blackout_days: int) -> bool:
    """True iff a high-impact event falls within ``blackout_days`` of ``as_of``.

    Boundary-inclusive on both ends: an event today, or exactly
    ``blackout_days`` out, both count as blackout.
    """
    return _blocking_event(as_of, events, blackout_days) is not None


def blackout_reason(as_of: date_, events: list[MacroEvent], blackout_days: int) -> str | None:
    """Human-readable reason for a blackout veto, or ``None`` if clear."""
    event = _blocking_event(as_of, events, blackout_days)
    if event is None:
        return None
    return f"{event.type} on {event.date.isoformat()} — within {blackout_days}-day blackout"


def holding_event_note(
    as_of: date_, events: list[MacroEvent], window_days: int = HOLDING_WINDOW_DAYS
) -> str | None:
    """Gap-risk warning for a high-impact event inside the expected holding window."""
    window_end = as_of + timedelta(days=window_days)
    upcoming = [e for e in events if e.impact == HIGH_IMPACT and as_of <= e.date <= window_end]
    if not upcoming:
        return None
    event = min(upcoming, key=lambda e: e.date)
    return f"Gap risk: {event.type} on {event.date.isoformat()} falls within the expected hold"


def event_gate(as_of: date_, events: list[MacroEvent], blackout_days: int) -> GateResult:
    """Gate 5 ("event clear") in ``signal.py``'s GateResult shape."""
    reason = blackout_reason(as_of, events, blackout_days)
    if reason is not None:
        return GateResult(name="event clear", passed=False, detail=reason)
    return GateResult(name="event clear", passed=True, detail="no high-impact event in window")
