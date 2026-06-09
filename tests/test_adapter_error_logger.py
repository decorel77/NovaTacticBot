"""Tests for adapter_error_logger.py (MASTER-004)."""
from pathlib import Path

from utils.adapter_error_logger import AdapterErrorEntry, AdapterErrorLogger


def test_log_and_read(tmp_path):
    logger = AdapterErrorLogger(tmp_path / "errors.jsonl")
    entry = AdapterErrorEntry(
        adapter_name="options_adapter",
        file_path="/data/events.jsonl",
        error_type="JSONDecodeError",
        error_message="Unexpected EOF",
        event_count_impact=5,
    )
    logger.log(entry)
    all_entries = logger.read_all()
    assert len(all_entries) == 1
    e = all_entries[0]
    assert e["event_type"] == "ADAPTER_ERROR"
    assert e["adapter_name"] == "options_adapter"
    assert e["event_count_impact"] == 5


def test_log_exception(tmp_path):
    logger = AdapterErrorLogger(tmp_path / "errors.jsonl")
    exc = ValueError("bad file")
    logger.log_exception("test_adapter", "/path/to/file.json", exc, event_count_impact=3)
    entries = logger.read_all()
    assert len(entries) == 1
    assert entries[0]["error_type"] == "ValueError"
    assert entries[0]["event_count_impact"] == 3


def test_multiple_entries(tmp_path):
    logger = AdapterErrorLogger(tmp_path / "errors.jsonl")
    for i in range(3):
        logger.log(AdapterErrorEntry(
            adapter_name="a", file_path=f"/f{i}", error_type="E", error_message="m"
        ))
    assert len(logger.read_all()) == 3


def test_missing_file(tmp_path):
    logger = AdapterErrorLogger(tmp_path / "nofile.jsonl")
    assert logger.read_all() == []


def test_no_broker_imports():
    import utils.adapter_error_logger as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "ibapi" not in src
    assert "import broker" not in src.lower()
