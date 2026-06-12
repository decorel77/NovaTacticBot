"""Statistical floor for tactical signal evidence (QA-016).

Pure advisory/design-safe layer. This module is intentionally not wired into
the runner, snapshot writer, or any execution path. The report generator may
display precomputed results, but it does not compute them by default. This
module only answers whether a tactical signal has enough evidence to be
labelled strong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Mapping

from core.tactic_event import TacticalEvent


APPROVED_STRENGTH = "STRONG"
DIAGNOSTIC_STRENGTH = "DIAGNOSTIC_ONLY"


@dataclass(frozen=True)
class StatisticalFloorConfig:
    """Conservative defaults until the floor is calibrated against history."""

    min_sample_size: int = 30
    min_confidence: float = 0.70
    min_win_rate: float = 0.55
    min_edge: float = 0.02
    max_staleness_hours: int = 168
    require_real_data: bool = True
    require_verified_regime_for_exposure_increase: bool = True
    known_regimes: frozenset[str] = frozenset(
        {"BULL", "BEAR", "NORMAL", "HIGH_VOL", "LOW_VOL", "SIDEWAYS", "HIGH_VOLATILITY"}
    )


@dataclass(frozen=True)
class TacticalSignalEvidence:
    """Evidence bundle for a candidate tactical signal.

    Numeric confidence and win-rate fields use 0.0-1.0, matching
    ``TacticalEvent.score``. ``edge`` is a decimal expected edge, not percent.
    """

    signal_id: str
    strategy_id: str
    sample_size: Any
    confidence: Any
    win_rate: Any | None = None
    edge: Any | None = None
    produced_at: Any | None = None
    fresh_until: Any | None = None
    data_is_real: Any = False
    regime: str | None = None
    regime_verified: Any = False
    exposure_increasing: bool = True
    input_source: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StatisticalFloorResult:
    """Advisory result from the statistical floor."""

    approved: bool
    strength: str
    reason: str
    signal_id: str | None = None
    strategy_id: str | None = None
    refusal_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
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
            "approved": self.approved,
            "strength": self.strength,
            "reason": self.reason,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "refusal_reasons": list(self.refusal_reasons),
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics),
            "advisory_only": self.advisory_only,
            "diagnostic_only": self.diagnostic_only,
            "design_only": self.design_only,
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "allocation_change_enabled": self.allocation_change_enabled,
            "downstream_export_enabled": self.downstream_export_enabled,
        }


def evaluate_statistical_floor(
    evidence: TacticalSignalEvidence,
    *,
    now: datetime | None = None,
    config: StatisticalFloorConfig | None = None,
) -> StatisticalFloorResult:
    """Evaluate whether signal evidence may be treated as strong.

    Any missing, invalid, fake, stale, or regime-unsafe evidence fails closed to
    diagnostic-only. This function never writes files and never calls external
    systems.
    """

    cfg = config or StatisticalFloorConfig()
    current = _coerce_utc(now)
    refusals: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {
        "input_source": evidence.input_source,
        "exposure_increasing": bool(evidence.exposure_increasing),
    }

    sample_size = _strict_int(evidence.sample_size)
    if sample_size is None:
        refusals.append("sample_size_invalid")
    else:
        metrics["sample_size"] = sample_size
        if sample_size < cfg.min_sample_size:
            refusals.append(f"sample_size_below_floor:{sample_size}<{cfg.min_sample_size}")

    confidence = _strict_unit_float(evidence.confidence)
    if confidence is None:
        refusals.append("confidence_invalid")
    else:
        metrics["confidence"] = confidence
        if confidence < cfg.min_confidence:
            refusals.append(f"confidence_below_floor:{confidence:.4f}<{cfg.min_confidence:.4f}")

    win_rate = _strict_optional_unit_float(evidence.win_rate)
    edge = _strict_optional_float(evidence.edge)
    if evidence.win_rate is not None and win_rate is None:
        refusals.append("win_rate_invalid")
    if evidence.edge is not None and edge is None:
        refusals.append("edge_invalid")
    if win_rate is None and edge is None:
        refusals.append("edge_or_win_rate_missing")
    if win_rate is not None:
        metrics["win_rate"] = win_rate
        if win_rate < cfg.min_win_rate:
            refusals.append(f"win_rate_below_floor:{win_rate:.4f}<{cfg.min_win_rate:.4f}")
    if edge is not None:
        metrics["edge"] = edge
        if edge < cfg.min_edge:
            refusals.append(f"edge_below_floor:{edge:.4f}<{cfg.min_edge:.4f}")

    if cfg.require_real_data and evidence.data_is_real is not True:
        refusals.append("data_not_real")

    freshness_refusals, freshness_metrics = _freshness_refusals(
        evidence.produced_at,
        evidence.fresh_until,
        now=current,
        max_staleness_hours=cfg.max_staleness_hours,
    )
    refusals.extend(freshness_refusals)
    metrics.update(freshness_metrics)

    regime = _regime_label(evidence.regime)
    metrics["regime"] = regime
    if evidence.exposure_increasing and cfg.require_verified_regime_for_exposure_increase:
        if regime in ("", "UNKNOWN") or regime not in cfg.known_regimes:
            refusals.append(f"regime_unknown_or_unsupported:{regime or 'UNKNOWN'}")
        if evidence.regime_verified is not True:
            refusals.append("regime_not_verified")
    elif regime in ("", "UNKNOWN") or regime not in cfg.known_regimes:
        warnings.append(f"regime_diagnostic_only:{regime or 'UNKNOWN'}")

    unique_refusals = tuple(dict.fromkeys(refusals))
    unique_warnings = tuple(dict.fromkeys(warnings))
    approved = not unique_refusals
    strength = APPROVED_STRENGTH if approved else DIAGNOSTIC_STRENGTH
    reason = (
        "Statistical floor passed; signal may be labelled STRONG for advisory reporting."
        if approved
        else "Statistical floor refused strong classification; diagnostic-only."
    )

    return StatisticalFloorResult(
        approved=approved,
        strength=strength,
        reason=reason,
        signal_id=evidence.signal_id,
        strategy_id=evidence.strategy_id,
        refusal_reasons=unique_refusals,
        warnings=unique_warnings,
        metrics=metrics,
        diagnostic_only=not approved,
    )


def evidence_from_event(
    event: TacticalEvent,
    *,
    sample_size: Any | None = None,
    win_rate: Any | None = None,
    edge: Any | None = None,
    data_is_real: Any | None = None,
    regime_verified: Any | None = None,
    exposure_increasing: bool | None = None,
) -> TacticalSignalEvidence:
    """Build evidence from a TacticalEvent plus optional explicit overrides.

    Metadata keys are read only when the corresponding override is omitted:
    ``sample_size``, ``win_rate``, ``edge``, ``data_is_real``,
    ``regime_verified``, ``exposure_increasing``, ``produced_at``,
    ``fresh_until``, and ``input_source``.
    """

    metadata = event.metadata or {}
    return TacticalSignalEvidence(
        signal_id=str(event.event_id),
        strategy_id=str(event.strategy_id),
        sample_size=sample_size if sample_size is not None else metadata.get("sample_size"),
        confidence=event.score if event.score is not None else metadata.get("confidence"),
        win_rate=win_rate if win_rate is not None else metadata.get("win_rate"),
        edge=edge if edge is not None else metadata.get("edge"),
        produced_at=metadata.get("produced_at") or event.timestamp,
        fresh_until=metadata.get("fresh_until"),
        data_is_real=data_is_real if data_is_real is not None else metadata.get("data_is_real"),
        regime=event.regime,
        regime_verified=(
            regime_verified if regime_verified is not None else metadata.get("regime_verified")
        ),
        exposure_increasing=(
            exposure_increasing
            if exposure_increasing is not None
            else metadata.get("exposure_increasing", True)
        ),
        input_source=str(metadata.get("input_source") or event.source_bot or "unknown"),
        metadata=metadata,
    )


def _strict_int(value: Any) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _strict_unit_float(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    converted = float(value)
    if not isfinite(converted) or not 0.0 <= converted <= 1.0:
        return None
    return converted


def _strict_optional_unit_float(value: Any) -> float | None:
    if value is None:
        return None
    return _strict_unit_float(value)


def _strict_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        return None
    converted = float(value)
    if not isfinite(converted):
        return None
    return converted


def _freshness_refusals(
    produced_at_raw: Any,
    fresh_until_raw: Any,
    *,
    now: datetime,
    max_staleness_hours: int,
) -> tuple[list[str], dict[str, Any]]:
    metrics: dict[str, Any] = {}
    produced_at = _parse_timestamp(produced_at_raw)
    if produced_at is None:
        return ["produced_at_missing_or_invalid"], metrics

    metrics["produced_at"] = produced_at.isoformat()
    if produced_at > now:
        return ["produced_at_future"], metrics

    refusals: list[str] = []
    age_hours = (now - produced_at).total_seconds() / 3600
    metrics["age_hours"] = round(age_hours, 4)
    if age_hours > max_staleness_hours:
        refusals.append(f"evidence_stale:{age_hours:.2f}>{max_staleness_hours}")

    if fresh_until_raw is not None:
        fresh_until = _parse_timestamp(fresh_until_raw)
        if fresh_until is None:
            refusals.append("fresh_until_invalid")
        else:
            metrics["fresh_until"] = fresh_until.isoformat()
            if fresh_until < now and not any(r.startswith("evidence_stale:") for r in refusals):
                refusals.append("evidence_stale:fresh_until_expired")

    return refusals, metrics


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _regime_label(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return "UNKNOWN"
    return value.strip().upper()
