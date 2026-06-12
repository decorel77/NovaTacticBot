"""Tests for adapters/nova_botv2_trade_adapter.py (NEXT-008 / NEXT-009).

Fixture-based and hermetic: every test writes a synthetic trade_events.jsonl into
a tmp dir. No real NovaBotV2 data, no broker, no writes to any source repo.
"""
from __future__ import annotations

import json
from pathlib import Path

from adapters.nova_botv2_trade_adapter import NovaBotV2TradeAdapter
from core.tactic_event import EventType, Outcome, SourceBot


def _sell_event(
    *,
    execution_mode="LIVE_RECONCILED",
    strategy="BREAKOUT",
    setup_type="TREND",
    netto_pnl=3.75,
    pnl_abs=5.0,
    ticker="LUNR",
    trade_id="TRD-1",
    exec_ids="E1",
    timestamp="2026-06-11 01:18:44",
    sell_reason="BROKER_MANAGED_TAKE_PROFIT",
    **data_overrides,
):
    data = {
        "actie": "SELL",
        "execution_mode": execution_mode,
        "strategy": strategy,
        "setup_type": setup_type,
        "netto_pnl": netto_pnl,
        "pnl_abs": pnl_abs,
        "profit_abs": pnl_abs,
        "pnl_pct": 25.0,
        "ticker": ticker,
        "currency": "USD",
        "quantity": 2.0,
        "price": 12.5,
        "trade_id": trade_id,
        "exec_ids": exec_ids,
        "sell_reason": sell_reason,
        "reason": sell_reason,
        "cycle_id": "cyc-1",
        "session_id": "sess-1",
        "broker_source": "IBKR",
        "timestamp": timestamp,
    }
    data.update(data_overrides)
    return {
        "data": data,
        "event_type": "SELL_EXECUTED",
        "level": "INFO",
        "message": sell_reason,
        "source": "trade_logger",
        "timestamp": timestamp,
    }


def _write_jsonl(directory: Path, records) -> Path:
    path = directory / "trade_events.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return path


def _load(directory: Path, **kwargs):
    return NovaBotV2TradeAdapter(source_dir=directory, **kwargs).load()


def test_maps_sell_executed_to_trade_outcome(tmp_path):
    _write_jsonl(tmp_path, [_sell_event()])
    events = _load(tmp_path)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == EventType.TRADE_OUTCOME
    assert ev.source_bot == SourceBot.NOVA_BOT_V2
    assert ev.strategy_id == "BREAKOUT"
    assert ev.realized_pnl == 3.75  # netto_pnl preferred
    assert ev.outcome == Outcome.WIN
    assert ev.metadata["ticker"] == "LUNR"
    assert ev.metadata["sell_reason"] == "BROKER_MANAGED_TAKE_PROFIT"


def test_data_is_real_true_for_live_modes(tmp_path):
    _write_jsonl(
        tmp_path,
        [
            _sell_event(execution_mode="LIVE", trade_id="A", exec_ids="1"),
            _sell_event(execution_mode="LIVE_RECONCILED", trade_id="B", exec_ids="2"),
        ],
    )
    events = _load(tmp_path)
    assert all(ev.metadata["data_is_real"] is True for ev in events)


def test_data_is_real_fails_closed_for_simulated_or_unknown(tmp_path):
    _write_jsonl(
        tmp_path,
        [
            _sell_event(execution_mode="DRY_RUN", trade_id="A", exec_ids="1"),
            _sell_event(execution_mode="SIMULATED", trade_id="B", exec_ids="2"),
            _sell_event(execution_mode="", trade_id="C", exec_ids="3"),
            _sell_event(execution_mode="WEIRD_MODE", trade_id="D", exec_ids="4"),
        ],
    )
    events = _load(tmp_path)
    assert len(events) == 4
    assert all(ev.metadata["data_is_real"] is False for ev in events)


