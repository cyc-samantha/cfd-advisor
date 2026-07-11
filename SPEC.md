# SPEC — Index CFD Trade Advisor ("Boring Moat", v2)

| | |
|---|---|
| **Status** | Draft v2 — replaces the options-strategy v1 spec entirely (user pivoted: too complicated) |
| **Date** | 2026-07-11 |
| **Deliverable** | Analysis & suggestion tool for **high-confidence, stop-loss-protected CFD trades on index ETFs/indices**. **No auto-trading.** User executes manually in Trading212. |
| **Audience** | Harness build team (agents). Phases in §9 are the build order. |
| **Repo state** | **No repo or folder exists yet.** Phase 0 = general greenfield project setup (`git init`, scaffolding, tooling) inside `options-advisor/`. |

---

## 1. Product Summary

Given a target index (S&P 500, Nasdaq-100, optionally gold/silver), the tool analyses current conditions and outputs **at most one** suggestion per target:

> **LONG / SHORT / NO TRADE** — with exact entry zone, **stop-loss**, **take-profit**, **position size**, and **max loss in dollars**.

The user places the trade manually in the Trading212 CFD app by copying the numbers. The tool only suggests when several independent signals agree (**high confidence**); most days the answer is **"No trade"** — that is the safety mechanism, together with small fixed risk per trade and a hard stop on every position.

### Non-goals
- No automated order placement, ever.
- No scalping/intraday signals — swing trades held days to a few weeks.
- No martingale, averaging down, or trading without a stop.
- No real-time streaming; daily bars + delayed quotes are sufficient for swing signals.

### Where "safe" actually comes from (design principles, encode in README)
CFDs are leveraged and most retail CFD accounts lose money. This tool makes the approach conservative by construction:
1. **Risk-first sizing** — position size is *derived from* the stop distance so that a stopped-out trade loses a fixed small % of capital (default **1%**). Leverage is an output, never an input.
2. **Confluence gate** — trade only when trend + pullback + volatility conditions all agree (§5). Few trades, high conviction.
3. **Event blackout** — no new positions right before CPI / FOMC / NFP (§6).
4. **Honest max loss** — the card shows the stop-based max loss **and** warns that CFD stops are not guaranteed through gaps (overnight/weekend). A "reduced size for gap risk" toggle exists.

---

## 2. Assumptions & Decisions (defaults; overridable in `config.yaml`)

| # | Question | Default decision | Rationale |
|---|---|---|---|
| A1 | Trading212 API for data? | **Not in v1.** T212's public API supports only Invest/ISA (real stock) accounts — **no public CFD endpoints** (no CFD quotes, positions, or orders). v1 uses free `yfinance` daily data; a `MarketDataProvider` seam lets a broker feed drop in later (v2: T212 Invest API for portfolio sync; CFD stays manual). | Realistic — don't spec against an API that doesn't exist. |
| A2 | Which instruments? | Analyse the ETFs **SPY, QQQ** (and optionally **GLD, SLV**) as proxies; the card also shows the matching T212 CFD symbol (US500, US100, Gold, Silver) with a price-scale note. | ETF daily data is free and clean; the CFD tracks the same underlying. |
| A3 | Long only or both? | **Both**, but shorts require a stricter confluence score (downtrends are choppier) — config `allow_short: true`. | User asked for high confidence + safety. |
| A4 | Risk per trade | **1% of account capital** (config `risk_pct`, allowed 0.25–2%). Max **2 open positions**, max **2%** total open risk. | Standard conservative fixed-fractional sizing. |
| A5 | Take-profit | Default **1.5R** (1.5× the stop distance) with an optional note to move stop to breakeven at +1R. Config `tp_r_multiple`. | Positive expectancy even at ~50% hit rate. |
| A6 | Timeframe | Daily bars; signals evaluated once per day after US close (or on demand). | Boring, low-maintenance, low-noise. |
| A7 | UI | Same as v1: Streamlit one page + mirror CLI. One card per target. | "As easy and boring as possible." |

---

## 3. Architecture

