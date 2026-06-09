"""
TacticBot run history tracker.

Appends a summary of each TacticBot run to data/system/run_history.json.
Enables cross-run trend analysis (TACTIC-HA-005).

Entry schema (v1.0):
  timestamp           — ISO-8601 UTC
  run_id              — str (uuid or caller-supplied)
  run_count           — int (1-based index within this file)
  events_processed    — int
  reports_generated   — int
  errors              — list[str]
  schema_version      — "1.0"

ADVISORY_ONLY. No broker imports. Writes to data/system/ only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid as _uuid

_DEFAULT_SYSTEM_DIR = Path(__file__).resolve().parents[1] / "data" / "system"
_HISTORY_FILE = _DEFAULT_SYSTEM_DIR / "run_history.json"

SCHEMA_VERSION = "1.0"


@dataclass
class RunHistoryEntry:
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    run_id: str = field(default_factory=lambda: str(_uuid.uuid4()))
    run_count: int = 1
    events_processed: int = 0
    reports_generated: int = 0
    errors: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


class RunHistoryTracker:
    """Appends RunHistoryEntry records to data/system/run_history.json."""

    def __init__(self, history_file: Optional[Path] = None) -> None:
        self._file = history_file or _HISTORY_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: RunHistoryEntry) -> None:
        entries = self.read_all()
        # Auto-set run_count based on current length
        entry.run_count = len(entries) + 1
        entries.append(entry.to_dict())
        with open(self._file, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2)

    def read_all(self) -> list[dict]:
        """Return all run history entries (oldest first)."""
        if not self._file.exists():
            return []
        with open(self._file, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []

    def latest(self) -> Optional[dict]:
        entries = self.read_all()
        return entries[-1] if entries else None

    def count(self) -> int:
        return len(self.read_all())
