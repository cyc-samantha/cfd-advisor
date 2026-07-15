"""SQLite suggestion/outcome journal (SPEC §7, §8 INV-4, Phase 3).

INV-4 (journal before display) means every ``TradePlan``/``NoTrade`` a
caller intends to show the user must be passed through :meth:`record`
first; ``advise.py`` is responsible for enforcing the ordering.
"""

import sqlite3
from datetime import UTC, date, datetime

from advisor.strategy.models import NoTrade, TradePlan

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    target TEXT NOT NULL,
    cfd_symbol TEXT NOT NULL,
    kind TEXT NOT NULL,
    direction TEXT,
    confidence TEXT,
    score INTEGER,
    entry_low REAL,
    entry_high REAL,
    stop_loss REAL,
    take_profit REAL,
    size_units REAL,
    max_loss_usd REAL,
    risk_pct REAL,
    capital REAL,
    reason TEXT,
    card_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id),
    taken INTEGER NOT NULL DEFAULT 0,
    closed INTEGER NOT NULL DEFAULT 0,
    entry_price REAL,
    exit_price REAL,
    r_result REAL,
    notes TEXT,
    updated_ts TEXT
);
"""

_TRADE_PLAN_ONLY_FIELDS = (
    "entry_low",
    "entry_high",
    "stop_loss",
    "take_profit",
    "size_units",
    "max_loss_usd",
    "risk_pct",
    "capital",
)


_INSERT_SQL = (
    "INSERT INTO suggestions "
    "(ts, as_of_date, target, cfd_symbol, kind, direction, confidence, score, "
    "entry_low, entry_high, stop_loss, take_profit, size_units, max_loss_usd, "
    "risk_pct, capital, reason, card_json) VALUES "
    "(:ts, :as_of_date, :target, :cfd_symbol, :kind, :direction, :confidence, :score, "
    ":entry_low, :entry_high, :stop_loss, :take_profit, :size_units, :max_loss_usd, "
    ":risk_pct, :capital, :reason, :card_json)"
)


def _trade_only_values(result: TradePlan | NoTrade, is_trade: bool) -> dict:
    return {field: getattr(result, field, None) if is_trade else None
            for field in _TRADE_PLAN_ONLY_FIELDS}


def _kind_values(result: TradePlan | NoTrade, is_trade: bool) -> dict:
    return {
        "kind": "trade" if is_trade else "no_trade",
        "direction": result.direction.value if is_trade else None,
        "reason": None if is_trade else result.reason,
        "score": sum(gate.passed for gate in result.gates),
    }


# Flatten a TradePlan/NoTrade into the ``suggestions`` column values.
def _row_values(result: TradePlan | NoTrade) -> dict:
    is_trade = isinstance(result, TradePlan)
    return {**_trade_only_values(result, is_trade), **_kind_values(result, is_trade)}


def _record_identity(result: TradePlan | NoTrade, *, as_of: date, cfd_symbol: str) -> dict:
    return {"as_of_date": as_of.isoformat(), "target": result.target, "cfd_symbol": cfd_symbol}


# confidence isn't carried by TradePlan/NoTrade (only Signal has it) -- always null.
def _record_payload(result: TradePlan | NoTrade) -> dict:
    return {"ts": datetime.now(UTC).isoformat(), "confidence": None,
            "card_json": result.model_dump_json()}


def _record_params(result: TradePlan | NoTrade, *, as_of: date, cfd_symbol: str) -> dict:
    identity = _record_identity(result, as_of=as_of, cfd_symbol=cfd_symbol)
    return {**_row_values(result), **identity, **_record_payload(result)}


class JournalStore:
    """SQLite-backed journal of suggestions and their outcomes."""

    def __init__(self, path: str = "data/advisor.sqlite") -> None:
        # A single long-lived connection is required for `:memory:` paths --
        # a fresh connection per call would open a distinct, empty database.
        self._connection = sqlite3.connect(path)
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def record(self, result: TradePlan | NoTrade, *, as_of: date, cfd_symbol: str) -> int:
        """Journal a suggestion; the single public write entry point (INV-4)."""
        params = _record_params(result, as_of=as_of, cfd_symbol=cfd_symbol)
        cursor = self._connection.execute(_INSERT_SQL, params)
        self._connection.commit()
        return cursor.lastrowid

    def list_suggestions(self, limit: int = 20) -> list[dict]:
        """Newest-first list of journaled suggestions."""
        cursor = self._connection.execute(
            "SELECT * FROM suggestions ORDER BY id DESC LIMIT ?", (limit,)
        )
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def open_exposure(self) -> tuple[int, float]:
        """(count, total risk_pct) of trades taken and not yet closed."""
        cursor = self._connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(s.risk_pct), 0.0) "
            "FROM suggestions s JOIN outcomes o ON o.suggestion_id = s.id "
            "WHERE s.kind = 'trade' AND o.taken = 1 AND o.closed = 0"
        )
        count, total_risk_pct = cursor.fetchone()
        return count, total_risk_pct
