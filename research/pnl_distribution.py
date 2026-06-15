"""Research-only PnL distribution analysis (TACTIC-HA-006).

Builds a DIAGNOSTIC-ONLY descriptive distribution of realized PnL over a list of
``TacticalEvent`` trade outcomes: a histogram, count/mean/median/min/max/stdev,
a win/loss/breakeven split, and a small per-strategy summary.

RESEARCH / DIAGNOSTIC-ONLY. This module:

  - computes a *descriptive* tally only (no recommendation, no forecast, no edge),
  - reads ``TacticalEvent`` objects in memory; performs no I/O during compute,
  - imports no broker / order / live-cycle / scheduler / network / subprocess
    module (only the stdlib ``statistics``),
  - is NOT wired into ``tools/run_tacticbot.py``, the analytics engine, or any
    scheduler,
  - FAILS CLOSED: empty input, or no realized-PnL values, yields an error result
    with no fabricated statistics; ``NaN`` PnL values are skipped, never counted,
  - is sample-aware: below ``min_sample`` the overall ``status`` is
    ``INSUFFICIENT_SAMPLE`` (descriptive numbers are facts about the sample, never
    a predictive edge),
  - PROPAGATES ``data_is_real`` verbatim from the caller (default ``False``).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Iterable

from core.tactic_event import EventType, Outcome, TacticalEvent

RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"

STATUS_DIAGNOSTIC: str = "DIAGNOSTIC_ONLY"
STATUS_INSUFFICIENT: str = "INSUFFICIENT_SAMPLE"

DEFAULT_MIN_SAMPLE: int = 30   # NEXT-016 floor for treating the sample as non-trivial
DEFAULT_BUCKET_COUNT: int = 6


@dataclass(frozen=True)
class PnlBucket:
    label: str
    low: float
    high: float
    count: int


@dataclass(frozen=True)
class StrategyPnlSummary:
    strategy_id: str
    sample_count: int
    wins: int
    losses: int
    mean_pnl: float | None
    total_pnl: float


@dataclass(frozen=True)
class PnlDistribution:
    research_only: bool
    broker_execution: str
    diagnostic_only: bool
    status: str                 # DIAGNOSTIC_ONLY | INSUFFICIENT_SAMPLE
    data_is_real: bool
    min_sample: int
    sample_count: int           # TRADE_OUTCOME events with a finite realized_pnl
    wins: int
    losses: int
    breakevens: int
    total_pnl: float
    mean_pnl: float | None
    median_pnl: float | None
    min_pnl: float | None
    max_pnl: float | None
    stdev_pnl: float | None     # population stdev; None when sample_count < 2
    buckets: tuple[PnlBucket, ...]
    by_strategy: dict[str, StrategyPnlSummary]
    notes: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _histogram(values: list[float], bucket_count: int) -> tuple[PnlBucket, ...]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return (PnlBucket(label=f"[{lo:.4g}]", low=round(lo, 6), high=round(lo, 6), count=len(values)),)

    width = (hi - lo) / bucket_count
    buckets: list[PnlBucket] = []
    for i in range(bucket_count):
        b_lo = lo + i * width
        b_hi = lo + (i + 1) * width if i < bucket_count - 1 else hi
        if i < bucket_count - 1:
            count = sum(1 for v in values if b_lo <= v < b_hi)
            closer = ")"
        else:
            count = sum(1 for v in values if b_lo <= v <= b_hi)
            closer = "]"
        buckets.append(
            PnlBucket(
                label=f"[{b_lo:.4g}, {b_hi:.4g}{closer}",
                low=round(b_lo, 6),
                high=round(b_hi, 6),
                count=count,
            )
        )
    return tuple(buckets)


def _fail_closed(reason: str, *, min_sample: int) -> PnlDistribution:
    return PnlDistribution(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        diagnostic_only=True,
        status=STATUS_INSUFFICIENT,
        data_is_real=False,
        min_sample=min_sample,
        sample_count=0,
        wins=0,
        losses=0,
        breakevens=0,
        total_pnl=0.0,
        mean_pnl=None,
        median_pnl=None,
        min_pnl=None,
        max_pnl=None,
        stdev_pnl=None,
        buckets=(),
        by_strategy={},
        notes=(reason,),
        errors=(reason,),
    )


def build_pnl_distribution(
    events: Iterable[TacticalEvent],
    *,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    data_is_real: bool = False,
) -> PnlDistribution:
    """Build a descriptive realized-PnL distribution, failing closed on no data.

    The sample is the set of ``TRADE_OUTCOME`` events whose ``realized_pnl`` is a
    finite number. Descriptive statistics are computed over that sample; below
    ``min_sample`` the overall ``status`` is ``INSUFFICIENT_SAMPLE``. Nothing here
    is a forecast or an edge. ``data_is_real`` is the caller's value, verbatim.
    """
    event_list = list(events)
    if not event_list:
        return _fail_closed("no events provided", min_sample=min_sample)

    bucket_count = max(1, int(bucket_count))

    pnl_values: list[float] = []
    wins = losses = breakevens = 0
    per_strategy: dict[str, dict[str, float]] = {}

    for e in event_list:
        if e.event_type != EventType.TRADE_OUTCOME:
            continue
        if not _is_finite_number(e.realized_pnl):
            continue
        pnl = float(e.realized_pnl)
        pnl_values.append(pnl)

        if e.outcome == Outcome.WIN:
            wins += 1
        elif e.outcome == Outcome.LOSS:
            losses += 1
        elif e.outcome == Outcome.BREAKEVEN:
            breakevens += 1

        s = per_strategy.setdefault(e.strategy_id, {"n": 0, "wins": 0, "losses": 0, "total": 0.0})
        s["n"] += 1
        s["total"] += pnl
        if e.outcome == Outcome.WIN:
            s["wins"] += 1
        elif e.outcome == Outcome.LOSS:
            s["losses"] += 1

    if not pnl_values:
        return _fail_closed("no realized PnL values found in trade outcomes", min_sample=min_sample)

    sample_count = len(pnl_values)
    total_pnl = round(sum(pnl_values), 6)
    mean_pnl = round(statistics.fmean(pnl_values), 6)
    median_pnl = round(statistics.median(pnl_values), 6)
    min_pnl = round(min(pnl_values), 6)
    max_pnl = round(max(pnl_values), 6)
    stdev_pnl = round(statistics.pstdev(pnl_values), 6) if sample_count >= 2 else None

    by_strategy = {
        sid: StrategyPnlSummary(
            strategy_id=sid,
            sample_count=int(d["n"]),
            wins=int(d["wins"]),
            losses=int(d["losses"]),
            mean_pnl=round(d["total"] / d["n"], 6) if d["n"] else None,
            total_pnl=round(d["total"], 6),
        )
        for sid, d in sorted(per_strategy.items())
    }

    status = STATUS_DIAGNOSTIC if sample_count >= min_sample else STATUS_INSUFFICIENT

    notes: list[str] = [
        f"DIAGNOSTIC_ONLY: descriptive realized-PnL distribution over {sample_count} "
        f"trade outcome(s); not a forecast, not an edge, not trading advice."
    ]
    if status == STATUS_INSUFFICIENT:
        notes.append(
            f"INSUFFICIENT_SAMPLE: {sample_count} PnL value(s) < min_sample {min_sample}; "
            f"these descriptive numbers must not be read as a trusted edge."
        )

    return PnlDistribution(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        diagnostic_only=True,
        status=status,
        data_is_real=bool(data_is_real),  # propagated, never invented
        min_sample=min_sample,
        sample_count=sample_count,
        wins=wins,
        losses=losses,
        breakevens=breakevens,
        total_pnl=total_pnl,
        mean_pnl=mean_pnl,
        median_pnl=median_pnl,
        min_pnl=min_pnl,
        max_pnl=max_pnl,
        stdev_pnl=stdev_pnl,
        buckets=_histogram(pnl_values, bucket_count),
        by_strategy=by_strategy,
        notes=tuple(notes),
    )
