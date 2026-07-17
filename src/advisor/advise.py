"""Orchestrates a single advise() call (SPEC §3/§5/§6, §8 INV-3/INV-4, Phase 3).

Sequence: load bars -> resolve as_of -> hard calendar veto (stale/blackout,
independent of the scorer -- see analysis.events module docstring) -> score
-> risk-size -> journal (INV-4) -> return. Shared once by both the CLI and
the Streamlit UI so there is exactly one place this policy lives.
"""

from dataclasses import dataclass
from datetime import date as date_

from advisor.analysis.events import EventCalendar, blackout_reason, event_gate
from advisor.analysis.signal import SignalConfig, evaluate, score_gates
from advisor.config import AppConfig
from advisor.datasource.base import CsvFixtureProvider, DataUnavailable, MarketDataProvider
from advisor.datasource.yfinance_provider import YFinanceProvider
from advisor.journal.store import JournalStore
from advisor.strategy.models import Bar, Direction, GateResult, NoTrade, Signal, TradePlan
from advisor.strategy.risk import build_trade_plan

HISTORY_DAYS = 260


def build_provider(offline: bool) -> MarketDataProvider:
    """Fixture provider offline (tests/demo, INV-5); yfinance otherwise."""
    return CsvFixtureProvider() if offline else YFinanceProvider()


@dataclass(frozen=True)
class AdviseOptions:
    """Explicit, typed overrides for the open-exposure/as_of inputs to :func:`advise`.

    Replaces a ``**overrides`` dict (former footgun: a mistyped key like
    ``open_position`` would silently be dropped by ``.get(...)`` and the
    INV-3 exposure check would size the plan as if the account were flat).
    """

    open_positions: int | None = None
    open_risk_pct: float | None = None
    as_of: date_ | None = None
    calendar_check: bool = True


@dataclass(frozen=True)
class AdviseResult:
    """A `TradePlan`/`NoTrade` paired with the `as_of` date it was analysed against.

    Callers that render a second artefact keyed on time (e.g. the event/gap-risk
    note) must anchor it to this `as_of`, not wall-clock `date.today()` --
    `advise()` may resolve `as_of` to the fixture's last bar date rather than today.
    """

    plan: TradePlan | NoTrade
    as_of: date_
    calendar_checked: bool


@dataclass(frozen=True)
class _AdviseRequest:
    target: str
    provider: MarketDataProvider
    calendar: EventCalendar
    store: JournalStore
    config: AppConfig
    capital: float
    open_positions: int | None
    open_risk_pct: float | None
    as_of: date_ | None
    calendar_check: bool


# Analyse `target` and return a journaled TradePlan or NoTrade (INV-4), paired
# with the `as_of` date it was analysed against (see `AdviseResult`).
def advise(
    target: str, *, provider: MarketDataProvider, calendar: EventCalendar,
    store: JournalStore, config: AppConfig, capital: float,
    options: AdviseOptions | None = None,
) -> AdviseResult:
    request = _build_request(
        target, provider, calendar, store, config, capital, options or AdviseOptions()
    )
    return _advise(request)


def _build_request(
    target: str,
    provider: MarketDataProvider,
    calendar: EventCalendar,
    store: JournalStore,
    config: AppConfig,
    capital: float,
    options: AdviseOptions,
) -> _AdviseRequest:
    return _AdviseRequest(
        target, provider, calendar, store, config, capital,
        options.open_positions, options.open_risk_pct, options.as_of, options.calendar_check,
    )


def _advise(request: _AdviseRequest) -> AdviseResult:
    cfd_symbol = request.config.cfd_symbol_for(request.target)
    bars, error = _try_load_bars(request.provider, request.target)
    if bars is None:
        return _journal_no_trade(request, cfd_symbol, error)
    return _advise_with_bars(request, bars, cfd_symbol)


def _try_load_bars(
    provider: MarketDataProvider, target: str
) -> tuple[list[Bar] | None, str | None]:
    try:
        return provider.daily_history(target, days=HISTORY_DAYS), None
    except DataUnavailable as exc:
        return None, exc.reason


def _journal_no_trade(request: _AdviseRequest, cfd_symbol: str, error: str) -> AdviseResult:
    as_of = request.as_of or date_.today()
    no_trade = NoTrade(target=request.target, reason=f"data unavailable: {error}", gates=[])
    request.store.record(no_trade, as_of=as_of, cfd_symbol=cfd_symbol)
    return AdviseResult(plan=no_trade, as_of=as_of, calendar_checked=request.calendar_check)


def _advise_with_bars(
    request: _AdviseRequest, bars: list[Bar], cfd_symbol: str
) -> AdviseResult:
    as_of = request.as_of or bars[-1].date
    veto = (
        _calendar_veto(request.calendar, as_of, request.config.blackout_days, request.target)
        if request.calendar_check else None
    )
    result = veto or _score_and_size(request, bars, as_of)
    request.store.record(result, as_of=as_of, cfd_symbol=cfd_symbol)
    return AdviseResult(plan=result, as_of=as_of, calendar_checked=request.calendar_check)


def _calendar_veto(
    calendar: EventCalendar, as_of: date_, blackout_days: int, target: str
) -> NoTrade | None:
    if calendar.is_stale(as_of):
        return NoTrade(target=target, reason="calendar stale — refresh before trading", gates=[])
    reason = blackout_reason(as_of, calendar.events, blackout_days)
    return NoTrade(target=target, reason=reason, gates=[]) if reason is not None else None


def _score_and_size(request: _AdviseRequest, bars: list[Bar], as_of: date_) -> TradePlan | NoTrade:
    gate = (
        event_gate(as_of, request.calendar.events, request.config.blackout_days)
        if request.calendar_check
        else GateResult(name="event clear", passed=True, detail="calendar check disabled")
    )
    sig_config = SignalConfig(allow_short=request.config.allow_short)
    signal, failing_gates = _evaluate(bars, sig_config, gate)
    if signal is None:
        return NoTrade(target=request.target, reason="no qualifying signal", gates=failing_gates)
    return _size_plan(request, bars, signal)


def _evaluate(
    bars: list[Bar], sig_config: SignalConfig, gate: GateResult
) -> tuple[Signal | None, list[GateResult]]:
    signal = evaluate(bars, sig_config, event_gate=gate)
    if signal is not None:
        return signal, []
    return None, score_gates(bars, Direction.LONG, sig_config, gate)


def _trade_plan_kwargs(
    request: _AdviseRequest, bars: list[Bar], signal: Signal, positions: int, risk_pct: float
) -> dict:
    return dict(
        target=request.target, bars=bars, signal=signal, capital=request.capital,
        risk_pct=request.config.risk_pct, tp_r_multiple=request.config.tp_r_multiple,
        open_positions=positions, open_risk_pct=risk_pct,
    )


def _size_plan(request: _AdviseRequest, bars: list[Bar], signal: Signal) -> TradePlan | NoTrade:
    positions, risk_pct = _resolve_exposure(request)
    kwargs = _trade_plan_kwargs(request, bars, signal, positions, risk_pct)
    return build_trade_plan(**kwargs)


def _resolve_exposure(request: _AdviseRequest) -> tuple[int, float]:
    if request.open_positions is not None and request.open_risk_pct is not None:
        return request.open_positions, request.open_risk_pct
    return request.store.open_exposure()
