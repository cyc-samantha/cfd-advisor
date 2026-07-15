"""Isolation guards: this adapter must never plug into MarketDataProvider.

Trading212's public API has no price/quote/OHLCV endpoint at all, so any
accidental coupling to the datasource seam would be a silent lie about
capability, not just an architecture smell.
"""

import ast
from pathlib import Path

from advisor.datasource.base import MarketDataProvider
from advisor.integrations.trading212.client import Trading212Client
from advisor.integrations.trading212.models import AccountSummary, Position

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = REPO_ROOT / "src" / "advisor" / "integrations" / "trading212"


def test_client_is_not_market_data_provider() -> None:
    assert not issubclass(Trading212Client, MarketDataProvider)


def test_exported_types_have_no_price_methods() -> None:
    banned = {"daily_history", "spot"}
    for exported_type in (Trading212Client, Position, AccountSummary):
        assert not (banned & set(dir(exported_type)))


def _iter_source_files(root: Path):
    return root.rglob("*.py")


def _file_contains(path: Path, needle: str) -> bool:
    return needle in path.read_text()


def test_market_data_provider_register_never_applied() -> None:
    source_files = [p for p in _iter_source_files(REPO_ROOT / "src") if ".venv" not in p.parts]
    assert not any(_file_contains(path, "MarketDataProvider.register(") for path in source_files)


def test_package_does_not_import_datasource() -> None:
    for path in _iter_source_files(PACKAGE_DIR):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            _assert_no_datasource_import(node)


def _assert_no_datasource_import(node: ast.AST) -> None:
    if isinstance(node, ast.ImportFrom) and node.module:
        assert "advisor.datasource" not in node.module
    if isinstance(node, ast.Import):
        assert not any("advisor.datasource" in alias.name for alias in node.names)
