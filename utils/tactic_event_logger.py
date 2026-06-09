"""
Internal event log schema and writer for NovaTacticBot.

Writes structured JSONL entries to data/logs/tactic_events.jsonl.
No broker imports. ADVISORY_ONLY — read/write to data/logs/ only.

Event types:
  ANALYSIS_RUN          — one entry per full analysis run
  ADAPTER_ERROR         — one entry per failing source adapter
  SOURCE_STALE          — one entry when a source file is older than threshold
  RECOMMENDATION_PRODUCED — one entry per recommendation emitted
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolved relative to this file's repo root
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
_LOG_FILE = _DEFAULT_LOG_DIR / "tactic_events.jsonl"


class TacticEventType(str, Enum):
    ANALYSIS_RUN = "ANALYSIS_RUN"
    ADAPTER_ERROR = "ADAPTER_ERROR"
    SOURCE_STALE = "SOURCE_STALE"
    RECOMMENDATION_PRODUCED = "RECOMMENDATION_PRODUCED"


@dataclass
class AnalysisRunPayload:
    sources_ingested: int
    event_count: int
    duration_seconds: float
    reports_generated: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class AdapterErrorPayload:
    source_file: str
    error_type: str
    error_message: str
    event_count_impact: int = 0


@dataclass
class SourceStalePayload:
    source_file: str
    last_modified_iso: str
    age_hours: float
    threshold_hours: float


@dataclass
class RecommendationProducedPayload:
    strategy_id: str
    recommendation_quality_score: float
    top_regime_fit: str | None = None
    edge_erosion_warning: bool = False


@dataclass
class TacticLogEntry:
    event_type: TacticEventType
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class TacticEventLogger:
    """Appends structured log entries to data/logs/tactic_events.jsonl."""

    def __init__(self, log_file: Path | None = None) -> None:
        self._log_file = log_file or _LOG_FILE
        self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: TacticLogEntry) -> None:
        with open(self._log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")
        logger.debug("Logged %s event", entry.event_type.value)

    def log_analysis_run(self, payload: AnalysisRunPayload) -> None:
        self._write(TacticLogEntry(
            event_type=TacticEventType.ANALYSIS_RUN,
            payload=asdict(payload),
        ))

    def log_adapter_error(self, payload: AdapterErrorPayload) -> None:
        self._write(TacticLogEntry(
            event_type=TacticEventType.ADAPTER_ERROR,
            payload=asdict(payload),
        ))

    def log_source_stale(self, payload: SourceStalePayload) -> None:
        self._write(TacticLogEntry(
            event_type=TacticEventType.SOURCE_STALE,
            payload=asdict(payload),
        ))

    def log_recommendation_produced(self, payload: RecommendationProducedPayload) -> None:
        self._write(TacticLogEntry(
            event_type=TacticEventType.RECOMMENDATION_PRODUCED,
            payload=asdict(payload),
        ))
