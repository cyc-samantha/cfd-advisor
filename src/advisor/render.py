"""Card rendering for the CLI and Streamlit UI (SPEC §4, §8 INV-6, Phase 3).

Rounding here is presentation-only: the underlying TradePlan/NoTrade model
is never mutated or recomputed, only formatted for display.
"""

from advisor.strategy.models import NoTrade, TradePlan

# INV-6 (SPEC §8): every output carries this disclaimer.
DISCLAIMER = (
    "Analysis tool, not financial advice. CFDs are leveraged; stops are not "
    "guaranteed through gaps. Data delayed. Verify prices in Trading212 before "
    "ordering."
)


def render_card(
    result: TradePlan | NoTrade, *, cfd_symbol: str, event_note: str | None = None
) -> str:
    """Render a TradePlan or NoTrade as a plain-text card (INV-6 always appended)."""
    body = (
        _trade_card(result, cfd_symbol) if isinstance(result, TradePlan) else _no_trade_card(result)
    )
    lines = [body] + ([event_note] if event_note else []) + [DISCLAIMER]
    return "\n".join(lines)


def _trade_card_header(plan: TradePlan, cfd_symbol: str) -> str:
    return (
        f"{cfd_symbol} (via {plan.target} analysis) — {plan.direction.value}\n"
        f"Entry zone   {plan.entry_low:.2f} - {plan.entry_high:.2f}\n"
        f"Stop loss    {plan.stop_loss:.2f}\n"
        f"Take profit  {plan.take_profit:.2f}"
    )


def _trade_card(plan: TradePlan, cfd_symbol: str) -> str:
    return (
        f"{_trade_card_header(plan, cfd_symbol)}\n"
        f"Size         {plan.size_units:.2f} units\n"
        f"Max loss     ${plan.max_loss_usd:.2f} ({plan.risk_pct:.1%} of ${plan.capital:,.0f})\n"
        f"{plan.breakeven_move_note}"
    )


def _no_trade_card(no_trade: NoTrade) -> str:
    return f"{no_trade.target} — NO TRADE\nReason: {no_trade.reason}"
