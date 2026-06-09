"""
Cross-run trend analyser for NovaTacticBot.

Compares current run metrics against last N baseline snapshots from
analytics_baseline.json and run_history.json. Reports significant shifts
in win rate, event volume, or strategy distribution.

Rules:
  - win_rate delta > 5pp vs recent average  → SIGNIFICANT_WIN_RATE_SHIFT
  - event_count delta > 30%                 → SIGNIFICANT_VOLUME_SHIFT
  - strategy presence in top-5 changed      → STRATEGY_MIX_CHANGE

Returns a TrendReport (no file writes here — caller may persist).

ADVISORY_ONLY. No broker imports. Read-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from utils.analytics_baseline_writer import AnalyticsBaselineWriter
from utils.run_history_tracker import RunHistoryTracker

_DEFAULT_SYSTEM_DIR = Path(__file__).resolve().parents[1] / "data" / "system"

WIN_RATE_SHIFT_THRESHOLD = 0.05   # 5 percentage points
VOLUME_SHIFT_THRESHOLD = 0.30     # 30 percent


@dataclass
class TrendFlag:
    flag: str
    detail: str


@dataclass
class TrendReport:
    """Result of a cross-run trend analysis pass."""
    run_count: int = 0
    baselines_compared: int = 0
    recent_avg_win_rate: Optional[float] = None
    current_win_rate: Optional[float] = None
    win_rate_delta: Optional[float] = None
    recent_avg_event_count: Optional[float] = None
    current_event_count: int = 0
    event_count_delta_pct: Optional[float] = None
    flags: list[TrendFlag] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    schema_version: str = "1.0"

    def has_significant_changes(self) -> bool:
        return len(self.flags) > 0


def _recent_avg_win_rate(baselines: list[dict], n: int) -> Optional[float]:
    recent = baselines[-n:]
    rates = [b.get("overall_win_rate") for b in recent if b.get("overall_win_rate") is not None]
    return sum(rates) / len(rates) if rates else None


def _recent_avg_event_count(baselines: list[dict], n: int) -> Optional[float]:
    recent = baselines[-n:]
    counts = [b.get("total_events", 0) for b in recent]
    return sum(counts) / len(counts) if counts else None


def _top_strategies(snapshot: dict, top_n: int = 5) -> frozenset[str]:
    dist: dict[str, int] = snapshot.get("strategy_distribution", {})
    if not dist:
        return frozenset()
    sorted_strats = sorted(dist.items(), key=lambda x: x[1], reverse=True)
    return frozenset(s for s, _ in sorted_strats[:top_n])


class CrossRunTrendAnalyser:
    """Compares the most-recent baseline against prior history."""

    def __init__(
        self,
        baseline_file: Optional[Path] = None,
        history_file: Optional[Path] = None,
        lookback: int = 5,
    ) -> None:
        self._baseline_writer = AnalyticsBaselineWriter(baseline_file)
        self._history_tracker = RunHistoryTracker(history_file)
        self._lookback = lookback

    def analyse(self) -> TrendReport:
        """Compare the most-recent baseline snapshot against prior baselines."""
        report = TrendReport()

        baselines = self._baseline_writer.read_all()
        report.run_count = self._history_tracker.count()

        if len(baselines) < 2:
            report.observations.append(
                f"Not enough baseline history for trend analysis ({len(baselines)} snapshot(s) available)."
            )
            return report

        # Current = last snapshot; comparison window = prior N snapshots
        current = baselines[-1]
        prior = baselines[:-1]
        n = min(self._lookback, len(prior))
        report.baselines_compared = n

        # --- Win rate trend ---
        report.current_win_rate = current.get("overall_win_rate")
        report.recent_avg_win_rate = _recent_avg_win_rate(prior, n)

        if report.current_win_rate is not None and report.recent_avg_win_rate is not None:
            delta = report.current_win_rate - report.recent_avg_win_rate
            report.win_rate_delta = delta
            if abs(delta) >= WIN_RATE_SHIFT_THRESHOLD:
                direction = "UP" if delta > 0 else "DOWN"
                report.flags.append(TrendFlag(
                    flag="SIGNIFICANT_WIN_RATE_SHIFT",
                    detail=(
                        f"win_rate {direction} {abs(delta)*100:.1f}pp "
                        f"(current={report.current_win_rate*100:.1f}% "
                        f"vs avg={report.recent_avg_win_rate*100:.1f}%)"
                    ),
                ))

        # --- Event volume trend ---
        report.current_event_count = int(current.get("total_events", 0))
        report.recent_avg_event_count = _recent_avg_event_count(prior, n)

        if report.recent_avg_event_count and report.recent_avg_event_count > 0:
            vol_delta = (report.current_event_count - report.recent_avg_event_count) / report.recent_avg_event_count
            report.event_count_delta_pct = vol_delta
            if abs(vol_delta) >= VOLUME_SHIFT_THRESHOLD:
                direction = "UP" if vol_delta > 0 else "DOWN"
                report.flags.append(TrendFlag(
                    flag="SIGNIFICANT_VOLUME_SHIFT",
                    detail=(
                        f"event_count {direction} {abs(vol_delta)*100:.0f}% "
                        f"(current={report.current_event_count} "
                        f"vs avg={report.recent_avg_event_count:.0f})"
                    ),
                ))

        # --- Strategy mix trend (compare top-5 vs last snapshot) ---
        if len(prior) >= 1:
            prev_top = _top_strategies(prior[-1])
            curr_top = _top_strategies(current)
            if prev_top and curr_top and prev_top != curr_top:
                added = curr_top - prev_top
                removed = prev_top - curr_top
                if added or removed:
                    report.flags.append(TrendFlag(
                        flag="STRATEGY_MIX_CHANGE",
                        detail=(
                            f"top-5 strategy set changed: "
                            f"added={sorted(added) or 'none'} "
                            f"removed={sorted(removed) or 'none'}"
                        ),
                    ))

        if not report.flags:
            report.observations.append(
                f"No significant trend changes detected across last {n} baseline(s)."
            )

        return report
