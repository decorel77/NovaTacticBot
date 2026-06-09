"""Tests for the OptionsAdapter."""

import json
import csv
import pytest
from pathlib import Path

from adapters.options_adapter import OptionsAdapter
from core.tactic_event import EventType, Outcome, Regime, SourceBot


@pytest.fixture
def tmp_source(tmp_path):
    return tmp_path


class TestOptionsAdapterNoSource:
    def test_no_source_dir_returns_empty(self):
        adapter = OptionsAdapter(source_dir=None)
        events = adapter.load()
        assert events == []

    def test_nonexistent_dir_returns_empty(self):
        adapter = OptionsAdapter(source_dir="/nonexistent/path/xyz")
        events = adapter.load()
        assert events == []


class TestOptionsAdapterJSON:
    def test_loads_single_json_record(self, tmp_source):
        record = {
            "strategy_id": "covered_call",
            "event_type": "trade_outcome",
            "regime": "normal",
            "score": 0.8,
            "expected_rr": 1.5,
            "realized_pnl": 45.0,
            "outcome": "win",
        }
        (tmp_source / "trades.json").write_text(json.dumps([record]))
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert len(events) == 1
        e = events[0]
        assert e.source_bot == SourceBot.NOVA_BOT_V2_OPTIONS
        assert e.strategy_id == "covered_call"
        assert e.event_type == EventType.TRADE_OUTCOME
        assert e.regime == Regime.NORMAL
        assert e.score == 0.8
        assert e.outcome == Outcome.WIN

    def test_loads_wrapped_json(self, tmp_source):
        data = {"trades": [
            {"strategy_id": "iron_condor", "outcome": "loss"},
            {"strategy_id": "cash_secured_put", "outcome": "win"},
        ]}
        (tmp_source / "report.json").write_text(json.dumps(data))
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert len(events) == 2

    def test_malformed_json_recorded_as_error(self, tmp_source):
        (tmp_source / "bad.json").write_text("{not valid json")
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert events == []
        assert len(adapter.load_errors) == 1

    def test_multiple_json_files(self, tmp_source):
        for i in range(3):
            records = [{"strategy_id": f"strat_{i}", "outcome": "win"}]
            (tmp_source / f"file_{i}.json").write_text(json.dumps(records))
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert len(events) == 3


class TestOptionsAdapterCSV:
    def test_loads_csv_file(self, tmp_source):
        rows = [
            {"strategy_id": "bull_put_spread", "outcome": "win", "realized_pnl": "120.0"},
            {"strategy_id": "bull_put_spread", "outcome": "loss", "realized_pnl": "-60.0"},
        ]
        csv_path = tmp_source / "history.csv"
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert len(events) == 2
        assert events[0].outcome == Outcome.WIN
        assert events[1].realized_pnl == pytest.approx(-60.0)

    def test_csv_with_unknown_fields_stored_in_metadata(self, tmp_source):
        rows = [{"strategy_id": "x", "outcome": "win", "custom_field": "abc"}]
        csv_path = tmp_source / "extra.csv"
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert events[0].metadata.get("custom_field") == "abc"


class TestOptionsAdapterLog:
    def test_loads_jsonline_log(self, tmp_source):
        lines = [
            json.dumps({"strategy_id": "covered_call", "outcome": "win"}),
            "not a json line - ignored",
            json.dumps({"strategy_id": "naked_put", "outcome": "loss"}),
        ]
        (tmp_source / "bot.log").write_text("\n".join(lines), encoding="utf-8")
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert len(events) == 2


class TestOptionsAdapterEdgeCases:
    def test_empty_directory_returns_empty(self, tmp_source):
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert events == []

    def test_missing_strategy_id_falls_back_to_unknown(self, tmp_source):
        record = {"outcome": "win", "realized_pnl": 50.0}
        (tmp_source / "t.json").write_text(json.dumps([record]))
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert len(events) == 1
        assert events[0].strategy_id == "unknown"

    def test_unknown_outcome_produces_none(self, tmp_source):
        record = {"strategy_id": "strat", "outcome": "completely_unknown_value"}
        (tmp_source / "t.json").write_text(json.dumps([record]))
        adapter = OptionsAdapter(source_dir=tmp_source)
        events = adapter.load()
        assert events[0].outcome is None
