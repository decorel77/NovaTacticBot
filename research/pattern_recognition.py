"""Offline research-only pattern recognition prototype (NEXT-PR-001).

A deterministic, fixture-driven research module that scans a single-symbol
daily OHLC(V) series for simple, *explainable* chart/trade setups. It exists so
Nova can later study which recurring market structures tend to precede good or
bad outcomes. It is RESEARCH-ONLY and completely separate from any live path:

  - it reads only in-memory data or local JSON fixtures,
  - it places no orders and connects to no broker,
  - it imports no broker / order / live-cycle / scheduler / network modules,
  - it touches no risk, capital, or position-sizing settings,
  - it is NOT wired into the NovaTacticBot advisory runner or any scheduler,
  - every signal it emits is flagged ``research_only=True`` and carries
    ``data_is_real`` propagated from the caller (never invented),
  - it FAILS CLOSED: on invalid/insufficient/degenerate data it reports a
    ``fail_closed_reason`` and ``detected=False`` rather than guessing.

The output is descriptive evidence, not a trade instruction. A ``PatternSignal``
says "this structure is present in this window, here are the numbers behind it,
here is how confident the rule is, and here is what data quality it assumed".
It never decides anything about live trading, sizing, or capital.

Patterns detected over a price series (see ``docs/pattern_recognition_research.md``):

  - breakout_after_consolidation
  - volume_spike
  - trend_continuation
  - mean_reversion_candidate
  - gap_continuation_risk
  - failed_breakout
  - higher_high_higher_low
  - drawdown_recovery

Plus one pattern over a sequence of labeled trade outcomes:

  - win_loss_clusters (longest win/loss streaks per normalized setup label)

Everything is pure arithmetic over the inputs: given the same fixture it always
produces the same numbers. No wall-clock, no randomness, no I/O during compute.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

# Reuse the already-proven, broker-free validation + label normalization from
# the sibling research harness so the two modules share one vocabulary and one
# fail-closed contract. (Both are research-only; neither imports a broker.)
from research.stock_tactics_backtest import normalize_setup_label, validate_bars

RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"

PATTERN_NAMES: tuple[str, ...] = (
    "breakout_after_consolidation",
    "volume_spike",
    "trend_continuation",
    "mean_reversion_candidate",
    "gap_continuation_risk",
    "failed_breakout",
    "higher_high_higher_low",
    "drawdown_recovery",
    "win_loss_clusters",
)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PatternBar:
    """A daily OHLC bar with optional volume.

    ``volume`` is optional because some sanitized offline fixtures carry only
    price. Detectors that require volume (volume_spike) fail closed when it is
    absent rather than fabricating a baseline.
    """

    date: str  # ISO date "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(frozen=True)
class TradeOutcome:
    """A single closed-trade outcome label for win/loss cluster analysis.

    This is sanitized research input — a (date, setup_label, win) triple — not a
    live order or position. The label is normalized through the same
    fail-closed table as the backtest harness.
    """

    date: str
    setup_label: str
    win: bool


@dataclass(frozen=True)
class PatternConfig:
    """Thresholds for the detectors. Defaults are sensible for ~daily bars;
    tests override them for small synthetic fixtures."""

    # General context window.
    lookback: int = 20
    min_bars: int = 5
    # Breakout after consolidation.
    consolidation_window: int = 10
    consolidation_max_range_pct: float = 5.0
    breakout_buffer_pct: float = 0.0
    # Volume spike.
    volume_spike_window: int = 20
    volume_spike_mult: float = 2.0
    # Trend continuation / structure.
    trend_window: int = 10
    trend_min_consistency: float = 0.6
    # Gap continuation risk.
    gap_pct: float = 2.0
    # Mean reversion.
    mean_reversion_z: float = 2.0
    # Drawdown / recovery.
    drawdown_pct: float = 10.0
    recovery_frac: float = 0.5
    # Win/loss clusters (operate on outcomes, not bars).
    cluster_min_outcomes: int = 6
    cluster_min_len: int = 3


@dataclass(frozen=True)
class PatternSignal:
    """One detector's verdict on one window. Advisory / research-only.

    Fields mirror the safety contract requested for Nova pattern research:
      - ``pattern_name``         which detector produced this
      - ``detected``             whether the rule fired
      - ``confidence_score``     0.0-1.0; 0.0 when not detected or failed closed
      - ``evidence``             the explainable numbers behind the verdict
      - ``required_data_quality``what the detector assumed about the input
      - ``missing_data``         which required inputs were absent/insufficient
      - ``fail_closed_reason``   set (and detected=False) when the rule could not
                                 run on the given data
      - ``research_only``        always True
      - ``data_is_real``         propagated from the input; forced False on any
                                 fail-closed signal (a non-result vouches for
                                 nothing)
    """

    pattern_name: str
    detected: bool
    confidence_score: float
    evidence: dict[str, Any]
    required_data_quality: dict[str, Any]
    missing_data: tuple[str, ...] = ()
    fail_closed_reason: str | None = None
    research_only: bool = True
    data_is_real: bool = False


@dataclass(frozen=True)
class PatternScanReport:
    """Aggregate of every price-series detector (plus optional outcome cluster)
    over one symbol's window."""

    research_only: bool
    broker_execution: str
    data_is_real: bool
    input_source: str
    symbol: str
    bars_analysed: int
    config: dict[str, Any]
    signals: tuple[PatternSignal, ...]
    errors: tuple[str, ...] = ()          # dataset-level fatal errors (fail closed)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def detected(self) -> tuple[PatternSignal, ...]:
        return tuple(s for s in self.signals if s.detected)


