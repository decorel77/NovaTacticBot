"""Tests for strategy streak detection (TACTIC-SA-003)."""
from core.tactic_event import EventType, Outcome, TacticalEvent
from core.tactic_analytics_engine import LOSS_STREAK_FLAG_THRESHOLD, TacticAnalyticsEngine


def _outcome_event(strategy_id: str, outcome: str, ts: str = "2026-01-01T00:00:00") -> TacticalEvent:
    return TacticalEvent(
        event_id=f"{strategy_id}-{outcome}-{ts}",
        event_type=EventType.TRADE_OUTCOME,
        source_bot="test",
        strategy_id=strategy_id,
        outcome=outcome,
        timestamp=ts,
    )


def test_no_events_produces_empty_streak_analysis() -> None:
    result = TacticAnalyticsEngine().run([])
    assert result.streak_analysis.by_strategy == {}
    assert result.streak_analysis.flagged_strategies == []


def test_all_wins_no_flag() -> None:
    events = [_outcome_event("strat_a", Outcome.WIN, f"2026-01-0{i}T00:00:00") for i in range(1, 6)]
    result = TacticAnalyticsEngine().run(events)
    stats = result.streak_analysis.by_strategy["strat_a"]
    assert stats.max_win_streak == 5
    assert stats.max_loss_streak == 0
    assert stats.flagged is False


def test_loss_streak_below_threshold_not_flagged() -> None:
    events = [
        _outcome_event("strat_a", Outcome.WIN, "2026-01-01T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-02T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-03T00:00:00"),
    ]
    result = TacticAnalyticsEngine().run(events)
    stats = result.streak_analysis.by_strategy["strat_a"]
    assert stats.current_loss_streak == 2
    assert stats.flagged is False


def test_loss_streak_at_threshold_flagged() -> None:
    events = [
        _outcome_event("strat_a", Outcome.WIN, "2026-01-01T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-02T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-03T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-04T00:00:00"),
    ]
    result = TacticAnalyticsEngine().run(events)
    stats = result.streak_analysis.by_strategy["strat_a"]
    assert stats.current_loss_streak == LOSS_STREAK_FLAG_THRESHOLD
    assert stats.flagged is True
    assert "strat_a" in result.streak_analysis.flagged_strategies


def test_streak_resets_after_win() -> None:
    events = [
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-01T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-02T00:00:00"),
        _outcome_event("strat_a", Outcome.LOSS, "2026-01-03T00:00:00"),
        _outcome_event("strat_a", Outcome.WIN, "2026-01-04T00:00:00"),
    ]
    result = TacticAnalyticsEngine().run(events)
    stats = result.streak_analysis.by_strategy["strat_a"]
    assert stats.current_loss_streak == 0
    assert stats.flagged is False
    assert stats.max_loss_streak == 3


def test_max_streaks_tracked_correctly() -> None:
    events = [
        _outcome_event("s", Outcome.WIN,  "2026-01-01T00:00:00"),
        _outcome_event("s", Outcome.WIN,  "2026-01-02T00:00:00"),
        _outcome_event("s", Outcome.LOSS, "2026-01-03T00:00:00"),
        _outcome_event("s", Outcome.LOSS, "2026-01-04T00:00:00"),
        _outcome_event("s", Outcome.LOSS, "2026-01-05T00:00:00"),
        _outcome_event("s", Outcome.WIN,  "2026-01-06T00:00:00"),
    ]
    result = TacticAnalyticsEngine().run(events)
    stats = result.streak_analysis.by_strategy["s"]
    assert stats.max_win_streak == 2
    assert stats.max_loss_streak == 3
    assert stats.current_streak == 1  # ends on a win


def test_multiple_strategies_independent() -> None:
    events = [
        _outcome_event("good", Outcome.WIN, "2026-01-01T00:00:00"),
        _outcome_event("good", Outcome.WIN, "2026-01-02T00:00:00"),
        _outcome_event("bad",  Outcome.LOSS, "2026-01-01T00:00:00"),
        _outcome_event("bad",  Outcome.LOSS, "2026-01-02T00:00:00"),
        _outcome_event("bad",  Outcome.LOSS, "2026-01-03T00:00:00"),
    ]
    result = TacticAnalyticsEngine().run(events)
    assert result.streak_analysis.by_strategy["good"].flagged is False
    assert result.streak_analysis.by_strategy["bad"].flagged is True
    assert result.streak_analysis.flagged_strategies == ["bad"]


def test_flagged_streak_appears_in_observations() -> None:
    events = [
        _outcome_event("s", Outcome.LOSS, f"2026-01-0{i}T00:00:00") for i in range(1, 5)
    ]
    result = TacticAnalyticsEngine().run(events)
    assert any("loss streak" in obs.lower() for obs in result.observations)