```
options-advisor/
├── pyproject.toml            # uv, Python 3.12
├── config.yaml               # targets, risk_pct, tp multiple, blackout days, capital default
├── data/
│   ├── events.yaml           # macro calendar: CPI/FOMC/NFP dates (manually maintained)
│   └── advisor.sqlite        # suggestion + outcome journal
├── src/advisor/
│   ├── datasource/
│   │   ├── base.py           # MarketDataProvider ABC (daily_history, spot)  ← broker seam
│   │   └── yfinance_provider.py
│   ├── analysis/
│   │   ├── indicators.py     # SMA, RSI, ATR, swing high/low (pure pandas functions)
│   │   ├── signal.py         # confluence scoring → Direction + confidence
│   │   └── events.py         # blackout / staleness checks
│   ├── strategy/
│   │   ├── models.py         # pydantic: Bar, Signal, TradePlan, NoTrade
│   │   └── risk.py           # stop placement, sizing, R-multiples, max-loss math
│   ├── journal/store.py      # SQLite
│   ├── cli.py                # `advisor analyze SPY --capital 10000`
│   └── ui/app.py             # Streamlit single page
└── tests/
    ├── fixtures/             # frozen OHLCV CSVs — tests fully offline
    └── test_{indicators,signal,risk,events,plan}.py
```

**Stack**: Python 3.12, `uv`, `pytest`, `pydantic` v2, `yfinance`, `pandas`, `streamlit`, `typer`, stdlib `sqlite3`, `ruff`. Local, single-user, no server.

---

## 4. Inputs & Outputs

### Inputs per run
| Input | Type | Default |
|---|---|---|
| Target | dropdown (SPY, QQQ, GLD, SLV) | — |
| Account capital (CFD account equity) | USD | 10,000 |
| Risk per trade | 0.25–2% | 1% |
| Currently open positions (count + total open risk %) | small form | 0 |

### Output — one **Trade Plan card** or a **No-Trade card**

```
─────────────────────────────────────────────
 US500 (via SPY analysis)          LONG — HIGH CONFIDENCE (score 5/6)
─────────────────────────────────────────────
 Entry zone     5655 – 5670   (SPY 565.5–567.0; pullback to 20-day MA in uptrend)
 STOP LOSS      5602          (below swing low − 0.5×ATR;  −1.05% from entry)
 Take profit    5762          (+1.5R)                       [move stop to BE at 5715]
 Size           $100 risk ÷ 63 pts → 1.59 units ≈ €X margin at 1:20  (T212 shows this)
 MAX LOSS       $100 (1.0% of $10,000) if stopped at 5602
 ⚠ Gap risk     Stop is not guaranteed. A gap through 5602 loses more than $100.
                Holding over a weekend or CPI (2026-07-15) increases this risk.
 Costs          Overnight financing applies on CFDs — plan measured in days/weeks, not months.
 Why            Uptrend (price > 200SMA, 50>200) · pullback to 20SMA · RSI reset <45 →
                turning up · ATR normal · no event within 2 days · volume ok
 Checklist      ☐ set stop & TP in the SAME order ticket  ☐ verify size ⇒ ~$100 at stop  ☐ log it
─────────────────────────────────────────────
```

Card rules:
- **Stop-loss and max loss always present**; a `TradePlan` object without a stop cannot be constructed (INV-1).
- Size is expressed in **risk dollars and units**, plus the sentence "if T212 shows a different margin, the size is what matters — margin is just the deposit."
- No-Trade card states the concrete failed gate: `no pullback — chasing`, `downtrend (longs blocked)`, `FOMC tomorrow`, `ATR spike — volatility too hot`, `2 positions already open`.
- Every card journaled before display.

---

## 5. Signal Engine — confluence scoring (daily bars)

Six binary checks; **LONG requires ≥5/6**, **SHORT requires 6/6** (mirrored conditions). Anything less → No-Trade with the failing gates listed.

