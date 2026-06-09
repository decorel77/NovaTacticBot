"""
TacticBot result snapshot writer.

Writes data/system/result_snapshot.json after each analysis run so that
NovaBridge can observe TacticBot state via its adapter.

Fields:
  phase                       — str ("ANALYTICS")
  status                      — str ("OK" | "EMPTY" | "ERROR")
  top_strategy                — str | null
  top_regime_fit              — str | null
  last_run_timestamp          — ISO-8601 UTC
  event_count                 — int
  edge_erosion_warnings       — list[str]   strategy IDs with active warnings
  recommendation_quality_score — float | null
  schema_version              — "1.0"

ADVISORY_ONLY. No broker imports. Writes to data/system/ only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.tactic_analytics_engine import AnalyticsResult

_DEFAULT_SYSTEM_DIR = Path(__file__).resolve().parents[1] / "data" / "system"
_SNAPSHOT_FILE = _DEFAULT_SYSTEM_DIR / "result_snapshot.json"

SCHEMA_VERSION = "1.0"
PHASE = "ANALYTICS"


@dataclass
class TacticSnapshot:
    phase: str = PHASE
    status: str = "OK"
    top_strategy: Optional[str] = None
    top_regime_fit: Optional[str] = None
    last_run_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    event_count: int = 0
    edge_erosion_warnings: list[str] = field(default_factory=list)
    recommendation_quality_score: Optional[float] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def snapshot_from_result(result: AnalyticsResult) -> TacticSnapshot:
    """Build a TacticSnapshot from an AnalyticsResult."""
    event_count = result.data_quality.total_events
    status = "EMPTY" if event_count == 0 else "OK"

    # Top strategy: highest win_rate with at least 1 trade outcome
    top_strategy = None
    best_wr = -1.0
    for sid, s in result.strategy_stats.items():
        if s.win_rate is not None and s.win_rate > best_wr and s.trade_outcomes > 0:
            best_wr = s.win_rate
            top_strategy = sid

    # Top regime fit: regime with most trade outcomes
    top_regime_fit = None
    best_count = -1
    for rid, r in result.regime_stats.items():
        if r.trade_outcomes > best_count:
            best_count = r.trade_outcomes
            top_regime_fit = rid

    edge_erosion_warnings = [w.strategy_id for w in result.edge_erosion.warnings]
    rq_score = result.recommendation_quality.avg_score

    return TacticSnapshot(
        status=status,
        top_strategy=top_strategy,
        top_regime_fit=top_regime_fit,
        event_count=event_count,
        edge_erosion_warnings=edge_erosion_warnings,
        recommendation_quality_score=rq_score,
    )


class TacticSnapshotWriter:
    """Writes result_snapshot.json to data/system/ after each run."""

    def __init__(self, snapshot_file: Path | None = None) -> None:
        self._file = snapshot_file or _SNAPSHOT_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot: TacticSnapshot) -> Path:
        self._file.write_text(
            json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8"
        )
        return self._file

    def read(self) -> dict | None:
        if not self._file.exists():
            return None
        with open(self._file, encoding="utf-8") as fh:
            return json.load(fh)
