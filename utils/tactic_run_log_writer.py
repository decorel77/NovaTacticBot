"""
TacticBot run log writer.

Appends one structured JSON entry per analysis run to
data/logs/tactic_run_log.jsonl.

Fields per entry:
  run_id              — uuid4 string
  timestamp           — ISO-8601 UTC
  sources_ingested    — int
  event_counts        — dict[str, int] by EventType name
  duration_seconds    — float
  reports_generated   — int
  warnings            — list[str]
  schema_version      — "1.0"

No broker imports. ADVISORY_ONLY — writes to data/logs/ only.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
_RUN_LOG_FILE = _DEFAULT_LOG_DIR / "tactic_run_log.jsonl"

SCHEMA_VERSION = "1.0"


@dataclass
class RunLogEntry:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sources_ingested: int = 0
    event_counts: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    reports_generated: int = 0
    warnings: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


class TacticRunLogWriter:
    """Appends a RunLogEntry to data/logs/tactic_run_log.jsonl after each run."""

    def __init__(self, log_file: Path | None = None) -> None:
        self._log_file = log_file or _RUN_LOG_FILE
        self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def write(self, entry: RunLogEntry) -> None:
        with open(self._log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")

    def read_all(self) -> list[dict]:
        """Return all run log entries as dicts (oldest first)."""
        if not self._log_file.exists():
            return []
        entries = []
        with open(self._log_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
