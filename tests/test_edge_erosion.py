"""Tests for strategy edge erosion detector (TACTIC-SA-005)."""
from core.tactic_event import EventType, Outcome, TacticalEvent
from core.tactic_analytics_engine import EDGE_EROSION_THRESHOLD_PP, TacticAnalyticsEngine


def _ev(strategy_id: str, outcome: str, ts: str) -> TacticalEvent:
    return TacticalEvent(
        event_id=f"{strategy_id}-{outcome}-{ts}",
        event_type=EventType.TRADE_OUTCOME,
        source_bot="test",
        strategy_id=strategy_id,
        outcome=outcome,
        timestamp=ts,
    )


def _ts(i: int) -> str:
    return f"2026-01-{i:02d}T00:00:00"


def test_no_events_no_warnings() -> None:
    result = TacticAnalyticsEngine().run([])
    assert result.edge_erosion.warnings == []


def test_no_erosion_when_recent_matches_baseline() -> None:
    # 10 wins straight — rolling and baseline both 100%
    events = [_ev("strat_a", Outcome.WIN, _ts(i)) for i in range(1, 11)]
    result = TacticAnalyticsEngine().run(events)
    assert result.edge_erosion.warnings == []
    assert "strat_a" in result.edge_erosion.healthy_strategies


def test_erosion_flagged_when_drop_exceeds_threshold() -> None:
    # 20 wins (strong baseline), then 10 losses (rolling window)
    events = (
        [_ev("s", Outcome.WIN, _ts(i)) for i in range(1, 21)]
        + [_ev("s", Outcome.LOSS, _ts(i)) for i in range(21, 31)]
    )
    result = TacticAnalyticsEngine().run(events)
    assert len(result.edge_erosion.warnings) == 1
    w = result.edge_erosion.warnings[0]
    assert w.strategy_id == "s"
    assert w.drop_pp >= EDGE_EROSION_THRESHOLD_PP
    assert w.baseline_win_rate > w.rolling_win_rate


def test_erosion_warning_in_observations() -> None:
    events = (
        [_ev("s", Outcome.WIN, _ts(i)) for i in range(1, 21)]
        + [_ev("s", Outcome.LOSS, _ts(i)) for i in range(21, 31)]
    )
    result = TacticAnalyticsEngine().run(events)
    assert any("EDGE_EROSION_WARNING" in obs for obs in result.observations)


def test_no_flag_when_drop_below_threshold() -> None:
    # baseline ~80%, recent ~75% — only 5pp drop, below threshold
    events = [
        _ev("s", Outcome.WIN, _ts(i)) for i in range(1, 9)   # 8 wins
    ] + [
        _ev("s", Outcome.LOSS, _ts(9)),                       # 1 loss
        _ev("s", Outcome.LOSS, _ts(10)),                      # 1 loss in rolling window
    ]
    result = TacticAnalyticsEngine().run(events)
    # baseline = 8/10 = 80%, rolling last-10 = same 10 events, 8/10 = 80%
    assert result.edge_erosion.warnings == []


def test_skip_strategy_with_too_few_rolling_trades() -> None:
    # Only 2 trades total — rolling window too small (< 3), should be skipped
    events = [_ev("s", Outcome.WIN, _ts(1)), _ev("s", Outcome.LOSS, _ts(2))]
    result = TacticAnalyticsEngine().run(events)
    assert result.edge_erosion.warnings == []


def test_multiple_strategies_independent_erosion() -> None:
    good_events = [_ev("good", Outcome.WIN, _ts(i)) for i in range(1, 11)]
    bad_events = (
        [_ev("bad", Outcome.WIN, _ts(i)) for i in range(1, 21)]
        + [_ev("bad", Outcome.LOSS, _ts(i)) for i in range(21, 31)]
    )
    result = TacticAnalyticsEngine().run(good_events + bad_events)
    flagged_ids = [w.strategy_id for w in result.edge_erosion.warnings]
    assert "bad" in flagged_ids
    assert "good" not in flagged_ids