# --------------------------------------------------------------------------- #
# Small deterministic helpers
# --------------------------------------------------------------------------- #
def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _pct(value: float, base: float) -> float:
    """Percentage change of ``value`` versus ``base`` (base must be non-zero)."""
    return (value - base) / base * 100.0


def _closes(bars: Sequence[PatternBar]) -> list[float]:
    return [b.close for b in bars]


def validate_pattern_bars(bars: Sequence[PatternBar]) -> list[str]:
    """Return dataset-level errors. Reuses the backtest OHLC/date validation and
    adds optional-volume checks. Empty list means the bars are sane."""
    errors = validate_bars(bars)
    for i, bar in enumerate(bars):
        if bar.volume is None:
            continue
        if not isinstance(bar.volume, (int, float)) or isinstance(bar.volume, bool):
            errors.append(f"bar[{i}] {bar.date}: volume is not a number ({bar.volume!r})")
        elif bar.volume < 0:
            errors.append(f"bar[{i}] {bar.date}: volume must be >= 0 (got {bar.volume})")
    return errors


def _insufficient(
    name: str,
    required: dict[str, Any],
    have: int,
    *,
    need_key: str = "min_bars",
    unit: str = "bars",
    extra_missing: tuple[str, ...] = (),
) -> PatternSignal:
    """Build a fail-closed signal for not-enough-data. data_is_real forced False."""
    need = required.get(need_key)
    missing = (f"insufficient_{unit}: have {have} need {need}",) + extra_missing
    return PatternSignal(
        pattern_name=name,
        detected=False,
        confidence_score=0.0,
        evidence={},
        required_data_quality=required,
        missing_data=missing,
        fail_closed_reason=f"insufficient data: have {have} {unit}, need {need}",
        data_is_real=False,
    )


def _failed(
    name: str,
    required: dict[str, Any],
    reason: str,
    *,
    missing: tuple[str, ...] = (),
) -> PatternSignal:
    """Build a fail-closed signal for a degenerate/invalid input. data_is_real False."""
    return PatternSignal(
        pattern_name=name,
        detected=False,
        confidence_score=0.0,
        evidence={},
        required_data_quality=required,
        missing_data=missing,
        fail_closed_reason=reason,
        data_is_real=False,
    )


