"""QA-019 tests for the NovaTacticBot strategy correlation diagnostic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.strategy_correlation import (
    StrategyCorrelationConfig,
    compute_strategy_correlation,
    render_markdown_section,
)
from core.tactic_analytics_engine import AnalyticsResult, StrategyStats
from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent
from utils.tactic_snapshot_writer import snapshot_from_result

START = datetime(2026, 4, 1, 15, 30, 0, tzinfo=timezone.utc)


def _outcome(
    source_bot: str,
    day_offset: int,
    pnl: object,
    *,
    data_is_real: object = True,
    event_type: str = EventType.TRADE_OUTCOME,
    outcome: str = Outcome.WIN,
) -> TacticalEvent:
    return TacticalEvent(
        source_bot=source_bot,
        event_type=event_type,
        strategy_id="strat",
        timestamp=START + timedelta(days=day_offset),
        realized_pnl=pnl,
        outcome=outcome,
        metadata={"data_is_real": data_is_real},
    )


def _streams(days: int, pnl_b=lambda pnl_a: pnl_a * 2.0):
    events_a = []
    events_b = []
    for day in range(days):
        pnl_a = float((day % 7) - 3)  # deterministic, non-constant
        events_a.append(_outcome(SourceBot.NOVA_BOT_V2, day, pnl_a))
        events_b.append(_outcome(SourceBot.NOVA_BOT_V2_OPTIONS, day, pnl_b(pnl_a)))
    return events_a, events_b


def test_correlated_streams_with_enough_overlap_report_correlation() -> None:
    events_a, events_b = _streams(40)

    result = compute_strategy_correlation(events_a, events_b)

    assert result.computed is True
    assert result.insufficient_sample is False
    assert result.overlap_days == 40
    assert result.correlation is not None and abs(result.correlation - 1.0) < 1e-9
    assert result.refusal_reasons == ()
    assert "small_sample:40<60" in result.warnings
    assert result.broker_execution_enabled is False
    assert result.order_placement_enabled is False
    assert result.live_trading_enabled is False
    assert result.allocation_change_enabled is False
    assert result.downstream_export_enabled is False
    assert result.diagnostic_only is True


def test_inverse_streams_report_negative_correlation_with_interval() -> None:
    events_a, events_b = _streams(40, pnl_b=lambda pnl_a: -pnl_a + 0.25 * (pnl_a**2))

    result = compute_strategy_correlation(events_a, events_b)

    assert result.correlation is not None and result.correlation < -0.5
    assert result.ci_low is not None and result.ci_high is not None
    assert result.ci_low <= result.correlation <= result.ci_high


def test_insufficient_overlap_withholds_correlation() -> None:
    events_a, events_b = _streams(10)

    result = compute_strategy_correlation(events_a, events_b)

    assert result.computed is False
    assert result.insufficient_sample is True
    assert result.correlation is None
    assert result.ci_low is None and result.ci_high is None
    assert "insufficient_overlap:10<30" in result.refusal_reasons


def test_fake_or_unflagged_data_is_excluded_fail_closed() -> None:
    events_a, events_b = _streams(40)
    fake_a = [
        _outcome(SourceBot.NOVA_BOT_V2, day, 1.0, data_is_real=False)
        for day in range(40)
    ]

    result = compute_strategy_correlation(fake_a, events_b)

    assert result.computed is False
    assert result.insufficient_sample is True
    assert result.excluded_events.get("data_not_real") == 40
    assert result.events_used_a == 0
    assert result.events_used_b == 40


def test_pending_invalid_pnl_and_non_outcome_events_are_excluded() -> None:
    events_a, events_b = _streams(35)
    events_a.append(_outcome(SourceBot.NOVA_BOT_V2, 50, 1.0, outcome=Outcome.PENDING))
    events_a.append(_outcome(SourceBot.NOVA_BOT_V2, 51, None))
    events_a.append(_outcome(SourceBot.NOVA_BOT_V2, 52, "12.5"))
    events_a.append(
        _outcome(SourceBot.NOVA_BOT_V2, 53, 1.0, event_type=EventType.RECOMMENDATION)
    )

    result = compute_strategy_correlation(events_a, events_b)

    assert result.excluded_events.get("outcome_pending") == 1
    assert result.excluded_events.get("realized_pnl_missing_or_invalid") == 2
    assert result.excluded_events.get("not_trade_outcome") == 1
    assert result.events_used_a == 35
    assert result.overlap_days == 35


def test_constant_series_refuses_instead_of_fake_zero() -> None:
    days = 35
    events_a = [_outcome(SourceBot.NOVA_BOT_V2, day, 5.0) for day in range(days)]
    _, events_b = _streams(days)

    result = compute_strategy_correlation(events_a, events_b)

    assert result.computed is False
    assert result.correlation is None
    assert "correlation_undefined:constant_series" in result.refusal_reasons


def test_rolling_windows_are_deterministic_and_gated() -> None:
    events_a, events_b = _streams(40)

    first = compute_strategy_correlation(events_a, events_b)
    second = compute_strategy_correlation(events_a, events_b)

    assert first.to_dict() == second.to_dict()
    assert len(first.rolling) == 11  # 40 overlap days, window 30
    assert all(point.correlation is not None for point in first.rolling)
    assert first.rolling[-1].window_end == "2026-05-10"

    below_floor = compute_strategy_correlation(
        events_a,
        events_b,
        config=StrategyCorrelationConfig(rolling_window_days=10),
    )
    assert all(point.correlation is None for point in below_floor.rolling)
    assert all(point.insufficient_sample for point in below_floor.rolling)


def test_markdown_section_renders_caveats_and_insufficient_sample() -> None:
    events_a, events_b = _streams(40, pnl_b=lambda pnl_a: -pnl_a + 0.25 * (pnl_a**2))
    reported = render_markdown_section(compute_strategy_correlation(events_a, events_b))

    assert "diagnostic only" in reported
    assert "95% CI" in reported
    assert "not proof of diversification" in reported

    short_a, short_b = _streams(5)
    withheld = render_markdown_section(compute_strategy_correlation(short_a, short_b))

    assert "INSUFFICIENT SAMPLE" in withheld
    assert "insufficient_overlap:5<30" in withheld


def test_strategy_correlation_source_has_no_banned_module_imports() -> None:
    source = Path("core/strategy_correlation.py").read_text(encoding="utf-8")

    banned_tokens = ("import socket", "import subprocess", "os.system", "ibapi", "ib_insync")
    assert all(token not in source for token in banned_tokens)


def test_default_snapshot_behavior_unchanged_when_correlation_not_enabled() -> None:
    result = AnalyticsResult()
    stats = StrategyStats(strategy_id="covered_call")
    stats.trade_outcomes = 10
    stats.wins = 7
    stats.win_rate = 0.7
    result.strategy_stats["covered_call"] = stats
    result.data_quality.total_events = 10

    snapshot = snapshot_from_result(result)
    payload = snapshot.to_dict()["payload"]

    assert "strategy_correlation" not in payload
    assert payload["top_strategy"] == "covered_call"
