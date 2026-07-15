"""Command-line interface for the Index CFD Trade Advisor (SPEC §9 Phase 3)."""

from __future__ import annotations

import typer

from advisor.advise import advise, build_provider
from advisor.analysis.events import load_events
from advisor.config import load_config
from advisor.journal.store import JournalStore
from advisor.render import DISCLAIMER, render_card

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
) -> None:
    """Analyse a target and print a trade plan or no-trade card (INV-4: journals first)."""
    config = load_config()
    result = advise(
        target,
        provider=build_provider(offline=offline),
        calendar=load_events(),
        store=JournalStore(path=db),
        config=config,
        capital=capital,
    )
    cfd_symbol = next((t.cfd_symbol for t in config.targets if t.symbol == target), target)
    typer.echo(render_card(result, cfd_symbol=cfd_symbol))


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
