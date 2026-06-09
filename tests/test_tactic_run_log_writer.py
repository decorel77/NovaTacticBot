"""Tests for TacticRunLogWriter (TACTIC-EL-002)."""
import json
from pathlib import Path

import pytest

from utils.tactic_run_log_writer import RunLogEntry, TacticRunLogWriter


@pytest.fixture()
def tmp_log(tmp_path: Path) -> Path:
    return tmp_path / "tactic_run_log.jsonl"


def test_write_creates_file(tmp_log: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_log)
    entry = RunLogEntry(sources_ingested=3, duration_seconds=1.2, reports_generated=2)
    writer.write(entry)
    assert tmp_log.exists()


def test_write_appends_jsonl(tmp_log: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_log)
    writer.write(RunLogEntry(sources_ingested=1, duration_seconds=0.5))
    writer.write(RunLogEntry(sources_ingested=2, duration_seconds=1.0))
    lines = tmp_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_entry_schema_version(tmp_log: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_log)
    writer.write(RunLogEntry())
    data = json.loads(tmp_log.read_text(encoding="utf-8").splitlines()[0])
    assert data["schema_version"] == "1.0"


def test_entry_has_run_id_and_timestamp(tmp_log: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_log)
    writer.write(RunLogEntry())
    data = json.loads(tmp_log.read_text(encoding="utf-8").splitlines()[0])
    assert "run_id" in data and len(data["run_id"]) > 10
    assert "timestamp" in data and "T" in data["timestamp"]


def test_entry_event_counts(tmp_log: Path) -> None:
    entry = RunLogEntry(
        sources_ingested=2,
        event_counts={"TRADE_OUTCOME": 10, "REJECTION": 3},
        reports_generated=1,
        warnings=["source stale"],
    )
    writer = TacticRunLogWriter(log_file=tmp_log)
    writer.write(entry)
    data = json.loads(tmp_log.read_text(encoding="utf-8").splitlines()[0])
    assert data["event_counts"]["TRADE_OUTCOME"] == 10
    assert data["warnings"] == ["source stale"]


def test_read_all_empty_when_no_file(tmp_path: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_path / "nonexistent.jsonl")
    assert writer.read_all() == []


def test_read_all_returns_entries(tmp_log: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_log)
    writer.write(RunLogEntry(sources_ingested=1))
    writer.write(RunLogEntry(sources_ingested=2))
    entries = writer.read_all()
    assert len(entries) == 2
    assert entries[0]["sources_ingested"] == 1
    assert entries[1]["sources_ingested"] == 2


def test_run_ids_are_unique(tmp_log: Path) -> None:
    writer = TacticRunLogWriter(log_file=tmp_log)
    for _ in range(5):
        writer.write(RunLogEntry())
    entries = writer.read_all()
    ids = [e["run_id"] for e in entries]
    assert len(set(ids)) == 5


def test_no_broker_imports() -> None:
    import importlib
    mod = importlib.import_module("utils.tactic_run_log_writer")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "ib_insync" not in src
    assert "ibapi" not in src
