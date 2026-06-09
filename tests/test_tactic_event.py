"""Tests for the TacticalEvent data contract."""

import pytest
from datetime import datetime

from core.tactic_event import (
    EventType,
    Outcome,
    Regime,
    SourceBot,
    TacticalEvent,
)


def make_event(**kwargs) -> TacticalEvent:
    defaults = dict(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id="covered_call",
    )
    defaults.update(kwargs)
    return TacticalEvent(**defaults)


class TestTacticalEventCreation:
    def test_minimal_valid_event(self):
        e = make_event()
        assert e.source_bot == SourceBot.NOVA_BOT_V2_OPTIONS
        assert e.event_type == EventType.TRADE_OUTCOME
        assert e.strategy_id == "covered_call"
        assert e.event_id is not None
        assert isinstance(e.timestamp, datetime)

    def test_full_event(self):
        e = make_event(
            regime=Regime.NORMAL,
            score=0.82,
            expected_rr=1.8,
            realized_pnl=55.20,
            outcome=Outcome.WIN,
        )
        assert e.regime == Regime.NORMAL
        assert e.score == 0.82
        assert e.outcome == Outcome.WIN

    def test_missing_source_bot_raises(self):
        with pytest.raises((ValueError, TypeError)):
            TacticalEvent(source_bot="", event_type=EventType.TRADE_OUTCOME, strategy_id="x")

    def test_missing_event_type_raises(self):
        with pytest.raises((ValueError, TypeError)):
            TacticalEvent(source_bot=SourceBot.NOVA_BOT_V2_OPTIONS, event_type="", strategy_id="x")

    def test_score_out_of_range_raises(self):
        with pytest.raises(ValueError):
            make_event(score=1.5)

    def test_score_negative_raises(self):
        with pytest.raises(ValueError):
            make_event(score=-0.1)

    def test_unique_event_ids(self):
        e1 = make_event()
        e2 = make_event()
        assert e1.event_id != e2.event_id


class TestTacticalEventHelpers:
    def test_is_trade_outcome(self):
        e = make_event(event_type=EventType.TRADE_OUTCOME)
        assert e.is_trade_outcome()

    def test_is_rejection(self):
        e = make_event(event_type=EventType.REJECTION)
        assert e.is_rejection()

    def test_is_win(self):
        e = make_event(outcome=Outcome.WIN)
        assert e.is_win()
        assert not e.is_loss()

    def test_is_loss(self):
        e = make_event(outcome=Outcome.LOSS)
        assert e.is_loss()
        assert not e.is_win()


class TestTacticalEventSerialization:
    def test_to_dict_roundtrip(self):
        e = make_event(score=0.75, outcome=Outcome.WIN, regime=Regime.BULL)
        d = e.to_dict()
        assert d["score"] == 0.75
        assert d["outcome"] == Outcome.WIN
        assert d["contract_version"] == "1.0"

    def test_from_dict_roundtrip(self):
        e = make_event(score=0.6, realized_pnl=100.0)
        d = e.to_dict()
        e2 = TacticalEvent.from_dict(d)
        assert e2.score == e.score
        assert e2.realized_pnl == e.realized_pnl
        assert e2.strategy_id == e.strategy_id

    def test_from_dict_missing_optional_fields(self):
        data = {
            "source_bot": SourceBot.NOVA_BOT_V2_OPTIONS,
            "event_type": EventType.TRADE_OUTCOME,
            "strategy_id": "naked_put",
        }
        e = TacticalEvent.from_dict(data)
        assert e.score is None
        assert e.regime is None
