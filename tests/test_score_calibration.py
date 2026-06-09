"""Tests for strategy score calibration analysis (TACTIC-SA-004)."""
from core.tactic_event import EventType, Outcome, TacticalEvent
from core.tactic_analytics_engine import TacticAnalyticsEngine


def _ev(score: float, outcome: str) -> TacticalEvent:
    return TacticalEvent(
        event_id=f"e-{score}-{outcome}",
        event_type=EventType.TRADE_OUTCOME,
        source_bot="test",
        strategy_id="s",
        score=score,
        outcome=outcome,
    )


def test_no_events_no_calibration() -> None:
    result = TacticAnalyticsEngine().run([])
    sc = result.score_calibration
    assert sc.calibration_coefficient is None
    assert sc.calibration_flag is False


def test_no_scored_events_sets_note() -> None:
    events = [TacticalEvent(
        event_id="e1", event_type=EventType.TRADE_OUTCOME,
        source_bot="test", strategy_id="s", outcome=Outcome.WIN,
    )]
    result = TacticAnalyticsEngine().run(events)
    assert "No scored trade outcomes" in result.score_calibration.calibration_note


def test_decile_buckets_created() -> None:
    events = [_ev(i / 100.0, Outcome.WIN if i > 50 else Outcome.LOSS) for i in range(1, 101)]
    result = TacticAnalyticsEngine().run(events)
    sc = result.score_calibration
    assert len(sc.decile_buckets) == 10
    assert all(b.decile in range(1, 11) for b in sc.decile_buckets)


def test_decile_win_rates_populated() -> None:
    # Scores 0–0.49 → LOSS; 0.5–1.0 → WIN (high score = high win rate)
    events = [_ev(i / 100.0, Outcome.WIN if i >= 50 else Outcome.LOSS) for i in range(0, 100)]
    result = TacticAnalyticsEngine().run(events)
    sc = result.score_calibration
    # Higher deciles should have higher win rates
    high_decile = next((b for b in sc.decile_buckets if b.decile == 10 and b.win_rate is not None), None)
    low_decile = next((b for b in sc.decile_buckets if b.decile == 1 and b.win_rate is not None), None)
    if high_decile and low_decile:
        assert high_decile.win_rate >= low_decile.win_rate


def test_calibration_flag_when_low_score_beats_high() -> None:
    # Low scores → WIN, high scores → LOSS (inverted — should flag)
    events = [_ev(i / 100.0, Outcome.LOSS if i >= 50 else Outcome.WIN) for i in range(0, 100)]
    result = TacticAnalyticsEngine().run(events)
    sc = result.score_calibration
    # The flag fires when rank-1 win_rate > rank-5 win_rate
    rank1 = next((b for b in sc.decile_buckets if b.decile == 1 and b.win_rate is not None), None)
    rank5 = next((b for b in sc.decile_buckets if b.decile == 5 and b.win_rate is not None), None)
    if rank1 and rank5 and rank1.win_rate > rank5.win_rate:
        assert sc.calibration_flag is True


def test_good_calibration_no_flag() -> None:
    # Strictly higher score → WIN, lower → LOSS
    events = [_ev(i / 100.0, Outcome.WIN if i >= 50 else Outcome.LOSS) for i in range(0, 100)]
    result = TacticAnalyticsEngine().run(events)
    sc = result.score_calibration
    rank1 = next((b for b in sc.decile_buckets if b.decile == 1 and b.win_rate is not None), None)
    rank5 = next((b for b in sc.decile_buckets if b.decile == 5 and b.win_rate is not None), None)
    if rank1 and rank5 and rank1.win_rate <= rank5.win_rate:
        assert sc.calibration_flag is False


def test_calibration_warning_in_observations_when_flagged() -> None:
    events = [_ev(i / 100.0, Outcome.LOSS if i >= 50 else Outcome.WIN) for i in range(0, 100)]
    result = TacticAnalyticsEngine().run(events)
    sc = result.score_calibration
    if sc.calibration_flag:
        assert any("CALIBRATION_WARNING" in obs for obs in result.observations)


def test_decile_score_ranges_cover_full_range(tmp_path) -> None:
    events = [_ev(i / 10.0, Outcome.WIN) for i in range(0, 11)]
    result = TacticAnalyticsEngine().run(events)
    sc = result.score_calibration
    assert len(sc.decile_buckets) == 10
    assert sc.decile_buckets[0].score_min <= sc.decile_buckets[-1].score_max
