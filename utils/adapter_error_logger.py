"""
TacticBot adapter error logger.

Logs ADAPTER_ERROR events when any adapter source file fails to parse.
Appends structured JSON entries to data/logs/tactic_adapter_errors.jsonl.

Entry schema (v1.0):
  timestamp       — ISO-8601 UTC
  event_type      — "ADAPTER_ERROR"
  adapter_name    — str
  file_path       — str
  error_type      — str  (exception class name)
  error_message   — str
  event_count_impact — int  (events lost due to this failure; 0 if unknown)
  schema_version  — "1.0"

Requires MASTER-003 (run log writer) complete — same log directory.
ADVISORY_ONLY. No broker imports. Writes to data/logs/ only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
_ERROR_LOG_FILE = _DEFAULT_LOG_DIR / "tactic_adapter_errors.jsonl"

SCHEMA_VERSION = "1.0"
EVENT_TYPE = "ADAPTER_ERROR"


@dataclass
class AdapterErrorEntry:
    adapter_name: str
    file_path: str
    error_type: str
    error_message: str
    event_count_impact: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    event_type: str = EVENT_TYPE
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


class AdapterErrorLogger:
    """Appends ADAPTER_ERROR entries to data/logs/tactic_adapter_errors.jsonl."""

    def __init__(self, log_file: Optional[Path] = None) -> None:
        self._log_file = log_file or _ERROR_LOG_FILE
        self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: AdapterErrorEntry) -> None:
        with open(self._log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")

    def log_exception(
        self,
        adapter_name: str,
        file_path: str,
        exc: Exception,
        event_count_impact: int = 0,
    ) -> None:
        """Convenience wrapper: build entry from a caught exception."""
        entry = AdapterErrorEntry(
            adapter_name=adapter_name,
            file_path=str(file_path),
            error_type=type(exc).__name__,
            error_message=str(exc),
            event_count_impact=event_count_impact,
        )
        self.log(entry)

    def read_all(self) -> list[dict]:
        """Return all logged errors (oldest first)."""
        if not self._log_file.exists():
            return []
        entries = []
        with open(self._log_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
