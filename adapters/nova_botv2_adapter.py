"""
NovaBotV2 Read-Only Adapter for NovaTacticBot.

Reads NovaBotV2's data/system/result_snapshot.json and converts observable
worker state into TacticalEvents of type SYSTEM_EVENT.

Safe fields used (per docs/bridge_adapter_spec.md in NovaBotV2):
  status, worker_entrypoint_status, worker_entrypoint.status,
  worker_entrypoint.final_status, worker_entrypoint.readiness_status,
  worker_entrypoint.queue_total, worker_entrypoint.selected_task_id,
  worker_entrypoint.selected_task_priority, worker_entrypoint.errors,
  cycle_report.readiness_status, cycle_report.queue_total,
  cycle_report.eligible_tasks, completed_at, report_only, redaction_applied.

Produces one SYSTEM_EVENT per loaded snapshot encoding worker health.
No broker access. No writes to NovaBotV2. ADVISORY_ONLY.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from adapters.base_adapter import BaseAdapter
from core.tactic_event import EventType, SourceBot, TacticalEvent

logger = logging.getLogger(__name__)

_NOVA_ROOT = Path(__file__).resolve().parents[3]  # C:\NovaGPT

DEFAULT_SOURCE_DIR = _NOVA_ROOT / "Apps" / "NovaBotV2" / "data" / "system"
_SNAPSHOT_FILE = "result_snapshot.json"
MAX_SNAPSHOT_BYTES = 65536


def _safe_str(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    return str(value)


class NovaBotV2Adapter(BaseAdapter):
    """Read-only adapter for NovaBotV2 result_snapshot.json."""

    SOURCE_BOT = SourceBot.NOVA_BOT_V2

    def __init__(self, source_dir: Optional[str | Path] = None) -> None:
        super().__init__(source_dir or DEFAULT_SOURCE_DIR)

    def _load_from_source(self) -> None:
        snapshot_path = self.source_dir / _SNAPSHOT_FILE

        # --- Size guard ---
        try:
            size = snapshot_path.stat().st_size
        except FileNotFoundError:
            self._record_error(f"NovaBotV2 snapshot not found: {snapshot_path}")
            return
        except OSError as exc:
            self._record_error(f"Cannot stat NovaBotV2 snapshot: {exc}")
            return

        if size > MAX_SNAPSHOT_BYTES:
            self._record_error(
                f"NovaBotV2 snapshot too large ({size} bytes > {MAX_SNAPSHOT_BYTES})"
            )
            return

        # --- Parse ---
        try:
            payload: dict[str, Any] = json.loads(
                snapshot_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            self._record_error(f"NovaBotV2 snapshot invalid JSON: {exc}")
            return
        except OSError as exc:
            self._record_error(f"NovaBotV2 snapshot unreadable: {exc}")
            return

        if not isinstance(payload, dict):
            self._record_error("NovaBotV2 snapshot is not a JSON object")
            return

        # --- Build event ---
        event = self._event_from_snapshot(payload, str(snapshot_path))
        if event is not None:
            self._add_event(event)

    def _event_from_snapshot(
        self, payload: dict[str, Any], source_file: str
    ) -> Optional[TacticalEvent]:
        """Convert a NovaBotV2 result_snapshot dict to a TacticalEvent."""
        worker_entry = payload.get("worker_entrypoint") or {}
        cycle = payload.get("cycle_report") or {}

        worker_status = _safe_str(
            payload.get("worker_entrypoint_status") or worker_entry.get("status"),
            "UNKNOWN",
        )
        final_status = _safe_str(worker_entry.get("final_status"), "UNKNOWN")
        readiness_status = _safe_str(worker_entry.get("readiness_status"), "UNKNOWN")
        queue_total = int(worker_entry.get("queue_total") or cycle.get("queue_total") or 0)
        eligible_tasks = int(cycle.get("eligible_tasks") or 0)
        selected_task_id = _safe_str(worker_entry.get("selected_task_id"), "none")
        selected_priority = _safe_str(worker_entry.get("selected_task_priority"), "unknown")
        errors: list[str] = list(worker_entry.get("errors") or [])
        completed_at = _safe_str(payload.get("completed_at"), "")
        report_only = bool(payload.get("report_only", True))

        # score: healthy worker = 1.0; UNKNOWN/error = 0.0
        healthy = worker_status in ("READY", "READY_FOR_PHASE_7", "READY_FOR_PHASE_8", "READY_FOR_PHASE_9")
        score = 1.0 if healthy and not errors else 0.5 if not errors else 0.0

        metadata: dict[str, Any] = {
            "worker_status": worker_status,
            "final_status": final_status,
            "readiness_status": readiness_status,
            "queue_total": queue_total,
            "eligible_tasks": eligible_tasks,
            "selected_task_id": selected_task_id,
            "selected_task_priority": selected_priority,
            "errors": errors,
            "completed_at": completed_at,
            "report_only": report_only,
            "source_file": source_file,
        }

        try:
            return TacticalEvent(
                source_bot=self.SOURCE_BOT,
                event_type=EventType.SYSTEM_EVENT,
                strategy_id=f"worker_health_{worker_status.lower()}",
                score=score,
                metadata=metadata,
            )
        except Exception as exc:
            self._record_error(f"Failed to build TacticalEvent from NovaBotV2 snapshot: {exc}")
            return None