| # | Gate (long side) | Implementation |
|---|---|---|
| 1 | **Trend**: close > 200-day SMA AND 50-day SMA > 200-day SMA | `indicators.py` |
| 2 | **Pullback, not chase**: low of last 3 bars touched the 20-day SMA, or RSI(14) dipped below 45 within last 5 bars | avoids buying extended tops |
| 3 | **Turn**: latest close > previous high (simple resumption trigger) | entry trigger |
| 4 | **Volatility sane**: ATR(14) < 1.5 × its 100-day median (no panic regime) | stop math is unreliable in vol spikes |
| 5 | **Event clear**: no high-impact event within `blackout_days: 2` (§6) | events.py |
| 6 | **Room**: distance to recent swing high ≥ 1.5R (TP isn't capped by obvious resistance) | risk/reward sanity |

Stop placement: below the most recent swing low minus 0.5×ATR (long); mirrored for short. Sizing: `units = (capital × risk_pct) / stop_distance`. All pure functions, table-tested on fixtures.

Confidence label: 6/6 = HIGH, 5/6 = MODERATE (long only), else NO TRADE. The score breakdown is always printed — the user should learn *why*, not just obey.

---

## 6. Event Calendar

Same mechanism as v1: `data/events.yaml`, manually maintained (~5 min/month), CPI / FOMC / NFP (+optional PCE). Rules: no **new** entries within `blackout_days` before a high-impact event; any event inside the expected holding window is listed on the card with the gap-risk warning; a calendar with no future events fails loudly ("stale — refresh before trading"). UI shows last-updated date.

---

## 7. Journal (SQLite)

`suggestions` (timestamp, target, direction, full card JSON, score breakdown) and `outcomes` (taken?, actual entry/exit, R result, notes). Plain table in the UI + CSV export. Goal: after 3–6 months the user can see hit-rate and average R — the evidence that the moat works (or the config needs tuning).

---

## 8. Hard Invariants

- **INV-1**: `TradePlan` requires stop_loss, take_profit, size, max_loss_usd — unconstructible without them (pydantic; tested).
- **INV-2**: `max_loss_usd ≤ capital × risk_pct` (± rounding) or the plan is rejected at construction.
- **INV-3**: New plan refused when open positions ≥ 2 or open risk ≥ 2%.
- **INV-4**: Journal before display.
- **INV-5**: No network in tests (fixture CSVs only).
- **INV-6**: Every output carries: *"Analysis tool, not financial advice. CFDs are leveraged; stops are not guaranteed through gaps. Data delayed. Verify prices in Trading212 before ordering."*

---

## 9. Delivery Phases

> **Phase 0 (per requester): no repo/folder exists — start with general greenfield project setup.**

| Phase | Scope | Acceptance criteria (failing tests first, per harness ATDD) |
|---|---|---|
| **0 — Setup** | `git init`, §3 layout, uv+pyproject, pytest+ruff, config defaults, project CLAUDE.md | `uv run pytest` green (empty ok); `uv run advisor --help` works |
| **1 — Data** | `MarketDataProvider` ABC + yfinance impl; fixture-capture script (OHLCV → CSV) | SPY & GLD fixtures load as typed `Bar` series; empty/bad data → typed `DataUnavailable` |
| **2 — Signals + risk** | indicators, 6-gate scorer, stop/size/TP math, `TradePlan`/`NoTrade` | Golden-number tests (below); every gate reachable in table tests; INV-1..3 proven |
| **3 — Events + journal + CLI + UI** | events.yaml loader/blackout, SQLite journal, typer CLI, Streamlit page | E2E on fixtures: `advisor analyze SPY` prints valid card & journals it; blackout blocks entry pre-CPI in test; Streamlit smoke test |
| **v2 (later)** | Trading212 Invest API adapter (portfolio/quotes for Invest side), weekly auto-refresh of event calendar, outcome analytics | — |

Golden-number example (Phase 2 gate): capital 10,000, risk 1%, entry 566.0, stop 559.7 → risk $100, stop distance 6.3, size 15.87 units, TP (1.5R) 575.45, max_loss $99.98. Hand-verified constants in the test file. ~4 pipeline stories, each Budget ≤ 7.

## 10. Known Limitations (state in README + UI footer)

1. Trading212 has **no public CFD API** — execution is manual by design; even in v2 only Invest-account data can sync.
2. ETF prices proxy the CFD instrument; small basis/scale differences exist (card shows both scales).
3. Stops can gap; max loss is the *planned* loss, not an absolute guarantee. Overnight financing makes long holds expensive.
4. yfinance data is delayed and occasionally flaky → typed errors, never silent wrong numbers.
5. Manual event calendar; staleness is surfaced loudly.
6. Not financial advice; user carries all execution and market risk.
