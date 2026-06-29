"""Research-only holding-period analytics (TACTIC-HA-007).

Builds a DIAGNOSTIC-ONLY descriptive summary of trade holding periods from a list
of ``TacticalEvent`` trade outcomes that carry ``entry_time`` / ``exit_time`` in
their ``metadata``. It reports per-strategy and overall holding-period stats
(count / mean / median / min / max, in days).

RESEARCH / DIAGNOSTIC-ONLY. This module:

  - computes a *descriptive* tally only (no forecast, no edge, no recommendation),
  - reads ``TacticalEvent`` objects in memory; performs no I/O during compute,
  - imports no broker / order / live-cycle / scheduler / network / subprocess
    module (only the stdlib ``datetime`` and ``statistics``),
  - is NOT wired into ``tools/run_tacticbot.py``, the analytics engine, or any
    scheduler,
  - NEVER fabricates timestamps: an outcome missing/unparseable ``entry_time`` or
    ``exit_time`` is **skipped** (counted in ``skipped_missing``); an
    ``exit_time <= entry_time`` (or mismatched tz-awareness) span is **skipped**
    (counted in ``skipped_invalid_span``) rather than producing a negative or
    invented duration,
  - FAILS CLOSED: empty input, or no valid holding periods, yields an error result
    with no statistics,
  - is sample-aware (``INSUFFICIENT_SAMPLE`` below ``min_sample``) and PROPAGATES
    ``data_is_real`` verbatim from the caller (default ``False``).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from core.tactic_event import EventType, TacticalEvent

RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"

STATUS_DIAGNOSTIC: str = "DIAGNOSTIC_ONLY"
STATUS_INSUFFICIENT: str = "INSUFFICIENT_SAMPLE"

DEFAULT_MIN_SAMPLE: int = 30  # NEXT-016 floor for treating the sample as non-trivial

_SECONDS_PER_DAY: float = 86400.0


@dataclass(frozen=True)
class StrategyHoldingSummary:
    strategy_id: str
    sample_count: int
    mean_days: float | None
    median_days: float | None
    min_days: float | None
    max_days: float | None


@dataclass(frozen=True)
class HoldingPeriodAnalysis:
    research_only: bool
    broker_execution: str
    diagnostic_only: bool
    status: str                 # DIAGNOSTIC_ONLY | INSUFFICIENT_SAMPLE
    data_is_real: bool
    min_sample: int
    sample_count: int           # outcomes with a valid (positive) holding period
    mean_days: float | None
    median_days: float | None
    min_days: float | None
    max_days: float | None
    by_strategy: dict[str, StrategyHoldingSummary]
    skipped_missing: int        # outcomes missing/unparseable entry or exit time
    skipped_invalid_span: int   # exit <= entry, or mismatched tz-awareness
    notes: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _holding_days(entry: datetime, exit_: datetime) -> float | None:
    """Positive holding period in days, or None for an invalid span.

    Returns None on ``exit <= entry`` or on mismatched tz-awareness (subtracting
    a naive and an aware datetime), so an invalid span is never fabricated.
    """
    try:
        seconds = (exit_ - entry).total_seconds()
    except TypeError:
        return None
    if seconds <= 0:
        return None
    return seconds / _SECONDS_PER_DAY


def _summary_stats(values: list[float]) -> tuple[float, float, float, float]:
    return (
        round(statistics.fmean(values), 6),
        round(statistics.median(values), 6),
        round(min(values), 6),
        round(max(values), 6),
    )


def _fail_closed(reason: str, *, min_sample: int, skipped_missing: int = 0, skipped_invalid: int = 0) -> HoldingPeriodAnalysis:
    return HoldingPeriodAnalysis(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        diagnostic_only=True,
        status=STATUS_INSUFFICIENT,
        data_is_real=False,
        min_sample=min_sample,
        sample_count=0,
        mean_days=None,
        median_days=None,
        min_days=None,
        max_days=None,
        by_strategy={},
        skipped_missing=skipped_missing,
        skipped_invalid_span=skipped_invalid,
        notes=(reason,),
        errors=(reason,),
    )


def build_holding_period_analysis(
    events: Iterable[TacticalEvent],
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    data_is_real: bool = False,
) -> HoldingPeriodAnalysis:
    """Build a descriptive holding-period summary, failing closed on no data.

    Only ``TRADE_OUTCOME`` events with both a parseable ``entry_time`` and
    ``exit_time`` in metadata and a positive span contribute. Nothing here is a
    forecast or an edge. ``data_is_real`` is the caller's value, verbatim.
    """
    event_list = list(events)
    if not event_list:
        return _fail_closed("no events provided", min_sample=min_sample)

    durations: list[float] = []
    per_strategy: dict[str, list[float]] = {}
    skipped_missing = 0
    skipped_invalid = 0

    for e in event_list:
        # Fail-closed on a non-event item (None / dict / str): skip it rather
        # than raising AttributeError on a malformed stream.
        if getattr(e, "event_type", None) != EventType.TRADE_OUTCOME:
            continue
        md = e.metadata or {}
        entry = _parse_dt(md.get("entry_time"))
        exit_ = _parse_dt(md.get("exit_time"))
        if entry is None or exit_ is None:
            skipped_missing += 1
            continue
        days = _holding_days(entry, exit_)
        if days is None:
            skipped_invalid += 1
            continue
        durations.append(days)
        per_strategy.setdefault(e.strategy_id, []).append(days)

    if not durations:
        return _fail_closed(
            "no valid holding periods found",
            min_sample=min_sample,
            skipped_missing=skipped_missing,
            skipped_invalid=skipped_invalid,
        )

    sample_count = len(durations)
    mean_days, median_days, min_days, max_days = _summary_stats(durations)

    by_strategy = {}
    for sid, vals in sorted(per_strategy.items()):
        s_mean, s_median, s_min, s_max = _summary_stats(vals)
        by_strategy[sid] = StrategyHoldingSummary(
            strategy_id=sid,
            sample_count=len(vals),
            mean_days=s_mean,
            median_days=s_median,
            min_days=s_min,
            max_days=s_max,
        )

    status = STATUS_DIAGNOSTIC if sample_count >= min_sample else STATUS_INSUFFICIENT

    notes: list[str] = [
        f"DIAGNOSTIC_ONLY: descriptive holding-period summary over {sample_count} "
        f"trade outcome(s); not a forecast, not an edge, not trading advice."
    ]
    if skipped_missing or skipped_invalid:
        notes.append(
            f"skipped {skipped_missing} outcome(s) with missing/unparseable timestamps "
            f"and {skipped_invalid} with a non-positive/invalid span (failed closed, never fabricated)."
        )
    if status == STATUS_INSUFFICIENT:
        notes.append(
            f"INSUFFICIENT_SAMPLE: {sample_count} holding period(s) < min_sample {min_sample}; "
            f"these descriptive numbers must not be read as a trusted edge."
        )

    return HoldingPeriodAnalysis(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        diagnostic_only=True,
        status=status,
        data_is_real=bool(data_is_real),  # propagated, never invented
        min_sample=min_sample,
        sample_count=sample_count,
        mean_days=mean_days,
        median_days=median_days,
        min_days=min_days,
        max_days=max_days,
        by_strategy=by_strategy,
        skipped_missing=skipped_missing,
        skipped_invalid_span=skipped_invalid,
        notes=tuple(notes),
    )
