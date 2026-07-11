"""Command-line interface for the Index CFD Trade Advisor.

Phase 0 scaffold: only ``--help`` and stub subcommands are wired up.
The real ``analyze`` / ``journal`` behaviour arrives in Phases 2 and 3.
"""

from __future__ import annotations

import typer

# INV-6 (SPEC §8): every output carries this disclaimer.
DISCLAIMER = (
    "Analysis tool, not financial advice. CFDs are leveraged; stops are not "
    "guaranteed through gaps. Data delayed. Verify prices in Trading212 before "
    "ordering."
)

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
) -> None:
    """Analyse a target and print a trade plan or no-trade card (Phase 2)."""
    typer.echo("not implemented yet (Phase 2/3)")


@app.command()
def journal() -> None:
    """Show the suggestion/outcome journal (Phase 3)."""
    typer.echo("not implemented yet (Phase 2/3)")


if __name__ == "__main__":
    app()
