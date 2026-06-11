"""QA-016 tests for the NovaTacticBot statistical floor."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.statistical_floor import (
    APPROVED_STRENGTH,
    DIAGNOSTIC_STRENGTH,
    TacticalSignalEvidence,
    evaluate_statistical_floor,
)
from core.tactic_analytics_engine import AnalyticsResult, StrategyStats
from core.tactic_event import EventType, SourceBot, TacticalEvent
from utils.tactic_snapshot_writer import snapshot_from_result

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _evidence(**overrides: object) -> TacticalSignalEvidence:
    data: dict[str, object] = {
        "signal_id": "sig-1",
        "strategy_id": "covered_call",
        "sample_size": 45,
        "confidence": 0.82,
        "win_rate": 0.62,
        "edge": 0.06,
        "produced_at": "2026-06-11T11:00:00+00:00",
        "fresh_until": "2026-06-11T13:00:00+00:00",
        "data_is_real": True,
        "regime": "BULL",
        "regime_verified": True,
        "exposure_increasing": True,
        "input_source": "fixture-realistic",
    }
    data.update(overrides)
    return TacticalSignalEvidence(**data)


def test_strong_signal_with_enough_evidence_passes_floor() -> None:
    result = evaluate_statistical_floor(_evidence(), now=NOW)

    assert result.approved is True
    assert result.strength == APPROVED_STRENGTH
    assert result.refusal_reasons == ()
    assert result.broker_execution_enabled is False
    assert result.order_placement_enabled is False
    assert result.downstream_export_enabled is False


def test_low_sample_size_fails_closed() -> None:
    result = evaluate_statistical_floor(_evidence(sample_size=12), now=NOW)

    assert result.approved is False
    assert result.strength == DIAGNOSTIC_STRENGTH
    assert "sample_size_below_floor:12<30" in result.refusal_reasons


def test_stale_data_fails_closed() -> None:
    result = evaluate_statistical_floor(
        _evidence(
            produced_at="2026-05-01T11:00:00+00:00",
            fresh_until="2026-05-02T11:00:00+00:00",
        ),
        now=NOW,
    )

    assert result.approved is False
    assert any(reason.startswith("evidence_stale:") for reason in result.refusal_reasons)


def test_missing_data_is_diagnostic_only() -> None:
    result = evaluate_statistical_floor(
        _evidence(sample_size=None, win_rate=None, edge=None, produced_at=None),
        now=NOW,
    )

    assert result.approved is False
    assert result.diagnostic_only is True
    assert "sample_size_invalid" in result.refusal_reasons
    assert "edge_or_win_rate_missing" in result.refusal_reasons
    assert "produced_at_missing_or_invalid" in result.refusal_reasons


def test_fake_or_unreal_data_fails_closed() -> None:
    result = evaluate_statistical_floor(_evidence(data_is_real=False), now=NOW)

    assert result.approved is False
    assert "data_not_real" in result.refusal_reasons


def test_invalid_confidence_winrate_and_edge_fail_closed() -> None:
    result = evaluate_statistical_floor(
        _evidence(confidence=1.2, win_rate="0.7", edge="wide"),
        now=NOW,
    )

    assert result.approved is False
    assert "confidence_invalid" in result.refusal_reasons
    assert "win_rate_invalid" in result.refusal_reasons
    assert "edge_invalid" in result.refusal_reasons


def test_unknown_or_unverified_regime_cannot_increase_strength() -> None:
    unknown = evaluate_statistical_floor(_evidence(regime="UNKNOWN"), now=NOW)
    unverified = evaluate_statistical_floor(
        _evidence(regime="BULL", regime_verified=False),
        now=NOW,
    )

    assert unknown.approved is False
    assert unverified.approved is False
    assert "regime_unknown_or_unsupported:UNKNOWN" in unknown.refusal_reasons
    assert "regime_not_verified" in unverified.refusal_reasons


def test_floor_can_build_evidence_from_event_without_side_effects() -> None:
    event = TacticalEvent(
        event_id="evt-1",
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.RECOMMENDATION,
        strategy_id="long_call",
        timestamp=NOW,
        regime="BULL",
        score=0.91,
        metadata={
            "sample_size": 35,
            "win_rate": 0.60,
            "edge": 0.04,
            "data_is_real": True,
            "regime_verified": True,
            "input_source": "unit-test",
        },
    )

    from core.statistical_floor import evidence_from_event

    result = evaluate_statistical_floor(evidence_from_event(event), now=NOW)

    assert result.approved is True
    assert result.metrics["input_source"] == "unit-test"


def test_statistical_floor_source_has_no_banned_module_imports() -> None:
    source = Path("core/statistical_floor.py").read_text(encoding="utf-8")

    banned_tokens = ("import socket", "import subprocess", "os.system", "ibapi", "ib_insync")
    assert all(token not in source for token in banned_tokens)


def test_default_snapshot_behavior_unchanged_when_floor_not_enabled() -> None:
    result = AnalyticsResult()
    stats = StrategyStats(strategy_id="covered_call")
    stats.trade_outcomes = 10
    stats.wins = 7
    stats.win_rate = 0.7
    result.strategy_stats["covered_call"] = stats
    result.data_quality.total_events = 10

    snapshot = snapshot_from_result(result)
    payload = snapshot.to_dict()["payload"]

    assert "statistical_floor" not in payload
    assert payload["top_strategy"] == "covered_call"
    assert payload["event_count"] == 10
