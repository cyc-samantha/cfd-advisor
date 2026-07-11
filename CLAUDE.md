# CLAUDE.md — Index CFD Trade Advisor

## Commands

```bash
uv sync                                        # install deps into .venv
uv run pytest                                  # run the test suite
uv run ruff check                              # lint
uv run advisor --help                          # CLI entry point
uv run streamlit run src/advisor/ui/app.py     # Streamlit UI (Phase 3)
```

## Architecture (one paragraph)

Local, single-user analysis tool that suggests **at most one** high-confidence,
stop-loss-protected CFD trade per index target (SPY→US500, QQQ→US100, GLD→Gold,
SLV→Silver). It is **not** an auto-trader — the user copies the numbers into
Trading212 manually. Daily OHLCV bars flow from a `MarketDataProvider`
(`datasource/`, yfinance impl behind an ABC seam), through pure-pandas indicators
and a six-gate confluence scorer (`analysis/`), into risk-first sizing and
`TradePlan`/`NoTrade` pydantic models (`strategy/`). Every suggestion is journaled
to SQLite (`journal/`) before display and surfaced via a Typer CLI (`cli.py`) and a
single-page Streamlit UI (`ui/app.py`). Config defaults live in `config.yaml`; the
manually maintained macro calendar lives in `data/events.yaml`.

Full specification: [SPEC.md](./SPEC.md). Build order is in SPEC §9 (this is the
Phase 0 scaffold).

## Hard Invariants (SPEC §8 — verbatim)

- **INV-1**: `TradePlan` requires stop_loss, take_profit, size, max_loss_usd — unconstructible without them (pydantic; tested).
- **INV-2**: `max_loss_usd ≤ capital × risk_pct` (± rounding) or the plan is rejected at construction.
- **INV-3**: New plan refused when open positions ≥ 2 or open risk ≥ 2%.
- **INV-4**: Journal before display.
- **INV-5**: No network in tests (fixture CSVs only).
- **INV-6**: Every output carries: *"Analysis tool, not financial advice. CFDs are leveraged; stops are not guaranteed through gaps. Data delayed. Verify prices in Trading212 before ordering."*
