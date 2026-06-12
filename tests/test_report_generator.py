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

    def test_small_real_outcome_sample_is_marked_diagnostic_only(self, tmp_path):
        events = [
            TacticalEvent(
                source_bot=SourceBot.NOVA_BOT_V2,
                event_type=EventType.TRADE_OUTCOME,
                strategy_id="BREAKOUT",
                outcome=Outcome.WIN,
                realized_pnl=5.0,
                metadata={"data_is_real": True},
            )
        ]
        result = run_pipeline(events)
        gen = TacticReportGenerator()
        path = gen.generate(result, output_path=tmp_path / "report.md")
        content = path.read_text()
        assert "Overall win rate" in content
        assert "DIAGNOSTIC_ONLY" in content
        assert "completed trades 1 < 30" in content

    def test_creates_parent_directories(self, tmp_path):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        deep_path = tmp_path / "a" / "b" / "c" / "report.md"
        path = gen.generate(result, output_path=deep_path)
        assert path.exists()

    def test_statistical_floor_section_fails_closed_without_evidence(self):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        content = gen._render(
            result,
            "NovaBotV2Options",
            supplementary={"statistical_floor": []},
        )
        assert "Statistical Floor (QA-016)" in content
        assert "DIAGNOSTIC_ONLY" in content
        assert "no statistical floor evidence supplied" in content

    def test_statistical_floor_section_renders_sample_counts(self):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        content = gen._render(
            result,
            "NovaBotV2Options",
            supplementary={
                "statistical_floor": [
                    {
                        "signal_id": "sig-1",
                        "strategy_id": "covered_call",
                        "strength": "DIAGNOSTIC_ONLY",
                        "metrics": {"sample_size": 12},
                        "refusal_reasons": ["sample_size_below_floor:12<30"],
                    }
                ]
            },
        )
        assert "sig-1" in content
        assert "covered_call" in content
        assert "12" in content
        assert "sample_size_below_floor:12<30" in content

    def test_statistical_floor_section_refuses_unapproved_strong_label(self):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        content = gen._render(
            result,
            "NovaBotV2Options",
            supplementary={
                "statistical_floor": [
                    {
                        "signal_id": "sig-strong",
                        "strategy_id": "covered_call",
                        "strength": "STRONG",
                        "metrics": {"sample_size": 99},
                    }
                ]
            },
        )
        assert "| sig-strong | covered_call | 99 | DIAGNOSTIC_ONLY | none |" in content

    def test_strategy_correlation_section_withholds_small_sample(self):
        result = run_pipeline([])
        gen = TacticReportGenerator()
        content = gen._render(
            result,
            "NovaBotV2Options",
            supplementary={
                "strategy_correlation": {
                    "source_a": "NovaBotV2",
                    "source_b": "NovaBotV2Options",
                    "overlap_days": 4,
                    "insufficient_sample": True,
                    "correlation": None,
                    "refusal_reasons": ["insufficient_overlap:4<30"],
                    "caveats": ["Diagnostic only."],
                }
            },
        )
        assert "Strategy Outcome Correlation (QA-019)" in content
        assert "INSUFFICIENT SAMPLE" in content
        assert "no correlation value is reported" in content
        assert "insufficient_overlap:4<30" in content
