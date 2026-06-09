"""Tests for Analytics Engine v2 passes: symbol concentration, confidence
distribution, and candidate ranking."""

from __future__ import annotations

import pytest

from core.tactic_analytics_engine import TacticAnalyticsEngine
from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent


def _trade(symbol: str, strategy_id: str, outcome: str, pnl: float, score: float = 0.7):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id=strategy_id,
        outcome=outcome,
        realized_pnl=pnl,
        regime=Regime.BULL,
        score=score,
        metadata={"symbol": symbol},
    )


def _rejection(symbol: str, strategy_id: str):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.REJECTION,
        strategy_id=strategy_id,
        regime=Regime.BEAR,
        metadata={"symbol": symbol},
    )


def _rec(symbol: str, strategy_id: str, score: float = 0.6):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.RECOMMENDATION,
        strategy_id=strategy_id,
        regime=Regime.BULL,
        score=score,
        metadata={"symbol": symbol},
    )


class TestSymbolConcentration:
    def _run(self, events):
        return TacticAnalyticsEngine().run(events).symbol_concentration

    def test_counts_events_per_symbol(self):
        events = [
            _trade("AAPL", "LONG_CALL", Outcome.WIN, 100.0),
            _trade("AAPL", "LONG_CALL", Outcome.LOSS, -50.0),
            _trade("SPY", "CSP", Outcome.WIN, 80.0),
        ]
        sc = self._run(events)
        assert sc.by_symbol["AAPL"] == 2
        assert sc.by_symbol["SPY"] == 1

    def test_top_symbols_sorted_by_total_events(self):
        events = [
            _trade("AAPL", "LC", Outcome.WIN, 100.0),
            _trade("AAPL", "LC", Outcome.WIN, 100.0),
            _trade("SPY", "CSP", Outcome.WIN, 80.0),
        ]
        sc = self._run(events)
        assert sc.top_symbols[0] == "AAPL"

    def test_rejection_counts_tracked(self):
        events = [
            _rejection("TSLA", "LONG_CALL"),
            _rejection("TSLA", "LONG_CALL"),
            _rejection("AAPL", "LONG_CALL"),
        ]
        sc = self._run(events)
        assert sc.rejections_by_symbol["TSLA"] == 2
        assert sc.rejections_by_symbol["AAPL"] == 1

    def test_pnl_accumulates_per_symbol(self):
        events = [
            _trade("AAPL", "LC", Outcome.WIN, 100.0),
            _trade("AAPL", "LC", Outcome.WIN, 50.0),
        ]
        sc = self._run(events)
        assert sc.pnl_by_symbol["AAPL"] == pytest.approx(150.0)

    def test_events_without_symbol_ignored(self):
        t = TacticalEvent(
            source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
            event_type=EventType.TRADE_OUTCOME,
            strategy_id="X",
            outcome=Outcome.WIN,
            realized_pnl=10.0,
            metadata={},
        )
        sc = self._run([t])
        assert sc.by_symbol == {}

    def test_empty_events_returns_empty_concentration(self):
        sc = self._run([])
        assert sc.by_symbol == {}
        assert sc.top_symbols == []


class TestConfidenceDistribution:
    def _run(self, events):
        return TacticAnalyticsEngine().run(events).confidence_distribution

    def test_total_scored_matches_events_with_scores(self):
        events = [
            _trade("AAPL", "LC", Outcome.WIN, 100.0, score=0.8),
            _trade("SPY", "CSP", Outcome.WIN, 50.0, score=0.65),
            TacticalEvent(  # no score
                source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
                event_type=EventType.TRADE_OUTCOME,
                strategy_id="X",
                outcome=Outcome.WIN,
                realized_pnl=10.0,
            ),
        ]
        cd = self._run(events)
        assert cd.total_scored == 2

    def test_scores_bucketed_correctly(self):
        events = [
            _trade("AAPL", "LC", Outcome.WIN, 100.0, score=0.45),   # < 0.5
            _trade("SPY", "CSP", Outcome.LOSS, -50.0, score=0.55),  # 0.5–0.6
            _trade("TSLA", "LC", Outcome.WIN, 80.0, score=0.75),    # 0.7–0.8
        ]
        cd = self._run(events)
        labels = {b.label: b for b in cd.buckets}
        assert labels["< 0.5"].count == 1
        assert labels["0.5–0.6"].count == 1
        assert labels["0.7–0.8"].count == 1

    def test_win_rate_per_bucket(self):
        events = [
            _trade("A", "LC", Outcome.WIN, 100.0, score=0.75),
            _trade("B", "LC", Outcome.WIN, 100.0, score=0.72),
            _trade("C", "LC", Outcome.LOSS, -50.0, score=0.71),
        ]
        cd = self._run(events)
        bucket = next(b for b in cd.buckets if b.label == "0.7–0.8")
        assert bucket.win_rate == pytest.approx(2 / 3)

    def test_avg_score_computed(self):
        events = [
            _trade("A", "LC", Outcome.WIN, 100.0, score=0.6),
            _trade("B", "LC", Outcome.WIN, 100.0, score=0.8),
        ]
        cd = self._run(events)
        assert cd.avg_score == pytest.approx(0.7)

    def test_empty_events_returns_empty_distribution(self):
        cd = self._run([])
        assert cd.total_scored == 0
        assert cd.avg_score is None


