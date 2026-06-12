"""Strategy outcome correlation diagnostic (QA-019).

Pure advisory/design-safe research layer. This module is intentionally not
wired into the runner, snapshot writer, or any execution path. The report
generator may display precomputed results, but it does not compute them by
default. It only measures correlation between two trade-outcome event streams
(e.g. NovaBotV2 vs NovaBotV2Options) so that "diversification" claims can be
checked instead of assumed.

Follows the QA-016 statistical floor pattern: deterministic, offline,
pure-python, fail-closed on missing/fake/invalid evidence, and gated by a
minimum-sample floor before any correlation number may be reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from math import atanh, isfinite, sqrt, tanh
from typing import Any, Iterable

from core.tactic_event import EventType, Outcome, TacticalEvent


CORRELATION_SCHEMA_VERSION = "strategy_correlation.v1"


@dataclass(frozen=True)
class StrategyCorrelationConfig:
    """Conservative defaults; aligned with the QA-016 statistical floor."""

    min_overlap_days: int = 30
    rolling_window_days: int = 30
    require_real_data: bool = True
    confidence_z: float = 1.96
    small_sample_warning_below: int = 60


@dataclass(frozen=True)
class RollingCorrelationPoint:
    """Correlation over one trailing window of overlapping outcome days."""

    window_end: str
    window_days: int
    overlap_days: int
    correlation: float | None
    insufficient_sample: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_end": self.window_end,
            "window_days": self.window_days,
            "overlap_days": self.overlap_days,
            "correlation": self.correlation,
            "insufficient_sample": self.insufficient_sample,
        }


@dataclass(frozen=True)
class StrategyCorrelationResult:
    """Advisory diagnostic result. Never an instruction to act."""

    computed: bool
    insufficient_sample: bool
    correlation: float | None
    ci_low: float | None
    ci_high: float | None
    overlap_days: int
    source_a: str
    source_b: str
    events_used_a: int = 0
    events_used_b: int = 0
    excluded_events: dict[str, int] = field(default_factory=dict)
    rolling: tuple[RollingCorrelationPoint, ...] = ()
    refusal_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    schema_version: str = CORRELATION_SCHEMA_VERSION
    advisory_only: bool = True
    diagnostic_only: bool = True
    design_only: bool = True
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    live_trading_enabled: bool = False
    allocation_change_enabled: bool = False
    downstream_export_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "computed": self.computed,
            "insufficient_sample": self.insufficient_sample,
            "correlation": self.correlation,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "overlap_days": self.overlap_days,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "events_used_a": self.events_used_a,
            "events_used_b": self.events_used_b,
            "excluded_events": dict(self.excluded_events),
            "rolling": [point.to_dict() for point in self.rolling],
            "refusal_reasons": list(self.refusal_reasons),
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
            "advisory_only": self.advisory_only,
            "diagnostic_only": self.diagnostic_only,
            "design_only": self.design_only,
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "allocation_change_enabled": self.allocation_change_enabled,
            "downstream_export_enabled": self.downstream_export_enabled,
        }


_STANDING_CAVEATS = (
    "Diagnostic only: correlation describes the past sample, not future co-movement.",
    "Correlation below 1.0 is not proof of diversification; both books share market beta.",
    "Daily-aggregated realized PnL hides intraday co-movement and overlapping holding periods.",
)


def compute_strategy_correlation(
    events_a: Iterable[TacticalEvent],
    events_b: Iterable[TacticalEvent],
    *,
    source_a: str = "NovaBotV2",
    source_b: str = "NovaBotV2Options",
    config: StrategyCorrelationConfig | None = None,
) -> StrategyCorrelationResult:
    """Correlate two trade-outcome streams on daily realized PnL.

    Any missing, fake, pending, or numerically invalid outcome is excluded
    fail-closed (counted in ``excluded_events``). No correlation value is
    reported below the minimum-overlap floor. This function never writes
    files and never calls external systems.
    """

    cfg = config or StrategyCorrelationConfig()
    excluded: dict[str, int] = {}

    daily_a, used_a = _daily_pnl(events_a, cfg, excluded)
    daily_b, used_b = _daily_pnl(events_b, cfg, excluded)

    overlap_dates = sorted(set(daily_a) & set(daily_b))
    overlap_days = len(overlap_dates)
    series_a = [daily_a[day] for day in overlap_dates]
    series_b = [daily_b[day] for day in overlap_dates]

    refusals: list[str] = []
    warnings: list[str] = []
    insufficient = overlap_days < cfg.min_overlap_days
    if insufficient:
        refusals.append(
            f"insufficient_overlap:{overlap_days}<{cfg.min_overlap_days}"
        )

    correlation: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    if not insufficient:
        correlation = _pearson(series_a, series_b)
        if correlation is None:
            refusals.append("correlation_undefined:constant_series")
        else:
            ci_low, ci_high = _fisher_interval(
                correlation, overlap_days, cfg.confidence_z
            )
            if ci_low is None:
                warnings.append("ci_unavailable_extreme_correlation")
        if overlap_days < cfg.small_sample_warning_below:
            warnings.append(
                f"small_sample:{overlap_days}<{cfg.small_sample_warning_below}"
            )

    rolling = _rolling_correlations(overlap_dates, series_a, series_b, cfg)

    return StrategyCorrelationResult(
        computed=correlation is not None,
        insufficient_sample=insufficient,
        correlation=correlation,
        ci_low=ci_low,
        ci_high=ci_high,
        overlap_days=overlap_days,
        source_a=source_a,
        source_b=source_b,
        events_used_a=used_a,
        events_used_b=used_b,
        excluded_events=excluded,
        rolling=rolling,
        refusal_reasons=tuple(dict.fromkeys(refusals)),
        warnings=tuple(dict.fromkeys(warnings)),
        caveats=_STANDING_CAVEATS,
    )


def render_markdown_section(result: StrategyCorrelationResult) -> str:
    """Render the diagnostic as a report section string.

    Pure string builder for display-only report integration. Nothing in the
    default runner computes or passes this result; production data wiring is a
    separate, explicitly-approved task (see docs/architecture/strategy_correlation.md).
    """

    lines = [
        "## Strategy Outcome Correlation (diagnostic only)",
        "",
        f"Streams: `{result.source_a}` vs `{result.source_b}` "
        f"({result.overlap_days} overlapping outcome days)",
        "",
    ]
    if result.insufficient_sample or result.correlation is None:
        lines.append(
            "**INSUFFICIENT SAMPLE — no correlation value is reported.** "
            "Reasons: " + (", ".join(result.refusal_reasons) or "none recorded")
        )
    else:
        interval = (
            f" (95% CI [{result.ci_low:+.2f}, {result.ci_high:+.2f}])"
            if result.ci_low is not None and result.ci_high is not None
            else " (interval unavailable)"
        )
        lines.append(
            f"Daily realized-PnL correlation: **{result.correlation:+.2f}**{interval}"
        )
    if result.warnings:
        lines.append("")
        lines.append("Warnings: " + ", ".join(result.warnings))
    lines.append("")
    lines.append("Caveats:")
    for caveat in result.caveats:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def _daily_pnl(
    events: Iterable[TacticalEvent],
    cfg: StrategyCorrelationConfig,
    excluded: dict[str, int],
) -> tuple[dict[date, float], int]:
    daily: dict[date, float] = {}
    used = 0
    for event in events:
        reason = _exclusion_reason(event, cfg)
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        day = _utc_day(event.timestamp)
        daily[day] = daily.get(day, 0.0) + float(event.realized_pnl)
        used += 1
    return daily, used


def _exclusion_reason(
    event: TacticalEvent, cfg: StrategyCorrelationConfig
) -> str | None:
    if event.event_type != EventType.TRADE_OUTCOME:
        return "not_trade_outcome"
    if event.outcome == Outcome.PENDING:
        return "outcome_pending"
    if not isinstance(event.timestamp, datetime):
        return "timestamp_invalid"
    pnl = event.realized_pnl
    if type(pnl) not in (int, float) or not isfinite(float(pnl)):
        return "realized_pnl_missing_or_invalid"
    if cfg.require_real_data and (event.metadata or {}).get("data_is_real") is not True:
        return "data_not_real"
    return None


def _utc_day(timestamp: datetime) -> date:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc).date()
    return timestamp.astimezone(timezone.utc).date()


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0.0 or var_y == 0.0:
        return None
    r = cov / sqrt(var_x * var_y)
    return max(-1.0, min(1.0, r))


def _fisher_interval(
    r: float, n: int, z: float
) -> tuple[float | None, float | None]:
    if n < 4 or abs(r) >= 1.0:
        return None, None
    transformed = atanh(r)
    se = 1.0 / sqrt(n - 3)
    return tanh(transformed - z * se), tanh(transformed + z * se)


def _rolling_correlations(
    overlap_dates: list[date],
    series_a: list[float],
    series_b: list[float],
    cfg: StrategyCorrelationConfig,
) -> tuple[RollingCorrelationPoint, ...]:
    window = cfg.rolling_window_days
    points: list[RollingCorrelationPoint] = []
    if window < 2:
        return ()
    below_floor = window < cfg.min_overlap_days
    for end in range(window, len(overlap_dates) + 1):
        start = end - window
        r = None if below_floor else _pearson(series_a[start:end], series_b[start:end])
        points.append(
            RollingCorrelationPoint(
                window_end=overlap_dates[end - 1].isoformat(),
                window_days=window,
                overlap_days=window,
                correlation=r,
                insufficient_sample=below_floor,
            )
        )
    return tuple(points)