# --------------------------------------------------------------------------- #
# Price-series detectors
# --------------------------------------------------------------------------- #
def detect_breakout_after_consolidation(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Fire when a tight prior range is followed by a close above that range.

    Confidence blends how *tight* the consolidation was with how *far* the last
    close cleared the range high. Both are bounded to [0, 1].
    """
    name = "breakout_after_consolidation"
    required = {
        "min_bars": cfg.consolidation_window + 1,
        "consolidation_window": cfg.consolidation_window,
        "needs_volume": False,
    }
    if len(bars) < cfg.consolidation_window + 1:
        return _insufficient(name, required, len(bars))

    window = bars[-(cfg.consolidation_window + 1):-1]
    last = bars[-1]
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    mid = (hi + lo) / 2.0
    if mid <= 0:
        return _failed(name, required, "degenerate consolidation window (non-positive mid)")
    range_vs_mid_pct = (hi - lo) / mid * 100.0
    consolidated = range_vs_mid_pct <= cfg.consolidation_max_range_pct
    breakout_level = hi * (1.0 + cfg.breakout_buffer_pct / 100.0)
    broke_out = last.close > breakout_level
    breakout_pct = _pct(last.close, hi)
    detected = consolidated and broke_out

    tight = _clamp01(1.0 - range_vs_mid_pct / cfg.consolidation_max_range_pct)
    strength = _clamp01(breakout_pct / cfg.consolidation_max_range_pct)
    confidence = _round(_clamp01(0.5 * tight + 0.5 * strength), 4) if detected else 0.0

    evidence = {
        "consolidation_high": _round(hi),
        "consolidation_low": _round(lo),
        "consolidation_range_pct": _round(range_vs_mid_pct),
        "consolidated": consolidated,
        "breakout_level": _round(breakout_level),
        "breakout_close": _round(last.close),
        "breakout_pct": _round(breakout_pct),
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_volume_spike(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Fire when the last bar's volume is a multiple of its trailing average.

    Fails closed (not "no spike") if volume is missing on any bar in the window,
    so an absent feed is never silently treated as a quiet tape.
    """
    name = "volume_spike"
    required = {"min_bars": cfg.volume_spike_window + 1, "needs_volume": True}
    if len(bars) < cfg.volume_spike_window + 1:
        return _insufficient(name, required, len(bars))

    window = bars[-(cfg.volume_spike_window + 1):-1]
    last = bars[-1]
    if last.volume is None or any(b.volume is None for b in window):
        return _failed(
            name, required, "volume missing on one or more bars in the window",
            missing=("volume",),
        )
    baseline = statistics.fmean(b.volume for b in window)
    if baseline <= 0:
        return _failed(name, required, "degenerate baseline volume (<= 0)")
    ratio = last.volume / baseline
    detected = ratio >= cfg.volume_spike_mult
    confidence = _round(_clamp01(ratio / (2.0 * cfg.volume_spike_mult)), 4) if detected else 0.0

    evidence = {
        "last_volume": _round(last.volume),
        "baseline_volume": _round(baseline),
        "ratio": _round(ratio),
        "spike_multiple_required": cfg.volume_spike_mult,
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_trend_continuation(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Fire when a directional window keeps going in the same direction.

    "Direction" is the sign of the window's net return; "continuation" requires
    the last bar to move with that direction and the window to be internally
    consistent (>= trend_min_consistency of bar-to-bar moves agree).
    """
    name = "trend_continuation"
    required = {"min_bars": cfg.trend_window + 1, "trend_window": cfg.trend_window, "needs_volume": False}
    if len(bars) < cfg.trend_window + 1:
        return _insufficient(name, required, len(bars))

    window = bars[-(cfg.trend_window + 1):]
    closes = _closes(window)
    if closes[0] <= 0:
        return _failed(name, required, "degenerate window (non-positive base close)")
    net_return_pct = _pct(closes[-1], closes[0])
    moves = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    ups = sum(1 for m in moves if m > 0)
    downs = sum(1 for m in moves if m < 0)
    up_fraction = ups / len(moves)
    down_fraction = downs / len(moves)
    last_move_up = window[-1].close > window[-2].close

    if net_return_pct > 0:
        direction = "up"
        consistency = up_fraction
        detected = last_move_up and consistency >= cfg.trend_min_consistency
    elif net_return_pct < 0:
        direction = "down"
        consistency = down_fraction
        detected = (not last_move_up) and consistency >= cfg.trend_min_consistency
    else:
        direction = "flat"
        consistency = 0.0
        detected = False

    confidence = _round(_clamp01(consistency), 4) if detected else 0.0
    evidence = {
        "direction": direction,
        "net_return_pct": _round(net_return_pct),
        "up_fraction": _round(up_fraction, 4),
        "down_fraction": _round(down_fraction, 4),
        "last_bar_move_up": last_move_up,
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_mean_reversion_candidate(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Fire when the last close is a z-score extreme versus its lookback window.

    Negative extreme => oversold (reversion-up candidate); positive extreme =>
    overbought (reversion-down candidate). Zero-variance windows fail closed.
    """
    name = "mean_reversion_candidate"
    required = {"min_bars": cfg.lookback, "lookback": cfg.lookback, "needs_volume": False}
    if len(bars) < cfg.lookback:
        return _insufficient(name, required, len(bars))

    closes = _closes(bars[-cfg.lookback:])
    mean = statistics.fmean(closes)
    stdev = statistics.pstdev(closes)
    if stdev == 0:
        return _failed(name, required, "zero variance window: no deviation to revert from")
    if mean <= 0:
        return _failed(name, required, "degenerate window (non-positive mean)")
    last_close = closes[-1]
    zscore = (last_close - mean) / stdev
    deviation_pct = _pct(last_close, mean)
    detected = abs(zscore) >= cfg.mean_reversion_z
    if zscore <= -cfg.mean_reversion_z:
        direction = "oversold_reversion_up"
    elif zscore >= cfg.mean_reversion_z:
        direction = "overbought_reversion_down"
    else:
        direction = "none"
    # z == threshold -> 0.5, z == 2x threshold -> 1.0
    confidence = (
        _round(_clamp01(0.5 + 0.5 * (abs(zscore) - cfg.mean_reversion_z) / cfg.mean_reversion_z), 4)
        if detected
        else 0.0
    )
    evidence = {
        "mean": _round(mean),
        "stdev": _round(stdev),
        "last_close": _round(last_close),
        "zscore": _round(zscore, 4),
        "deviation_pct": _round(deviation_pct),
        "direction": direction,
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_gap_continuation_risk(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Flag an opening gap and whether it shows continuation risk.

    This is an advisory *risk* flag, not a buy/sell call: it reports the gap
    size, direction, whether the bar closed in the gap direction, and whether
    the gap was (intrabar) filled back to the prior close.
    """
    name = "gap_continuation_risk"
    required = {"min_bars": 2, "needs_volume": False}
    if len(bars) < 2:
        return _insufficient(name, required, len(bars))

    prev, last = bars[-2], bars[-1]
    if prev.close <= 0:
        return _failed(name, required, "degenerate prior close (<= 0)")
    gap_pct = _pct(last.open, prev.close)
    gap_up = gap_pct >= cfg.gap_pct
    gap_down = gap_pct <= -cfg.gap_pct
    detected = gap_up or gap_down
    if gap_up:
        direction = "gap_up"
        closed_in_gap_direction = last.close > last.open
        gap_filled = last.low <= prev.close
    elif gap_down:
        direction = "gap_down"
        closed_in_gap_direction = last.close < last.open
        gap_filled = last.high >= prev.close
    else:
        direction = "none"
        closed_in_gap_direction = False
        gap_filled = False

    # Continuation risk is highest for a large, unfilled gap that closed in its
    # own direction. Confidence here measures gap magnitude only.
    confidence = _round(_clamp01(abs(gap_pct) / (2.0 * cfg.gap_pct)), 4) if detected else 0.0
    continuation_risk = detected and closed_in_gap_direction and not gap_filled
    evidence = {
        "gap_pct": _round(gap_pct),
        "direction": direction,
        "closed_in_gap_direction": closed_in_gap_direction,
        "gap_filled": gap_filled,
        "continuation_risk": continuation_risk,
        "prev_close": _round(prev.close),
        "open": _round(last.open),
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_failed_breakout(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Fire when a recent bar poked above the prior range but the last bar's
    close fell back below it (a fakeout / failed breakout).

    Layout: ``base_window`` = the consolidation before the breakout bar;
    ``breakout_bar`` = the second-to-last bar that pokes above; the last bar is
    the failure bar that closes back under the broken level.
    """
    name = "failed_breakout"
    required = {
        "min_bars": cfg.consolidation_window + 2,
        "consolidation_window": cfg.consolidation_window,
        "needs_volume": False,
    }
    if len(bars) < cfg.consolidation_window + 2:
        return _insufficient(name, required, len(bars))

    base_window = bars[-(cfg.consolidation_window + 2):-2]
    breakout_bar = bars[-2]
    fail_bar = bars[-1]
    base_high = max(b.high for b in base_window)
    if base_high <= 0:
        return _failed(name, required, "degenerate base window (non-positive high)")
    poked_above = breakout_bar.high > base_high
    closed_back_below = fail_bar.close < base_high
    detected = poked_above and closed_back_below
    poke_pct = _pct(breakout_bar.high, base_high)
    retrace_pct = _pct(base_high, fail_bar.close)
    confidence = (
        _round(_clamp01((retrace_pct + poke_pct) / (2.0 * cfg.consolidation_max_range_pct)), 4)
        if detected
        else 0.0
    )
    evidence = {
        "base_high": _round(base_high),
        "breakout_high": _round(breakout_bar.high),
        "fail_close": _round(fail_bar.close),
        "poke_pct": _round(poke_pct),
        "retrace_pct": _round(retrace_pct),
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_higher_high_higher_low(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Classify swing structure by comparing two halves of the trend window.

    Higher-high + higher-low => uptrend structure (HH_HL); lower-high +
    lower-low => downtrend structure (LH_LL); otherwise "mixed" (not detected).
    """
    name = "higher_high_higher_low"
    window_len = max(4, cfg.trend_window)
    required = {"min_bars": window_len, "trend_window": cfg.trend_window, "needs_volume": False}
    if len(bars) < window_len:
        return _insufficient(name, required, len(bars))

    window = bars[-window_len:]
    half = len(window) // 2
    first, second = window[:half], window[half:]
    fh_high = max(b.high for b in first)
    sh_high = max(b.high for b in second)
    fh_low = min(b.low for b in first)
    sh_low = min(b.low for b in second)
    higher_high = sh_high > fh_high
    higher_low = sh_low > fh_low
    lower_high = sh_high < fh_high
    lower_low = sh_low < fh_low
    if higher_high and higher_low:
        structure = "HH_HL"
    elif lower_high and lower_low:
        structure = "LH_LL"
    else:
        structure = "mixed"
    detected = structure in ("HH_HL", "LH_LL")
    if detected and fh_high > 0 and fh_low > 0:
        high_margin = abs(_pct(sh_high, fh_high))
        low_margin = abs(_pct(sh_low, fh_low))
        confidence = _round(_clamp01((high_margin + low_margin) / (2.0 * cfg.consolidation_max_range_pct)), 4)
    else:
        confidence = 0.0
    evidence = {
        "structure": structure,
        "first_half_high": _round(fh_high),
        "second_half_high": _round(sh_high),
        "first_half_low": _round(fh_low),
        "second_half_low": _round(sh_low),
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


def detect_drawdown_recovery(
    bars: Sequence[PatternBar], cfg: PatternConfig, *, data_is_real: bool = False
) -> PatternSignal:
    """Fire when the window had a meaningful peak-to-trough drawdown AND has
    since recovered a configured fraction of that drawdown."""
    name = "drawdown_recovery"
    required = {"min_bars": cfg.lookback, "lookback": cfg.lookback, "needs_volume": False}
    if len(bars) < cfg.lookback:
        return _insufficient(name, required, len(bars))

    closes = _closes(bars[-cfg.lookback:])
    peak = closes[0]
    max_dd_pct = 0.0
    trough = closes[0]
    peak_at_trough = closes[0]
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = _pct(c, peak)
            if dd < max_dd_pct:
                max_dd_pct = dd
                trough = c
                peak_at_trough = peak
    depth = peak_at_trough - trough
    last_close = closes[-1]
    recovered_frac = (last_close - trough) / depth if depth > 0 else 0.0
    detected = abs(max_dd_pct) >= cfg.drawdown_pct and recovered_frac >= cfg.recovery_frac
    confidence = _round(_clamp01(0.5 * _clamp01(recovered_frac) + 0.5 * _clamp01(abs(max_dd_pct) / (2.0 * cfg.drawdown_pct))), 4) if detected else 0.0
    evidence = {
        "peak": _round(peak_at_trough),
        "trough": _round(trough),
        "max_drawdown_pct": _round(max_dd_pct),
        "recovered_frac": _round(recovered_frac, 4),
        "current_close": _round(last_close),
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


# --------------------------------------------------------------------------- #
# Outcome-sequence detector
# --------------------------------------------------------------------------- #
def _longest_streaks(wins: Sequence[bool]) -> tuple[int, int]:
    """Return (longest_win_streak, longest_loss_streak) over an ordered sequence."""
    longest_win = longest_loss = cur_win = cur_loss = 0
    for w in wins:
        if w:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        longest_win = max(longest_win, cur_win)
        longest_loss = max(longest_loss, cur_loss)
    return longest_win, longest_loss


def detect_win_loss_clusters(
    outcomes: Sequence[TradeOutcome],
    cfg: PatternConfig,
    *,
    data_is_real: bool = False,
) -> PatternSignal:
    """Detect repeated win/loss streaks ("clusters") per normalized setup label.

    Operates on sanitized outcome labels only. Labels normalize through the same
    fail-closed table as the backtest harness; unrecognized labels collapse to
    UNKNOWN and are recorded in evidence (never attributed to a real family).
    """
    name = "win_loss_clusters"
    required = {"min_outcomes": cfg.cluster_min_outcomes, "cluster_min_len": cfg.cluster_min_len}
    if len(outcomes) < cfg.cluster_min_outcomes:
        return _insufficient(
            name, required, len(outcomes), need_key="min_outcomes", unit="outcomes"
        )

    # Deterministic chronological order; ties broken by original index.
    ordered = sorted(enumerate(outcomes), key=lambda iv: (iv[1].date, iv[0]))
    ordered_outcomes = [o for _, o in ordered]

    unrecognized: list[str] = []
    by_label_wins: dict[str, list[bool]] = {}
    for o in ordered_outcomes:
        label, recognized = normalize_setup_label(o.setup_label)
        if not recognized and o.setup_label not in unrecognized:
            unrecognized.append(str(o.setup_label))
        by_label_wins.setdefault(label, []).append(bool(o.win))

    overall_wins = [bool(o.win) for o in ordered_outcomes]
    o_win_streak, o_loss_streak = _longest_streaks(overall_wins)

    by_setup: dict[str, dict[str, Any]] = {}
    flagged: list[dict[str, Any]] = []
    for label in sorted(by_label_wins):
        wins = by_label_wins[label]
        win_streak, loss_streak = _longest_streaks(wins)
        n = len(wins)
        w = sum(1 for x in wins if x)
        by_setup[label] = {
            "n": n,
            "wins": w,
            "losses": n - w,
            "win_rate": _round(w / n, 4),
            "longest_win_streak": win_streak,
            "longest_loss_streak": loss_streak,
        }
        if win_streak >= cfg.cluster_min_len:
            flagged.append({"setup": label, "kind": "win", "length": win_streak})
        if loss_streak >= cfg.cluster_min_len:
            flagged.append({"setup": label, "kind": "loss", "length": loss_streak})

    detected = bool(flagged)
    max_len = max((f["length"] for f in flagged), default=0)
    confidence = _round(_clamp01(max_len / (2.0 * cfg.cluster_min_len)), 4) if detected else 0.0
    evidence = {
        "total_outcomes": len(ordered_outcomes),
        "overall": {
            "wins": sum(1 for x in overall_wins if x),
            "losses": sum(1 for x in overall_wins if not x),
            "longest_win_streak": o_win_streak,
            "longest_loss_streak": o_loss_streak,
        },
        "by_setup": by_setup,
        "flagged_clusters": flagged,
        "unrecognized_labels": unrecognized,
    }
    return PatternSignal(
        name, detected, confidence, evidence, required, data_is_real=data_is_real
    )


# --------------------------------------------------------------------------- #
# Top-level scan
# --------------------------------------------------------------------------- #
_PRICE_DETECTORS = (
    detect_breakout_after_consolidation,
    detect_volume_spike,
    detect_trend_continuation,
    detect_mean_reversion_candidate,
    detect_gap_continuation_risk,
    detect_failed_breakout,
    detect_higher_high_higher_low,
    detect_drawdown_recovery,
)


def scan_patterns(
    bars: Sequence[PatternBar],
    cfg: PatternConfig | None = None,
    *,
    symbol: str,
    input_source: str = "fixture",
    data_is_real: bool = False,
    outcomes: Sequence[TradeOutcome] | None = None,
) -> PatternScanReport:
    """Run every price-series detector (and the cluster detector when
    ``outcomes`` is supplied). Fails closed at the dataset level on invalid bars.

    ``data_is_real`` is propagated into every signal and the report; it is forced
    False whenever the bars fail validation (a non-result vouches for nothing).
    """
    cfg = cfg or PatternConfig()
    config_dict = asdict(cfg)
    errors = validate_pattern_bars(bars)
    if errors:
        return PatternScanReport(
            research_only=RESEARCH_ONLY,
            broker_execution=BROKER_EXECUTION,
            data_is_real=False,
            input_source=input_source,
            symbol=symbol,
            bars_analysed=len(bars),
            config=config_dict,
            signals=(),
            errors=tuple(errors),
        )

    signals = tuple(d(bars, cfg, data_is_real=data_is_real) for d in _PRICE_DETECTORS)
    notes: list[str] = []
    if outcomes is not None:
        cluster = detect_win_loss_clusters(outcomes, cfg, data_is_real=data_is_real)
        signals = signals + (cluster,)
        unrecognized = cluster.evidence.get("unrecognized_labels") if cluster.evidence else None
        if unrecognized:
            notes.append(
                f"win_loss_clusters: unrecognized labels treated as UNKNOWN: {unrecognized}"
            )

    return PatternScanReport(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        data_is_real=bool(data_is_real),
        input_source=input_source,
        symbol=symbol,
        bars_analysed=len(bars),
        config=config_dict,
        signals=signals,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Fixture loading + rendering (research convenience only)
# --------------------------------------------------------------------------- #
def load_dataset(
    path: str | Path,
) -> tuple[list[PatternBar], list[TradeOutcome], str, dict[str, Any]]:
    """Load a JSON dataset: {symbol, bars:[...], outcomes:[...], meta:{...}}.

    ``outcomes`` is optional. All checked-in fixtures are synthetic and declare
    ``data_is_real: false`` in ``meta``; this loader never asserts realness.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    symbol = str(data["symbol"])
    bars = [
        PatternBar(
            date=str(b["date"]),
            open=float(b["open"]),
            high=float(b["high"]),
            low=float(b["low"]),
            close=float(b["close"]),
            volume=(float(b["volume"]) if b.get("volume") is not None else None),
        )
        for b in data.get("bars", [])
    ]
    outcomes = [
        TradeOutcome(
            date=str(o["date"]),
            setup_label=str(o.get("setup_label", o.get("setup_type", ""))),
            win=bool(o["win"]),
        )
        for o in data.get("outcomes", [])
    ]
    meta = dict(data.get("meta", {}))
    return bars, outcomes, symbol, meta


def report_to_dict(report: PatternScanReport) -> dict[str, Any]:
    return asdict(report)


def render_report_text(report: PatternScanReport) -> str:
    lines = [
        "PATTERN RECOGNITION SCAN (RESEARCH ONLY)",
        "",
        f"research_only: {report.research_only}",
        f"broker_execution: {report.broker_execution}",
        f"data_is_real: {report.data_is_real}",
        f"input_source: {report.input_source}",
        f"symbol: {report.symbol}",
        f"bars_analysed: {report.bars_analysed}",
        "",
    ]
    if report.errors:
        lines.append("ERRORS (failed closed, no patterns evaluated):")
        lines.extend(f"  - {e}" for e in report.errors)
        return "\n".join(lines).rstrip() + "\n"

    lines.append("signals:")
    for s in report.signals:
        verdict = "DETECTED" if s.detected else "no-match"
        lines.append(f"  [{verdict}] {s.pattern_name} (confidence={s.confidence_score})")
        if s.fail_closed_reason:
            lines.append(f"      fail_closed: {s.fail_closed_reason}")
        if s.missing_data:
            lines.append(f"      missing_data: {list(s.missing_data)}")
        if s.detected and s.evidence:
            lines.append(f"      evidence: {s.evidence}")
    if report.notes:
        lines.append("notes:")
        lines.extend(f"  - {n}" for n in report.notes)
    lines.extend([
        "",
        "NOTE: research-only descriptive evidence. Detections are NOT trade",
        "signals and never control orders, risk, or capital. Small synthetic",
        "samples are not evidence of live edge.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline RESEARCH-ONLY pattern recognition scan (no broker, no orders)"
    )
    parser.add_argument("dataset", help="path to a JSON dataset fixture (synthetic by default)")
    parser.add_argument("--lookback", type=int, default=None)
    parser.add_argument("--consolidation-window", type=int, default=None)
    parser.add_argument("--trend-window", type=int, default=None)
    parser.add_argument("--volume-window", type=int, default=None)
    args = parser.parse_args(argv)

    bars, outcomes, symbol, meta = load_dataset(args.dataset)
    overrides: dict[str, Any] = {}
    if args.lookback is not None:
        overrides["lookback"] = args.lookback
    if args.consolidation_window is not None:
        overrides["consolidation_window"] = args.consolidation_window
    if args.trend_window is not None:
        overrides["trend_window"] = args.trend_window
    if args.volume_window is not None:
        overrides["volume_spike_window"] = args.volume_window
    cfg = PatternConfig(**overrides)

    report = scan_patterns(
        bars,
        cfg,
        symbol=symbol,
        input_source=str(meta.get("input_source", "fixture")),
        data_is_real=False,  # CLI never asserts realness; fixtures are research-only
        outcomes=outcomes or None,
    )
    print(render_report_text(report), end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
