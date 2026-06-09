"""
Analytics baseline snapshot writer for NovaTacticBot.

After each analysis run, persists key metrics to
data/system/analytics_baseline.json for cross-run trend detection.

Schema (list of snapshots, newest appended last):
  timestamp           — ISO-8601 UTC
  run_id              — optional run identifier
  total_events        — int
  overall_win_rate    — float | null
  avg_pnl             — float | null
  strategy_win_rates  — dict[str, float | null]
  regime_win_rates    — dict[str, float | null]
  strategy_distribution — dict[str, int]  (event counts)
  regime_distribution   — dict[str, int]
  schema_version      — "1.0"

No broker imports. ADVISORY_ONLY — writes to data/system/ only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.tactic_analytics_engine import AnalyticsResult

_DEFAULT_SYSTEM_DIR = Path(__file__).resolve().parents[1] / "data" / "system"
_BASELINE_FILE = _DEFAULT_SYSTEM_DIR / "analytics_baseline.json"

SCHEMA_VERSION = "1.0"


@dataclass
class BaselineSnapshot:
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    run_id: Optional[str] = None
    total_events: int = 0
    overall_win_rate: Optional[float] = None
    avg_pnl: Optional[float] = None
    strategy_win_rates: dict[str, Optional[float]] = field(default_factory=dict)
    regime_win_rates: dict[str, Optional[float]] = field(default_factory=dict)
    strategy_distribution: dict[str, int] = field(default_factory=dict)
    regime_distribution: dict[str, int] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def snapshot_from_result(result: AnalyticsResult, run_id: str | None = None) -> BaselineSnapshot:
    """Build a BaselineSnapshot from an AnalyticsResult."""
    total_outcomes = sum(
        s.trade_outcomes for s in result.strategy_stats.values()
    )
    total_wins = sum(s.wins for s in result.strategy_stats.values())
    overall_win_rate = total_wins / total_outcomes if total_outcomes > 0 else None

    total_pnl = sum(
        s.total_pnl for s in result.strategy_stats.values()
    )
    avg_pnl = total_pnl / total_outcomes if total_outcomes > 0 else None

    return BaselineSnapshot(
        run_id=run_id,
        total_events=result.data_quality.total_events,
        overall_win_rate=overall_win_rate,
        avg_pnl=avg_pnl,
        strategy_win_rates={
            sid: s.win_rate for sid, s in result.strategy_stats.items()
        },
        regime_win_rates={
            rid: r.win_rate for rid, r in result.regime_stats.items()
        },
        strategy_distribution={
            sid: s.total_events for sid, s in result.strategy_stats.items()
        },
        regime_distribution={
            rid: r.total_events for rid, r in result.regime_stats.items()
        },
    )


class AnalyticsBaselineWriter:
    """Appends a BaselineSnapshot to data/system/analytics_baseline.json."""

    def __init__(self, baseline_file: Path | None = None) -> None:
        self._file = baseline_file or _BASELINE_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, snapshot: BaselineSnapshot) -> None:
        snapshots = self.read_all()
        snapshots.append(snapshot.to_dict())
        with open(self._file, "w", encoding="utf-8") as fh:
            json.dump(snapshots, fh, indent=2)

    def read_all(self) -> list[dict]:
        """Return all stored snapshots as dicts (oldest first)."""
        if not self._file.exists():
            return []
        with open(self._file, encoding="utf-8") as fh:
            return json.load(fh)

    def latest(self) -> dict | None:
        snapshots = self.read_all()
        return snapshots[-1] if snapshots else None
