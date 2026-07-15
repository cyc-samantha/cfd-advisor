"""Command-line interface for the Index CFD Trade Advisor (SPEC §9 Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import typer

from advisor.advise import AdviseOptions, advise, build_provider
from advisor.analysis.events import EventCalendar, holding_event_note, load_events
from advisor.config import AppConfig, load_config
from advisor.journal.store import JournalStore
from advisor.render import DISCLAIMER, render_card
from advisor.strategy.models import TradePlan

__all__ = ["DISCLAIMER", "app"]

app = typer.Typer(
    name="advisor",
    help=(
        "Index CFD Trade Advisor — suggests high-confidence, stop-loss-protected "
        "CFD trades on index ETFs (SPY, QQQ, GLD, SLV). No auto-trading; you "
        "execute manually in Trading212.\n\n"
        f"{DISCLAIMER}"
    ),
    epilog=DISCLAIMER,
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def analyze(
    target: str = typer.Argument(..., help="Target symbol: SPY, QQQ, GLD, or SLV."),
    capital: float = typer.Option(10000, help="CFD account equity in USD."),
    offline: bool = typer.Option(True, help="Use frozen fixture data instead of yfinance."),
    db: str = typer.Option("data/advisor.sqlite", help="Path to the journal SQLite database."),
    open_positions: int = typer.Option(
        None, "--open-positions", help="Currently open CFD positions (INV-3)."
    ),
    open_risk_pct: float = typer.Option(
        None, "--open-risk-pct", help="Currently open risk as a fraction of capital (INV-3)."
    ),
) -> None:
    """Analyse a target and print a trade plan or no-trade card (INV-4: journals first)."""
    config = load_config()
    calendar = load_events()
    args = _AnalyzeArgs(
        target, capital, offline, db,
        AdviseOptions(open_positions=open_positions, open_risk_pct=open_risk_pct),
    )
    result = _run_advise(args, config, calendar)
    typer.echo(_render_result(result, config, calendar, target))


@dataclass(frozen=True)
class _AnalyzeArgs:
    target: str
    capital: float
    offline: bool
    db: str
    options: AdviseOptions


def _run_advise(args: _AnalyzeArgs, config: AppConfig, calendar: EventCalendar):
    return advise(
        args.target, provider=build_provider(offline=args.offline), calendar=calendar,
        store=JournalStore(path=args.db), config=config, capital=args.capital, options=args.options,
    )


def _render_result(result, config: AppConfig, calendar: EventCalendar, target: str) -> str:
    is_trade = isinstance(result, TradePlan)
    event_note = holding_event_note(date.today(), calendar.events) if is_trade else None
    return render_card(result, cfd_symbol=config.cfd_symbol_for(target), event_note=event_note)


@app.command()
def journal(
    db: str = typer.Option("data/advisor.sqlite", help="Path to the journal SQLite database."),
    limit: int = typer.Option(20, help="Number of recent suggestions to show."),
) -> None:
    """Show the suggestion journal."""
    rows = JournalStore(path=db).list_suggestions(limit=limit)
    typer.echo(_journal_table(rows))
    typer.echo(DISCLAIMER)


def _journal_table(rows: list[dict]) -> str:
    if not rows:
        return "No suggestions recorded yet."
    lines = [_journal_row(row) for row in rows]
    return "\n".join(lines)


def _journal_row(row: dict) -> str:
    return f"{row['as_of_date']}  {row['target']:>4}  {row['kind']:>8}  {row.get('reason') or ''}"


if __name__ == "__main__":
    app()
