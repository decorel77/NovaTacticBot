"""Tests for the TacticAnalyticsEngine."""

import pytest

from core.tactic_analytics_engine import TacticAnalyticsEngine
from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent


def make_trade(strategy_id="strat_a", outcome=Outcome.WIN, pnl=100.0, regime=Regime.NORMAL, score=None):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id=strategy_id,
        outcome=outcome,
        realized_pnl=pnl,
        regime=regime,
        score=score,
    )


def make_rejection(strategy_id="strat_a", regime=Regime.NORMAL):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.REJECTION,
        strategy_id=strategy_id,
        regime=regime,
    )


class TestEmptyInput:
    def test_empty_events_returns_result(self):
        engine = TacticAnalyticsEngine()
        result = engine.run([])
        assert result.strategy_stats == {}
        assert result.regime_stats == {}
        assert len(result.open_questions) > 0


class TestStrategyAnalysis:
    def test_win_rate_calculation(self):
        events = [
            make_trade(outcome=Outcome.WIN),
            make_trade(outcome=Outcome.WIN),
            make_trade(outcome=Outcome.LOSS),
        ]
        result = TacticAnalyticsEngine().run(events)
        s = result.strategy_stats["strat_a"]
        assert s.wins == 2
        assert s.losses == 1
        assert s.win_rate == pytest.approx(2 / 3)

    def test_multiple_strategies(self):
        events = [
            make_trade("iron_condor", Outcome.WIN),
            make_trade("covered_call", Outcome.LOSS),
            make_trade("covered_call", Outcome.WIN),
        ]
        result = TacticAnalyticsEngine().run(events)
        assert "iron_condor" in result.strategy_stats
        assert "covered_call" in result.strategy_stats

    def test_avg_pnl(self):
        events = [
            make_trade(pnl=100.0),
            make_trade(pnl=200.0),
        ]
        result = TacticAnalyticsEngine().run(events)
        s = result.strategy_stats["strat_a"]
        assert s.avg_realized_pnl == pytest.approx(150.0)

    def test_avg_score(self):
        events = [
            make_trade(score=0.8),
            make_trade(score=0.6),
        ]
        result = TacticAnalyticsEngine().run(events)
        s = result.strategy_stats["strat_a"]
        assert s.avg_score == pytest.approx(0.7)


class TestRegimeAnalysis:
    def test_regime_bucketing(self):
        events = [
            make_trade(regime=Regime.BULL, outcome=Outcome.WIN),
            make_trade(regime=Regime.BULL, outcome=Outcome.WIN),
            make_trade(regime=Regime.BEAR, outcome=Outcome.LOSS),
        ]
        result = TacticAnalyticsEngine().run(events)
        assert result.regime_stats[Regime.BULL].wins == 2
        assert result.regime_stats[Regime.BEAR].losses == 1

    def test_missing_regime_bucketed_as_unknown(self):
        events = [make_trade(regime=None)]
        result = TacticAnalyticsEngine().run(events)
        assert "UNKNOWN" in result.regime_stats


class TestRejectionAnalysis:
    def test_rejection_rate(self):
        events = [
            make_trade(outcome=Outcome.WIN),
            make_rejection(),
            make_rejection(),
        ]
        result = TacticAnalyticsEngine().run(events)
        rs = result.rejection_stats
        assert rs.total_rejections == 2
        assert rs.rejection_rate == pytest.approx(2 / 3)

    def test_rejection_by_strategy(self):
        events = [
            make_rejection("strat_a"),
            make_rejection("strat_a"),
            make_rejection("strat_b"),
        ]
        result = TacticAnalyticsEngine().run(events)
        assert result.rejection_stats.by_strategy["strat_a"] == 2
        assert result.rejection_stats.by_strategy["strat_b"] == 1


class TestRecommendationQuality:
    def test_high_vs_low_score_win_rate(self):
        events = [
            make_trade(score=0.9, outcome=Outcome.WIN),
            make_trade(score=0.8, outcome=Outcome.WIN),
            make_trade(score=0.3, outcome=Outcome.LOSS),
            make_trade(score=0.2, outcome=Outcome.LOSS),
        ]
        result = TacticAnalyticsEngine().run(events)
        rq = result.recommendation_quality
        assert rq.high_score_win_rate == pytest.approx(1.0)
        assert rq.low_score_win_rate == pytest.approx(0.0)


class TestDataQuality:
    def test_counts_missing_fields(self):
        events = [
            make_trade(regime=None, score=None),
            make_trade(regime=Regime.BULL),
        ]
        result = TacticAnalyticsEngine().run(events)
        dq = result.data_quality
        assert dq.total_events == 2
        assert dq.missing_regime == 1
        assert dq.missing_score >= 1

    def test_source_bot_counts(self):
        events = [make_trade(), make_trade()]
        result = TacticAnalyticsEngine().run(events)
        assert result.data_quality.source_bot_counts[SourceBot.NOVA_BOT_V2_OPTIONS] == 2
