"""Tests for regime bias detector (TACTIC-RA-002)."""
from core.tactic_event import EventType, Outcome, TacticalEvent
from core.tactic_analytics_engine import REGIME_BIAS_MULTIPLIER, TacticAnalyticsEngine


_counter = 0


def _ev(event_type: str, regime: str, outcome: str | None = None) -> TacticalEvent:
    global _counter
    _counter += 1
    return TacticalEvent(
        event_id=f"ev-{_counter}",
        event_type=event_type,
        source_bot="test",
        strategy_id="s",
        regime=regime,
        outcome=outcome,
    )


def test_no_events_no_bias() -> None:
    result = TacticAnalyticsEngine().run([])
    assert result.regime_bias.warnings == []


def test_uniform_distribution_no_bias() -> None:
    # 4 events per regime, 4 trades per regime → equal rates
    events = []
    for regime in ["BULL", "BEAR", "NORMAL", "HIGH_VOL"]:
        for _ in range(4):
            events.append(_ev(EventType.TRADE_OUTCOME, regime, Outcome.WIN))
    result = TacticAnalyticsEngine().run(events)
    assert result.regime_bias.warnings == []


def _biased_events():
    """10 BULL events total (base 10%), but 10/20 trades in BULL (50%) → multiplier 5x."""
    evts = []
    # 10 BULL trade outcomes (base rate for BULL = 10/90 ≈ 11%, trade rate = 10/20 = 50%)
    for _ in range(10):
        evts.append(_ev(EventType.TRADE_OUTCOME, "BULL", Outcome.WIN))
    # 80 BEAR non-outcome events (recommendations) — inflates BEAR base rate
    for _ in range(80):
        evts.append(_ev(EventType.RECOMMENDATION, "BEAR"))
    # 10 BEAR trade outcomes
    for _ in range(10):
        evts.append(_ev(EventType.TRADE_OUTCOME, "BEAR", Outcome.WIN))
    return evts


def test_bias_flagged_when_regime_overtrades() -> None:
    result = TacticAnalyticsEngine().run(_biased_events())
    flagged_regimes = [w.regime for w in result.regime_bias.warnings]
    assert "BULL" in flagged_regimes


def test_bias_warning_multiplier_above_threshold() -> None:
    result = TacticAnalyticsEngine().run(_biased_events())
    flagged = {w.regime: w for w in result.regime_bias.warnings}
    assert flagged["BULL"].multiplier > REGIME_BIAS_MULTIPLIER


def test_bias_appears_in_observations() -> None:
    result = TacticAnalyticsEngine().run(_biased_events())
    assert any("REGIME_BIAS" in obs for obs in result.observations)


def test_base_rates_and_trade_rates_populated() -> None:
    events = [
        _ev(EventType.TRADE_OUTCOME, "BULL", Outcome.WIN),
        _ev(EventType.TRADE_OUTCOME, "BEAR", Outcome.LOSS),
        _ev(EventType.RECOMMENDATION, "BEAR"),
    ]
    result = TacticAnalyticsEngine().run(events)
    rb = result.regime_bias
    assert "BULL" in rb.regime_base_rates
    assert "BEAR" in rb.regime_base_rates
    assert abs(rb.regime_base_rates["BULL"] + rb.regime_base_rates["BEAR"] - 1.0) < 0.001


def test_no_trade_outcomes_no_bias() -> None:
    events = [_ev(EventType.RECOMMENDATION, "BULL") for _ in range(5)]
    result = TacticAnalyticsEngine().run(events)
    assert result.regime_bias.warnings == []
