"""Tests for card rendering and the INV-6 disclaimer (SPEC §4/§8, Phase 3)."""

from advisor.render import DISCLAIMER, render_card
from advisor.strategy.models import Direction, GateResult, NoTrade, TradePlan

PASSING_GATES = [GateResult(name=f"gate{i}", passed=True, detail="ok") for i in range(6)]
FAILING_GATES = [GateResult(name="trend", passed=False, detail="downtrend")] + PASSING_GATES[1:]


def _trade_plan() -> TradePlan:
    return TradePlan(
        target="SPY",
        direction=Direction.LONG,
        entry_low=566.001,
        entry_high=566.499,
        stop_loss=559.7,
        take_profit=575.45,
        size_units=15.8734,
        max_loss_usd=99.976,
        capital=10_000.0,
        risk_pct=0.01,
        breakeven_move_note="move stop to breakeven (1R) at 572.3",
        gates=PASSING_GATES,
    )


def test_disclaimer_matches_inv6_text() -> None:
    assert "not financial advice" in DISCLAIMER
    assert "Trading212" in DISCLAIMER


def test_render_card_trade_plan_always_includes_disclaimer() -> None:
    card = render_card(_trade_plan(), cfd_symbol="US500")
    assert DISCLAIMER in card


def test_render_card_trade_plan_shows_direction_and_cfd_symbol() -> None:
    card = render_card(_trade_plan(), cfd_symbol="US500")
    assert "LONG" in card
    assert "US500" in card
    assert "SPY" in card


def test_render_card_rounds_size_and_max_loss_for_display_only() -> None:
    plan = _trade_plan()
    card = render_card(plan, cfd_symbol="US500")
    assert "15.87" in card
    assert "99.98" in card
    # Presentation rounding must never mutate the underlying model.
    assert plan.size_units == 15.8734
    assert plan.max_loss_usd == 99.976


def test_render_card_no_trade_shows_reason_and_disclaimer() -> None:
    no_trade = NoTrade(target="QQQ", reason="downtrend (longs blocked)", gates=FAILING_GATES)
    card = render_card(no_trade, cfd_symbol="US100")
    assert "downtrend (longs blocked)" in card
    assert DISCLAIMER in card
    assert "NO TRADE" in card.upper()


def test_render_card_includes_event_note_when_supplied() -> None:
    card = render_card(_trade_plan(), cfd_symbol="US500", event_note="CPI on 2026-07-15")
    assert "CPI on 2026-07-15" in card
