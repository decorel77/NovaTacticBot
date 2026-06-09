"""Tests for the TacticReportGenerator."""

import pytest
from pathlib import Path

from core.tactic_analytics_engine import AnalyticsResult, TacticAnalyticsEngine
from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent
from utils.tactic_report_generator import TacticReportGenerator


def run_pipeline(events):
    engine = TacticAnalyticsEngine()
    result = engine.run(events)
    return result


class TestReportGeneration:
    def test_generates_file(self, tmp_path):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        path = gen.generate(result, output_path=tmp_path / "report.md")
        assert path.exists()
        content = path.read_text()
        assert "NovaTacticBot Intelligence Report" in content

    def test_advisory_only_footer(self, tmp_path):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        path = gen.generate(result, output_path=tmp_path / "report.md")
        content = path.read_text()
        assert "advisory only" in content.lower()
        assert "no trades" in content.lower()

    def test_report_contains_strategy_table(self, tmp_path):
        events = [
            TacticalEvent(
                source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
                event_type=EventType.TRADE_OUTCOME,
                strategy_id="covered_call",
                outcome=Outcome.WIN,
                realized_pnl=50.0,
            )
        ]
        result = run_pipeline(events)
        gen = TacticReportGenerator()
        path = gen.generate(result, output_path=tmp_path / "report.md")
        content = path.read_text()
        assert "covered_call" in content
        assert "Strategy Analysis" in content

    def test_report_contains_regime_section(self, tmp_path):
        events = [
            TacticalEvent(
                source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
                event_type=EventType.TRADE_OUTCOME,
                strategy_id="iron_condor",
                regime=Regime.HIGH_VOL,
                outcome=Outcome.LOSS,
            )
        ]
        result = run_pipeline(events)
        gen = TacticReportGenerator()
        path = gen.generate(result, output_path=tmp_path / "report.md")
        content = path.read_text()
        assert "Regime Analysis" in content
        assert "HIGH_VOL" in content

    def test_empty_data_report_is_valid(self, tmp_path):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        path = gen.generate(result, output_path=tmp_path / "report.md")
        content = path.read_text()
        assert len(content) > 100
        assert "Executive Summary" in content

    def test_creates_parent_directories(self, tmp_path):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        deep_path = tmp_path / "a" / "b" / "c" / "report.md"
        path = gen.generate(result, output_path=deep_path)
        assert path.exists()
