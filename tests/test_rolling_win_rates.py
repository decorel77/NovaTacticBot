"""Tests for TACTIC-HA-003: rolling window win-rate tracker."""
import pytest
from datetime import datetime, timezone, timedelta

from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent
from core.tactic_analytics_engine import TacticAnalyticsEngine


def make_outcome(outcome: Outcome, strategy: str = "strat_a", offset_days: int = 0) -> TacticalEvent:
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id=strategy,
        outcome=outcome,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset_days),
    )


def make_rejection(strategy: str = "strat_a", offset_days: int = 0) -> TacticalEvent:
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.REJECTION,
        strategy_id=strategy,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset_days),
    )


class TestRollingWinRates:
    def _run(self, events):
        return TacticAnalyticsEngine().run(events)

    def test_empty_events_zero_trades(self):
        result = self._run([])
        assert result.rolling_win_rates.last_10.trades == 0
        assert result.rolling_win_rates.last_10.win_rate is None

    def test_five_wins_five_losses_last10(self):
        events = [make_outcome(Outcome.WIN, offset_days=i) for i in range(5)]
        events += [make_outcome(Outcome.LOSS, offset_days=i + 5) for i in range(5)]
        result = self._run(events)
        rw = result.rolling_win_rates.last_10
        assert rw.trades == 10
        assert rw.wins == 5
        assert rw.win_rate == pytest.approx(0.5)

    def test_last10_only_takes_most_recent(self):
        # 15 events: first 5 losses, last 10 wins
        events = [make_outcome(Outcome.LOSS, offset_days=i) for i in range(5)]
        events += [make_outcome(Outcome.WIN, offset_days=i + 5) for i in range(10)]
        result = self._run(events)
        rw = result.rolling_win_rates.last_10
        assert rw.trades == 10
        assert rw.wins == 10
        assert rw.win_rate == pytest.approx(1.0)

    def test_last30_window(self):
        events = [make_outcome(Outcome.WIN, offset_days=i) for i in range(20)]
        events += [make_outcome(Outcome.LOSS, offset_days=i + 20) for i in range(10)]
        result = self._run(events)
        rw = result.rolling_win_rates.last_30
        assert rw.trades == 30
        assert rw.wins == 20
        assert rw.win_rate == pytest.approx(20 / 30)

    def test_last100_fewer_than_100_events(self):
        events = [make_outcome(Outcome.WIN, offset_days=i) for i in range(15)]
        result = self._run(events)
        rw = result.rolling_win_rates.last_100
        assert rw.trades == 15
        assert rw.wins == 15
        assert rw.win_rate == pytest.approx(1.0)

    def test_rejections_excluded(self):
        events = [make_outcome(Outcome.WIN, offset_days=i) for i in range(5)]
        events += [make_rejection(offset_days=i + 10) for i in range(20)]
        result = self._run(events)
        assert result.rolling_win_rates.last_10.trades == 5

    def test_per_strategy_last10(self):
        events = [make_outcome(Outcome.WIN, "strat_a", offset_days=i) for i in range(6)]
        events += [make_outcome(Outcome.LOSS, "strat_a", offset_days=i + 6) for i in range(4)]
        events += [make_outcome(Outcome.WIN, "strat_b", offset_days=i) for i in range(3)]
        result = self._run(events)
        by_strat = result.rolling_win_rates.by_strategy_last_10
        assert "strat_a" in by_strat
        assert "strat_b" in by_strat
        assert by_strat["strat_a"].trades == 10
        assert by_strat["strat_b"].trades == 3
        assert by_strat["strat_b"].win_rate == pytest.approx(1.0)

    def test_rolling_win_rates_in_analytics_result(self):
        from core.tactic_analytics_engine import AnalyticsResult, RollingWinRates
        result = AnalyticsResult()
        assert isinstance(result.rolling_win_rates, RollingWinRates)