class TestCandidateRanking:
    def _run(self, events):
        return TacticAnalyticsEngine().run(events).candidate_ranking

    def test_candidates_produced(self):
        events = [
            _trade("AAPL", "LONG_CALL", Outcome.WIN, 100.0, score=0.8),
            _trade("SPY", "CSP", Outcome.LOSS, -50.0, score=0.5),
        ]
        ranking = self._run(events)
        symbols = {c.symbol for c in ranking.candidates}
        assert "AAPL" in symbols
        assert "SPY" in symbols

    def test_sorted_by_composite_descending(self):
        events = [
            _trade("AAPL", "LC", Outcome.WIN, 100.0, score=0.9),   # high composite
            _trade("SPY", "CSP", Outcome.LOSS, -50.0, score=0.5),  # low composite
        ]
        ranking = self._run(events)
        scores = [c.composite_score for c in ranking.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_composite_score_formula(self):
        # composite = avg_score * win_rate for known outcomes
        events = [
            _trade("AAPL", "LC", Outcome.WIN, 100.0, score=0.8),
            _trade("AAPL", "LC", Outcome.WIN, 80.0, score=0.8),
        ]
        ranking = self._run(events)
        cand = next(c for c in ranking.candidates if c.symbol == "AAPL")
        assert cand.win_rate == pytest.approx(1.0)
        assert cand.avg_score == pytest.approx(0.8)
        assert cand.composite_score == pytest.approx(0.8)

    def test_candidate_without_outcomes_uses_0_5_win_rate_factor(self):
        events = [_rec("MSFT", "CC", score=0.7)]
        ranking = self._run(events)
        cand = next((c for c in ranking.candidates if c.symbol == "MSFT"), None)
        assert cand is not None
        assert cand.win_rate is None
        assert cand.composite_score == pytest.approx(0.7 * 0.5)

    def test_empty_events_returns_empty_ranking(self):
        ranking = self._run([])
        assert ranking.candidates == []


class TestAdapterAuditSummaryFallback:
    """decision_audit_summary.json is used only when audit_trail.jsonl is missing."""

    def test_audit_summary_used_when_jsonl_missing(self, tmp_path):
        """Adapter falls back to audit summary when JSONL is absent."""
        reports_dir = tmp_path / "data" / "reports"
        reports_dir.mkdir(parents=True)
        import json

        summary = {
            "advisory_only": True,
            "total_entries": 1,
            "entries": [
                {
                    "signal_id": "s-001",
                    "strategy_id": "LONG_CALL",
                    "final_decision": "ACCEPTED",
                    "regime": "BULL",
                    "score": 0.8,
                    "risk_reward_result": {"is_valid": True, "risk_reward_ratio": 2.0},
                }
            ],
        }
        (reports_dir / "decision_audit_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        # No decision_audit_trail.jsonl — adapter must use summary
        from adapters.nova_options_adapter import NovaBotV2OptionsAdapter
        adapter = NovaBotV2OptionsAdapter(source_dir=tmp_path)
        events = adapter.load()
        assert len(events) == 1
        assert any("audit_summary" in k for k in adapter.diagnostics.source_breakdown)

    def test_audit_summary_skipped_when_jsonl_present(self):
        """If JSONL is present, audit summary is loaded but not parsed into events."""
        from adapters.nova_options_adapter import NovaBotV2OptionsAdapter
        from pathlib import Path

        fixture = Path(__file__).parent / "fixtures" / "nova_options"
        adapter = NovaBotV2OptionsAdapter(source_dir=fixture)
        adapter.load()
        # audit_trail.jsonl is in the fixture → summary should NOT contribute events
        assert "audit_summary" not in adapter.diagnostics.source_breakdown


class TestLifecycleSummaryLoaded:
    def test_lifecycle_summary_loaded_from_real_dir(self, tmp_path):
        import json
        from adapters.nova_options_adapter import NovaBotV2OptionsAdapter

        reports = tmp_path / "data" / "reports"
        reports.mkdir(parents=True)
        (tmp_path / "data" / "logs").mkdir(parents=True)
        lc = {"advisory_only": True, "total_signals": 5, "by_status": {"RECOMMENDED": 3, "PAPER_EXIT": 2}}
        (reports / "signal_lifecycle_summary.json").write_text(json.dumps(lc), encoding="utf-8")

        adapter = NovaBotV2OptionsAdapter(source_dir=tmp_path)
        adapter.load()
        assert adapter.lifecycle_summary.get("total_signals") == 5
        assert any("signal_lifecycle_summary.json" in f for f in adapter.diagnostics.files_found)


class TestDiagnosticsReport:
    def test_diagnostics_md_generated_separately(self, tmp_path):
        from adapters.nova_options_adapter import NovaBotV2OptionsAdapter
        from core.tactic_analytics_engine import TacticAnalyticsEngine
        from utils.tactic_report_generator import TacticReportGenerator
        from pathlib import Path

        fixture = Path(__file__).parent / "fixtures" / "nova_options"
        adapter = NovaBotV2OptionsAdapter(source_dir=fixture)
        events = adapter.load()
        result = TacticAnalyticsEngine().run(events)

        diag_path = tmp_path / "adapter_diagnostics.md"
        gen = TacticReportGenerator()
        gen.generate(
            result,
            output_path=tmp_path / "report.md",
            diagnostics=adapter.diagnostics,
            diagnostics_path=diag_path,
        )

        assert diag_path.exists()
        content = diag_path.read_text()
        assert "Files Discovered" in content
        assert "Records Parsed" in content
        assert "Parse Failures" in content

    def test_diagnostics_md_not_generated_without_diagnostics(self, tmp_path):
        from core.tactic_analytics_engine import TacticAnalyticsEngine
        from utils.tactic_report_generator import TacticReportGenerator

        result = TacticAnalyticsEngine().run([])
        diag_path = tmp_path / "adapter_diagnostics.md"
        gen = TacticReportGenerator()
        gen.generate(result, output_path=tmp_path / "report.md", diagnostics_path=diag_path)
        assert not diag_path.exists()
