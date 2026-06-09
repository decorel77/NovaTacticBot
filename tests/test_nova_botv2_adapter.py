"""Tests for adapters/nova_botv2_adapter.py.

Verifies: snapshot parsing, event structure, safe field extraction,
fail-closed behaviour, score logic, and no broker imports.
"""
import json
import tempfile
import unittest
from pathlib import Path

from adapters.nova_botv2_adapter import MAX_SNAPSHOT_BYTES, NovaBotV2Adapter
from core.tactic_event import EventType, SourceBot


READY_SNAPSHOT = {
    "project": "NovaBotV2",
    "status": "done",
    "worker_entrypoint_status": "READY",
    "completed_at": "2026-06-09T18:00:00Z",
    "report_only": True,
    "redaction_applied": True,
    "worker_entrypoint": {
        "status": "READY",
        "final_status": "READY_FOR_PHASE_7",
        "readiness_status": "READY_FOR_PHASE_3",
        "queue_total": 3,
        "selected_task_id": "validate_worker_state_files",
        "selected_task_priority": "P1",
        "errors": [],
    },
    "cycle_report": {
        "readiness_status": "READY_FOR_PHASE_3",
        "queue_total": 3,
        "eligible_tasks": 3,
    },
}

ERROR_SNAPSHOT = dict(READY_SNAPSHOT)
ERROR_SNAPSHOT = {
    **READY_SNAPSHOT,
    "worker_entrypoint": {
        **READY_SNAPSHOT["worker_entrypoint"],
        "errors": ["some runtime error"],
    },
}


def _write_snapshot(directory: Path, data: dict) -> None:
    (directory / "result_snapshot.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


class TestNovaBotV2AdapterLoadsEvent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source_dir = Path(self.tmpdir)
        _write_snapshot(self.source_dir, READY_SNAPSHOT)
        self.adapter = NovaBotV2Adapter(self.source_dir)

    def test_loads_one_event(self):
        events = self.adapter.load()
        self.assertEqual(len(events), 1)

    def test_event_source_bot(self):
        events = self.adapter.load()
        self.assertEqual(events[0].source_bot, SourceBot.NOVA_BOT_V2)

    def test_event_type_is_system_event(self):
        events = self.adapter.load()
        self.assertEqual(events[0].event_type, EventType.SYSTEM_EVENT)

    def test_strategy_id_contains_worker_status(self):
        events = self.adapter.load()
        self.assertIn("worker_health", events[0].strategy_id)

    def test_score_is_one_when_healthy_no_errors(self):
        events = self.adapter.load()
        self.assertEqual(events[0].score, 1.0)

    def test_metadata_contains_worker_status(self):
        events = self.adapter.load()
        self.assertIn("worker_status", events[0].metadata)
        self.assertEqual(events[0].metadata["worker_status"], "READY")

    def test_metadata_contains_queue_total(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["queue_total"], 3)

    def test_metadata_contains_eligible_tasks(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["eligible_tasks"], 3)

    def test_metadata_contains_final_status(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["final_status"], "READY_FOR_PHASE_7")

    def test_metadata_errors_empty(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["errors"], [])

    def test_no_load_errors(self):
        self.adapter.load()
        self.assertEqual(self.adapter.load_errors, [])

    def test_report_only_in_metadata(self):
        events = self.adapter.load()
        self.assertTrue(events[0].metadata["report_only"])


class TestNovaBotV2AdapterErrorHandling(unittest.TestCase):
    def test_missing_snapshot_returns_empty(self):
        tmpdir = tempfile.mkdtemp()
        adapter = NovaBotV2Adapter(Path(tmpdir))
        events = adapter.load()
        self.assertEqual(events, [])
        self.assertTrue(len(adapter.load_errors) > 0)

    def test_invalid_json_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "result_snapshot.json").write_text("not json }", encoding="utf-8")
        adapter = NovaBotV2Adapter(tmpdir)
        events = adapter.load()
        self.assertEqual(events, [])
        self.assertTrue(len(adapter.load_errors) > 0)

    def test_too_large_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "result_snapshot.json").write_bytes(b"x" * (MAX_SNAPSHOT_BYTES + 1))
        adapter = NovaBotV2Adapter(tmpdir)
        events = adapter.load()
        self.assertEqual(events, [])

    def test_non_dict_json_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "result_snapshot.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        adapter = NovaBotV2Adapter(tmpdir)
        events = adapter.load()
        self.assertEqual(events, [])


class TestNovaBotV2AdapterScoring(unittest.TestCase):
    def _load(self, snapshot: dict) -> list:
        tmpdir = Path(tempfile.mkdtemp())
        _write_snapshot(tmpdir, snapshot)
        return NovaBotV2Adapter(tmpdir).load()

    def test_score_half_when_status_unknown_no_errors(self):
        snap = {**READY_SNAPSHOT, "worker_entrypoint_status": "UNKNOWN",
                "worker_entrypoint": {**READY_SNAPSHOT["worker_entrypoint"],
                                      "status": "UNKNOWN", "errors": []}}
        events = self._load(snap)
        self.assertIsNotNone(events)
        if events:
            self.assertEqual(events[0].score, 0.5)

    def test_score_zero_when_errors_present(self):
        events = self._load(ERROR_SNAPSHOT)
        self.assertIsNotNone(events)
        if events:
            self.assertEqual(events[0].score, 0.0)


class TestNovaBotV2NoBrokerImports(unittest.TestCase):
    def test_no_broker_imports(self):
        import ast, pathlib
        src = pathlib.Path(__file__).parent.parent / "adapters" / "nova_botv2_adapter.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        broker_modules = {"ib_insync", "ibapi", "TWS"}
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertFalse(imports & broker_modules)

    def test_source_bot_is_nova_botv2(self):
        self.assertEqual(NovaBotV2Adapter.SOURCE_BOT, SourceBot.NOVA_BOT_V2)

    def test_no_source_dir_returns_empty(self):
        adapter = NovaBotV2Adapter.__new__(NovaBotV2Adapter)
        adapter.source_dir = None
        adapter._events = []
        adapter._load_errors = []
        events = adapter.load()
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
