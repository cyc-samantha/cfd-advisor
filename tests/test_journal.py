"""Tests for the SQLite suggestion journal (SPEC §7, §8 INV-4, Phase 3)."""

from datetime import date

import pytest

from advisor.journal.store import JournalStore
from advisor.strategy.models import Direction, GateResult, NoTrade, TradePlan

PASSING_GATES = [GateResult(name=f"gate{i}", passed=True, detail="ok") for i in range(6)]
FAILING_GATES = [GateResult(name="trend", passed=False, detail="downtrend")] + PASSING_GATES[1:]


def _trade_plan(**overrides: object) -> TradePlan:
    base = dict(
        target="SPY",
        direction=Direction.LONG,
        entry_low=566.0,
        entry_high=566.5,
        stop_loss=559.7,
        take_profit=575.45,
        size_units=15.873,
        max_loss_usd=99.98,
        capital=10_000.0,
        risk_pct=0.01,
        breakeven_move_note="move stop to breakeven (1R) at 572.3",
        gates=PASSING_GATES,
    )
    base.update(overrides)
    return TradePlan(**base)


@pytest.fixture
def store() -> JournalStore:
    return JournalStore(path=":memory:")


def test_record_trade_plan_returns_incrementing_ids(store: JournalStore) -> None:
    first_id = store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    second_id = store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    assert second_id > first_id


def test_record_no_trade_returns_an_id(store: JournalStore) -> None:
    no_trade = NoTrade(target="QQQ", reason="downtrend (longs blocked)", gates=FAILING_GATES)
    suggestion_id = store.record(no_trade, as_of=date(2026, 7, 15), cfd_symbol="US100")
    assert isinstance(suggestion_id, int)


def test_list_suggestions_newest_first(store: JournalStore) -> None:
    store.record(_trade_plan(), as_of=date(2026, 7, 14), cfd_symbol="US500")
    store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    rows = store.list_suggestions()
    assert rows[0]["as_of_date"] == "2026-07-15"
    assert rows[1]["as_of_date"] == "2026-07-14"


def test_list_suggestions_captures_trade_plan_fields(store: JournalStore) -> None:
    store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    row = store.list_suggestions()[0]
    assert row["kind"] == "trade"
    assert row["direction"] == "LONG"
    assert row["target"] == "SPY"
    assert row["cfd_symbol"] == "US500"
    assert row["stop_loss"] == pytest.approx(559.7)
    assert row["max_loss_usd"] == pytest.approx(99.98)


def test_list_suggestions_captures_no_trade_fields(store: JournalStore) -> None:
    no_trade = NoTrade(target="QQQ", reason="downtrend (longs blocked)", gates=FAILING_GATES)
    store.record(no_trade, as_of=date(2026, 7, 15), cfd_symbol="US100")
    row = store.list_suggestions()[0]
    assert row["kind"] == "no_trade"
    assert row["reason"] == "downtrend (longs blocked)"
    assert row["direction"] is None


def test_list_suggestions_respects_limit(store: JournalStore) -> None:
    for _ in range(3):
        store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    assert len(store.list_suggestions(limit=2)) == 2


def test_list_suggestions_empty_journal_returns_empty_list(store: JournalStore) -> None:
    assert store.list_suggestions() == []


def test_open_exposure_zero_on_empty_journal(store: JournalStore) -> None:
    assert store.open_exposure() == (0, 0.0)


def test_open_exposure_counts_taken_unclosed(store: JournalStore) -> None:
    suggestion_id = store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    store._connection.execute(
        "INSERT INTO outcomes (suggestion_id, taken, closed) VALUES (?, 1, 0)",
        (suggestion_id,),
    )
    store._connection.commit()
    count, risk_pct = store.open_exposure()
    assert count == 1
    assert risk_pct == pytest.approx(0.01)


def test_open_exposure_ignores_untaken_suggestions(store: JournalStore) -> None:
    suggestion_id = store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    store._connection.execute(
        "INSERT INTO outcomes (suggestion_id, taken, closed) VALUES (?, 0, 0)",
        (suggestion_id,),
    )
    store._connection.commit()
    assert store.open_exposure() == (0, 0.0)


def test_open_exposure_ignores_closed_positions(store: JournalStore) -> None:
    suggestion_id = store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    store._connection.execute(
        "INSERT INTO outcomes (suggestion_id, taken, closed) VALUES (?, 1, 1)",
        (suggestion_id,),
    )
    store._connection.commit()
    assert store.open_exposure() == (0, 0.0)


def test_two_stores_sharing_a_memory_path_do_not_share_rows(store: JournalStore) -> None:
    other = JournalStore(path=":memory:")
    store.record(_trade_plan(), as_of=date(2026, 7, 15), cfd_symbol="US500")
    assert other.list_suggestions() == []
