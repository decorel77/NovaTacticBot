"""Tests for TACTIC-EL-001: tactic event log schema."""
import json
import pytest
from pathlib import Path

from utils.tactic_event_logger import (
    AnalysisRunPayload,
    AdapterErrorPayload,
    SourceStalePayload,
    RecommendationProducedPayload,
    TacticEventLogger,
    TacticEventType,
)


@pytest.fixture
def logger(tmp_path):
    return TacticEventLogger(log_file=tmp_path / "events.jsonl")


def read_entries(logger):
    return [json.loads(l) for l in logger._log_file.read_text().strip().splitlines()]


class TestTacticEventLogger:
    def test_log_analysis_run(self, logger):
        logger.log_analysis_run(AnalysisRunPayload(
            sources_ingested=3, event_count=42,
            duration_seconds=1.5, reports_generated=2,
        ))
        entries = read_entries(logger)
        assert len(entries) == 1
        assert entries[0]["event_type"] == "ANALYSIS_RUN"
        assert entries[0]["payload"]["sources_ingested"] == 3
        assert entries[0]["schema_version"] == "1.0"

    def test_log_adapter_error(self, logger):
        logger.log_adapter_error(AdapterErrorPayload(
            source_file="data/raw/options.csv",
            error_type="JSONDecodeError",
            error_message="Unexpected EOF",
            event_count_impact=10,
        ))
        entries = read_entries(logger)
        assert entries[0]["event_type"] == "ADAPTER_ERROR"
        assert entries[0]["payload"]["source_file"] == "data/raw/options.csv"

    def test_log_source_stale(self, logger):
        logger.log_source_stale(SourceStalePayload(
            source_file="data/raw/signals.json",
            last_modified_iso="2026-06-08T10:00:00+00:00",
            age_hours=26.0,
            threshold_hours=24.0,
        ))
        entries = read_entries(logger)
        assert entries[0]["event_type"] == "SOURCE_STALE"
        assert entries[0]["payload"]["age_hours"] == 26.0

    def test_log_recommendation_produced(self, logger):
        logger.log_recommendation_produced(RecommendationProducedPayload(
            strategy_id="covered_call",
            recommendation_quality_score=0.85,
            top_regime_fit="BULL",
            edge_erosion_warning=False,
        ))
        entries = read_entries(logger)
        assert entries[0]["event_type"] == "RECOMMENDATION_PRODUCED"
        assert entries[0]["payload"]["strategy_id"] == "covered_call"

    def test_multiple_events_appended(self, logger):
        logger.log_analysis_run(AnalysisRunPayload(1, 5, 0.5, 1))
        logger.log_adapter_error(AdapterErrorPayload("f.csv", "ValueError", "bad", 0))
        entries = read_entries(logger)
        assert len(entries) == 2

    def test_no_broker_imports(self):
        import utils.tactic_event_logger as mod
        import inspect
        src = inspect.getsource(mod)
        for banned in ("ib_insync", "ibapi", "alpaca", "ccxt"):
            assert banned not in src

    def test_log_file_created_automatically(self, tmp_path):
        deep = tmp_path / "nested" / "dir"
        tl = TacticEventLogger(log_file=deep / "events.jsonl")
        tl.log_analysis_run(AnalysisRunPayload(1, 1, 0.1, 1))
        assert (deep / "events.jsonl").exists()

    def test_timestamp_present(self, logger):
        logger.log_analysis_run(AnalysisRunPayload(1, 1, 0.1, 1))
        entries = read_entries(logger)
        assert "timestamp" in entries[0]
        assert entries[0]["timestamp"].endswith("+00:00") or "Z" in entries[0]["timestamp"] or "T" in entries[0]["timestamp"]
