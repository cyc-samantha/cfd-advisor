# Index CFD Trade Advisor ("Boring Moat")

Analysis & suggestion tool for high-confidence, stop-loss-protected CFD trades on
the Dow 30 plus index and commodity proxies (SPY, QQQ, GLD, SLV). **No
auto-trading** — the user executes manually in Trading212 by copying the numbers.

See [SPEC.md](./SPEC.md) for the full specification. This project is built in
phases (SPEC §9); this is the Phase 0 scaffold.

## Why this is conservative by construction

1. **Risk-first sizing** — position size is derived from the stop distance so a
   stopped-out trade loses a fixed small % of capital (default 1%). Leverage is an
   output, never an input.
2. **Confluence gate** — trade only when trend + pullback + volatility conditions
   all agree. Few trades, high conviction.
3. **Event blackout** — no new positions right before CPI / FOMC / NFP.
4. **Honest max loss** — the card shows the stop-based max loss and warns that CFD
   stops are not guaranteed through gaps.

## Disclaimer

Analysis tool, not financial advice. CFDs are leveraged; stops are not guaranteed
through gaps. Data delayed. Verify prices in Trading212 before ordering.

## Commands

```bash
uv sync
uv run pytest
uv run ruff check
uv run advisor --help
uv run streamlit run src/advisor/ui/app.py
```