def test_outcome_derivation(tmp_path):
    _write_jsonl(
        tmp_path,
        [
            _sell_event(netto_pnl=5.0, pnl_abs=5.0, trade_id="W", exec_ids="1"),
            _sell_event(netto_pnl=-2.0, pnl_abs=-2.0, trade_id="L", exec_ids="2"),
            _sell_event(netto_pnl=0.0, pnl_abs=0.0, trade_id="B", exec_ids="3"),
            _sell_event(netto_pnl="", pnl_abs="", profit_abs="", realized_pnl=None,
                        trade_id="P", exec_ids="4"),
        ],
    )
    by_trade = {ev.metadata["trade_id"]: ev for ev in _load(tmp_path)}
    assert by_trade["W"].outcome == Outcome.WIN
    assert by_trade["L"].outcome == Outcome.LOSS
    assert by_trade["B"].outcome == Outcome.BREAKEVEN
    assert by_trade["P"].outcome == Outcome.PENDING
    assert by_trade["P"].realized_pnl is None


def test_non_outcome_events_are_ignored(tmp_path):
    noise = [
        {"event_type": "WAIT_MARKET_CLOSED", "data": {"ticker": "VLO"}, "timestamp": "2026-06-11 13:03:47"},
        {"event_type": "BUY_SKIPPED", "data": {"ticker": "AAPL"}, "timestamp": "2026-06-11 13:03:47"},
        {"event_type": "LOGBOOK_ARCHIVED", "data": {"ticker": "VLO"}, "timestamp": "2026-06-11 13:03:47"},
    ]
    _write_jsonl(tmp_path, noise + [_sell_event()])
    events = _load(tmp_path)
    assert len(events) == 1
    assert events[0].event_type == EventType.TRADE_OUTCOME


def test_deduplicates_same_broker_fill(tmp_path):
    # Same trade logged twice (reconciliation), second is the more-complete line.
    first = _sell_event(netto_pnl=3.75, trade_id="TRD-1", exec_ids="E1")
    second = _sell_event(netto_pnl=5.0, trade_id="TRD-1", exec_ids="E1",
                         timestamp="2026-06-11 01:18:45")
    _write_jsonl(tmp_path, [first, second])
    events = _load(tmp_path)
    assert len(events) == 1
    assert events[0].realized_pnl == 5.0  # last (most-reconciled) kept


def test_dedup_can_be_disabled(tmp_path):
    first = _sell_event(trade_id="TRD-1", exec_ids="E1")
    second = _sell_event(trade_id="TRD-1", exec_ids="E1", timestamp="2026-06-11 01:18:45")
    _write_jsonl(tmp_path, [first, second])
    events = _load(tmp_path, deduplicate=False)
    assert len(events) == 2


def test_events_without_identity_are_not_merged(tmp_path):
    # Missing exec_ids -> no stable identity -> never collapsed.
    a = _sell_event(trade_id="TRD-1", exec_ids="")
    b = _sell_event(trade_id="TRD-1", exec_ids="")
    _write_jsonl(tmp_path, [a, b])
    events = _load(tmp_path)
    assert len(events) == 2


def test_missing_file_returns_empty_with_error(tmp_path):
    adapter = NovaBotV2TradeAdapter(source_dir=tmp_path)
    events = adapter.load()
    assert events == []
    assert any("not found" in e for e in adapter.load_errors)


def test_unparseable_line_is_skipped_but_others_load(tmp_path):
    path = tmp_path / "trade_events.jsonl"
    path.write_text(
        "{not valid json\n" + json.dumps(_sell_event()) + "\n", encoding="utf-8"
    )
    adapter = NovaBotV2TradeAdapter(source_dir=tmp_path)
    events = adapter.load()
    assert len(events) == 1
    assert any("unparseable" in e for e in adapter.load_errors)


def test_adapter_is_read_only(tmp_path):
    path = _write_jsonl(tmp_path, [_sell_event()])
    before = path.read_bytes()
    NovaBotV2TradeAdapter(source_dir=tmp_path).load()
    assert path.read_bytes() == before  # adapter never writes to the source file
