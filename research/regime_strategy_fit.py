"""Research-only regime x strategy fit matrix (TACTIC-RA-003).

Builds a DIAGNOSTIC-ONLY matrix of how each strategy resolved within each market
regime, from a list of ``TacticalEvent``s. Per cell it reports the decisive
trade-outcome sample, win/loss counts, and a win rate that is **withheld below
the documented sample floor** (the NEXT-016 >=30 gate). Every low-sample cell is
flagged ``INSUFFICIENT_SAMPLE`` and the whole matrix is ``diagnostic_only`` — a
cell win rate is never upgraded to a trusted strategy edge or a trade signal.

RESEARCH / DIAGNOSTIC-ONLY. This module:

  - computes a descriptive tally only (no recommendations, no optimization),
  - reads ``TacticalEvent`` objects in memory; performs no I/O during compute,
  - imports no broker / order / live-cycle / scheduler / network / subprocess
    module,
  - is NOT wired into ``tools/run_tacticbot.py`` or any scheduler,
  - FAILS CLOSED: an empty input yields an error result; an unknown/None regime
    collapses to a known ``UNKNOWN`` bucket (never a fabricated regime cell),
  - PROPAGATES ``data_is_real`` verbatim from the caller (default ``False``) and
    never invents realness or mixes provenance into a trusted number.

Placed under ``research/`` (not ``core/``) so it is unambiguously offline,
research-only, and unwired; the original TACTIC-RA-003 card suggested a
``core/`` analytics method.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from core.tactic_event import EventType, Outcome, Regime, TacticalEvent

MIN_SAMPLE: int = 30  # NEXT-016 gate: below this, per-cell win rate is withheld
RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"

STATUS_DIAGNOSTIC: str = "DIAGNOSTIC_ONLY"
STATUS_INSUFFICIENT: str = "INSUFFICIENT_SAMPLE"

# Known regime vocabulary (mirrors core.tactic_event.Regime). Anything outside
# this set fails closed to UNKNOWN and is recorded as unrecognized.
KNOWN_REGIMES: frozenset[str] = frozenset(
    {Regime.BULL, Regime.BEAR, Regime.NORMAL, Regime.HIGH_VOL, Regime.LOW_VOL, Regime.UNKNOWN}
)

_DECISIVE = (Outcome.WIN, Outcome.LOSS)


@dataclass(frozen=True)
class FitCell:
    regime: str
    strategy_id: str
    total_events: int          # all events for this (regime, strategy) pair
    sample_count: int          # decisive trade outcomes (WIN + LOSS)
    wins: int
    losses: int
    win_rate: float | None     # None => withheld (below the sample floor)
    win_rate_status: str       # "OK" | "INSUFFICIENT_SAMPLE"
    status: str                # DIAGNOSTIC_ONLY | INSUFFICIENT_SAMPLE


@dataclass(frozen=True)
class RegimeStrategyFit:
    research_only: bool
    broker_execution: str
    diagnostic_only: bool
    status: str                # DIAGNOSTIC_ONLY | INSUFFICIENT_SAMPLE
    data_is_real: bool
    min_sample: int
    regimes: tuple[str, ...]
    strategies: tuple[str, ...]
    cells: dict[str, FitCell]  # key = f"{regime}|{strategy_id}"
    total_events: int
    total_decisive: int
    notes: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    @staticmethod
    def cell_key(regime: str, strategy_id: str) -> str:
        return f"{regime}|{strategy_id}"


def _normalize_regime(raw: str | None) -> tuple[str, bool]:
    """Return (regime, recognized). None/blank/unknown fail closed to UNKNOWN."""
    if raw is None:
        return Regime.UNKNOWN, True  # absence is a known, expected bucket
    text = str(raw).strip().upper()
    if text in KNOWN_REGIMES:
        return text, True
    return Regime.UNKNOWN, False


def build_regime_strategy_fit(
    events: Iterable[TacticalEvent],
    *,
    min_sample: int = MIN_SAMPLE,
    data_is_real: bool = False,
) -> RegimeStrategyFit:
    """Build the regime x strategy fit matrix, failing closed on empty input.

    ``win_rate`` is computed for a cell only when its decisive sample reaches
    ``min_sample``; otherwise it is ``None`` (INSUFFICIENT_SAMPLE). The cell and
    overall ``status`` are INSUFFICIENT_SAMPLE while the decisive sample is below
    the floor — small samples never become a trusted edge. ``data_is_real`` is
    the caller's value, propagated verbatim.
    """
    event_list = list(events)

    if not event_list:
        return RegimeStrategyFit(
            research_only=RESEARCH_ONLY,
            broker_execution=BROKER_EXECUTION,
            diagnostic_only=True,
            status=STATUS_INSUFFICIENT,
            data_is_real=False,
            min_sample=min_sample,
            regimes=(),
            strategies=(),
            cells={},
            total_events=0,
            total_decisive=0,
            notes=("no events provided",),
            errors=("no events provided",),
        )

    # Aggregate per (regime, strategy).
    agg: dict[tuple[str, str], dict[str, int]] = {}
    regimes: set[str] = set()
    strategies: set[str] = set()
    unrecognized: list[str] = []

    for e in event_list:
        regime, recognized = _normalize_regime(e.regime)
        if not recognized and str(e.regime) not in unrecognized:
            unrecognized.append(str(e.regime))
        strat = e.strategy_id
        regimes.add(regime)
        strategies.add(strat)

        cell = agg.setdefault((regime, strat), {"total": 0, "wins": 0, "losses": 0})
        cell["total"] += 1
        if e.event_type == EventType.TRADE_OUTCOME and e.outcome in _DECISIVE:
            if e.outcome == Outcome.WIN:
                cell["wins"] += 1
            else:
                cell["losses"] += 1

    cells: dict[str, FitCell] = {}
    total_decisive = 0
    for (regime, strat) in sorted(agg):
        c = agg[(regime, strat)]
        wins, losses = c["wins"], c["losses"]
        decisive = wins + losses
        total_decisive += decisive

        if decisive >= min_sample:
            win_rate: float | None = round(wins / decisive, 4)
            win_rate_status = "OK"
            cell_status = STATUS_DIAGNOSTIC
        else:
            win_rate = None
            win_rate_status = STATUS_INSUFFICIENT
            cell_status = STATUS_INSUFFICIENT

        cells[RegimeStrategyFit.cell_key(regime, strat)] = FitCell(
            regime=regime,
            strategy_id=strat,
            total_events=c["total"],
            sample_count=decisive,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            win_rate_status=win_rate_status,
            status=cell_status,
        )

    overall_status = STATUS_DIAGNOSTIC if total_decisive >= min_sample else STATUS_INSUFFICIENT

    notes: list[str] = [
        f"DIAGNOSTIC_ONLY: regime x strategy fit over {len(event_list)} event(s); "
        f"descriptive tally, not a strategy edge and not trading advice."
    ]
    if unrecognized:
        notes.append(f"unrecognized regimes treated as UNKNOWN: {unrecognized}")
    if overall_status == STATUS_INSUFFICIENT:
        notes.append(
            f"INSUFFICIENT_SAMPLE: {total_decisive} decisive outcome(s) < min_sample "
            f"{min_sample}; per-cell win rates are withheld and nothing here is a trusted edge."
        )

    return RegimeStrategyFit(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        diagnostic_only=True,
        status=overall_status,
        data_is_real=bool(data_is_real),  # propagated, never invented
        min_sample=min_sample,
        regimes=tuple(sorted(regimes)),
        strategies=tuple(sorted(strategies)),
        cells=cells,
        total_events=len(event_list),
        total_decisive=total_decisive,
        notes=tuple(notes),
    )
