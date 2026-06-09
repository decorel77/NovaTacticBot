"""Tests for run_history_tracker.py (MASTER-005)."""
from pathlib import Path

from utils.run_history_tracker import RunHistoryEntry, RunHistoryTracker


def test_append_and_read(tmp_path):
    tracker = RunHistoryTracker(tmp_path / "run_history.json")
    e1 = RunHistoryEntry(events_processed=10, reports_generated=2)
    e2 = RunHistoryEntry(events_processed=20, reports_generated=3, errors=["warn"])
    tracker.append(e1)
    tracker.append(e2)
    entries = tracker.read_all()
    assert len(entries) == 2
    assert entries[0]["run_count"] == 1
    assert entries[1]["run_count"] == 2
    assert entries[1]["events_processed"] == 20


def test_latest(tmp_path):
    tracker = RunHistoryTracker(tmp_path / "run_history.json")
    tracker.append(RunHistoryEntry(events_processed=5))
    tracker.append(RunHistoryEntry(events_processed=15))
    assert tracker.latest()["events_processed"] == 15


def test_count(tmp_path):
    tracker = RunHistoryTracker(tmp_path / "run_history.json")
    assert tracker.count() == 0
    tracker.append(RunHistoryEntry())
    assert tracker.count() == 1


def test_missing_file(tmp_path):
    tracker = RunHistoryTracker(tmp_path / "missing.json")
    assert tracker.read_all() == []
    assert tracker.latest() is None


def test_no_broker_imports():
    import utils.run_history_tracker as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "ibapi" not in src
    assert "import broker" not in src.lower()
