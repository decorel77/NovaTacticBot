"""Offline RESEARCH-ONLY indicator prototypes (TA-004): MACD, Bollinger, volume trend.

A deterministic, pure-arithmetic research module that computes a few classic
technical indicators that the live NovaBotV2 path deliberately does **not** use
(its live set is EMA20/EMA50 + RSI + ATR - see NovaBotV2 docs/ta_indicator_
production_path.md). This module exists only so Nova can *study* whether such
indicators add anything; it is NOT a trading signal and claims no edge.

It is RESEARCH-ONLY and completely separate from any live path:

  - it reads only in-memory numbers (lists of closes / volumes) - no fixtures
    needed, no I/O during compute,
  - it places no orders and connects to no broker / data feed / network,
  - it imports no broker / order / live-cycle / scheduler / subprocess modules,
    and depends on nothing beyond the stdlib (no pandas / numpy),
  - it is NOT wired into ``tools/run_tacticbot.py`` or any scheduler, and must not
    be added to ``build_indicator_frame`` / ``detect_setup`` / the market scanner,
  - it touches no risk, capital, or position-sizing setting,
  - it FAILS CLOSED: on invalid / insufficient / non-finite input it reports a
    ``fail_closed_reason`` with ``status="FAIL_CLOSED"`` and null values rather
    than fabricating a number.

Given the same inputs it always produces the same numbers: no wall-clock, no
randomness. The output is descriptive evidence, never a trade instruction.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"

STATUS_OK: str = "OK"
STATUS_FAIL_CLOSED: str = "FAIL_CLOSED"

INDICATOR_NAMES: tuple[str, ...] = ("macd", "bollinger", "volume_trend")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ResearchIndicatorConfig:
    """Thresholds/periods. Defaults are classic; tests override for tiny series."""

    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_k: float = 2.0
    vol_short: int = 5
    vol_long: int = 20


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MacdResult:
    status: str
    macd: float | None
    signal: float | None
    histogram: float | None
    fail_closed_reason: str | None = None
    research_only: bool = True


@dataclass(frozen=True)
class BollingerResult:
    status: str
    mid: float | None
    upper: float | None
    lower: float | None
    percent_b: float | None
    bandwidth: float | None
    fail_closed_reason: str | None = None
    research_only: bool = True


@dataclass(frozen=True)
class VolumeTrendResult:
    status: str
    short_avg: float | None
    long_avg: float | None
    ratio: float | None
    direction: str            # "rising" | "falling" | "flat" | "none"
    fail_closed_reason: str | None = None
    research_only: bool = True


@dataclass(frozen=True)
class ResearchIndicatorReport:
    research_only: bool
    broker_execution: str
    status: str               # OK if every indicator computed; FAIL_CLOSED otherwise
    macd: MacdResult
    bollinger: BollingerResult
    volume_trend: VolumeTrendResult
    notes: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# Small deterministic helpers (fail closed on non-finite / wrong type)
# --------------------------------------------------------------------------- #
def _is_real_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _finite_floats(values: Sequence[Any]) -> list[float] | None:
    """Return a list of finite floats, or None if any element is invalid.

    Rejects None, bools, non-numeric, NaN and +-Infinity - fail closed rather
    than letting a bad value poison an indicator."""
    if values is None:
        return None
    try:
        seq = list(values)
    except TypeError:
        return None
    out: list[float] = []
    for v in seq:
        if not _is_real_number(v):
            return None
        out.append(float(v))
    return out


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _ema_series(values: Sequence[float], span: int) -> list[float]:
    """Deterministic EMA, seeded with the first value (adjust=False convention)."""
    alpha = 2.0 / (span + 1.0)
    out: list[float] = []
    prev: float | None = None
    for v in values:
        prev = v if prev is None else alpha * v + (1.0 - alpha) * prev
        out.append(prev)
    return out


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #
def compute_macd(closes: Sequence[Any], cfg: ResearchIndicatorConfig | None = None) -> MacdResult:
    cfg = cfg or ResearchIndicatorConfig()
    if cfg.macd_fast >= cfg.macd_slow or cfg.macd_signal < 1:
        return MacdResult(STATUS_FAIL_CLOSED, None, None, None, "invalid MACD periods")
    clean = _finite_floats(closes)
    if clean is None:
        return MacdResult(STATUS_FAIL_CLOSED, None, None, None, "closes contain non-finite/invalid values")
    need = cfg.macd_slow + cfg.macd_signal
    if len(clean) < need:
        return MacdResult(
            STATUS_FAIL_CLOSED, None, None, None,
            f"insufficient closes: have {len(clean)}, need {need}",
        )
    fast = _ema_series(clean, cfg.macd_fast)
    slow = _ema_series(clean, cfg.macd_slow)
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal_line = _ema_series(macd_line, cfg.macd_signal)
    macd_v = macd_line[-1]
    signal_v = signal_line[-1]
    return MacdResult(
        STATUS_OK,
        _round(macd_v),
        _round(signal_v),
        _round(macd_v - signal_v),
    )


def compute_bollinger(closes: Sequence[Any], cfg: ResearchIndicatorConfig | None = None) -> BollingerResult:
    cfg = cfg or ResearchIndicatorConfig()
    if cfg.bb_period < 2 or cfg.bb_k <= 0:
        return BollingerResult(STATUS_FAIL_CLOSED, None, None, None, None, None, "invalid Bollinger params")
    clean = _finite_floats(closes)
    if clean is None:
        return BollingerResult(STATUS_FAIL_CLOSED, None, None, None, None, None, "closes contain non-finite/invalid values")
    if len(clean) < cfg.bb_period:
        return BollingerResult(
            STATUS_FAIL_CLOSED, None, None, None, None, None,
            f"insufficient closes: have {len(clean)}, need {cfg.bb_period}",
        )
    window = clean[-cfg.bb_period:]
    mid = statistics.fmean(window)
    std = statistics.pstdev(window)
    if std == 0:
        # No dispersion -> bands collapse; %b is undefined. Fail closed.
        return BollingerResult(
            STATUS_FAIL_CLOSED, _round(mid), _round(mid), _round(mid), None, _round(0.0),
            "zero variance window: Bollinger bands collapse, percent_b undefined",
        )
    upper = mid + cfg.bb_k * std
    lower = mid - cfg.bb_k * std
    last = window[-1]
    percent_b = (last - lower) / (upper - lower)
    bandwidth = (upper - lower) / mid if mid != 0 else None
    return BollingerResult(
        STATUS_OK,
        _round(mid),
        _round(upper),
        _round(lower),
        _round(percent_b, 4),
        _round(bandwidth, 6) if bandwidth is not None else None,
    )


def compute_volume_trend(volumes: Sequence[Any], cfg: ResearchIndicatorConfig | None = None) -> VolumeTrendResult:
    cfg = cfg or ResearchIndicatorConfig()
    if cfg.vol_short < 1 or cfg.vol_long <= cfg.vol_short:
        return VolumeTrendResult(STATUS_FAIL_CLOSED, None, None, None, "none", "invalid volume windows")
    clean = _finite_floats(volumes)
    if clean is None:
        return VolumeTrendResult(STATUS_FAIL_CLOSED, None, None, None, "none", "volumes contain non-finite/invalid values")
    if any(v < 0 for v in clean):
        return VolumeTrendResult(STATUS_FAIL_CLOSED, None, None, None, "none", "negative volume is invalid")
    if len(clean) < cfg.vol_long:
        return VolumeTrendResult(
            STATUS_FAIL_CLOSED, None, None, None, "none",
            f"insufficient volumes: have {len(clean)}, need {cfg.vol_long}",
        )
    short_avg = statistics.fmean(clean[-cfg.vol_short:])
    long_avg = statistics.fmean(clean[-cfg.vol_long:])
    if long_avg <= 0:
        return VolumeTrendResult(STATUS_FAIL_CLOSED, None, None, None, "none", "degenerate baseline volume (<= 0)")
    ratio = short_avg / long_avg
    if ratio > 1.0:
        direction = "rising"
    elif ratio < 1.0:
        direction = "falling"
    else:
        direction = "flat"
    return VolumeTrendResult(
        STATUS_OK,
        _round(short_avg),
        _round(long_avg),
        _round(ratio, 4),
        direction,
    )


def compute_research_indicators(
    closes: Sequence[Any],
    volumes: Sequence[Any] | None = None,
    cfg: ResearchIndicatorConfig | None = None,
) -> ResearchIndicatorReport:
    """Compute all three research indicators. Fails closed per indicator; the
    report ``status`` is OK only when every indicator computed."""
    cfg = cfg or ResearchIndicatorConfig()
    macd = compute_macd(closes, cfg)
    bollinger = compute_bollinger(closes, cfg)
    volume_trend = (
        compute_volume_trend(volumes, cfg)
        if volumes is not None
        else VolumeTrendResult(STATUS_FAIL_CLOSED, None, None, None, "none", "no volumes provided")
    )
    statuses = (macd.status, bollinger.status, volume_trend.status)
    overall = STATUS_OK if all(s == STATUS_OK for s in statuses) else STATUS_FAIL_CLOSED
    notes = (
        "RESEARCH-ONLY: MACD/Bollinger/volume-trend are not used in the live path "
        "and are not a trade signal; no edge is claimed.",
    )
    return ResearchIndicatorReport(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        status=overall,
        macd=macd,
        bollinger=bollinger,
        volume_trend=volume_trend,
        notes=notes,
    )


def report_to_dict(report: ResearchIndicatorReport) -> dict[str, Any]:
    return asdict(report)
