"""Runner wiring tests for NovaBotV2 closed stock trade outcomes.

Hermetic: fixtures are written under tmp_path. No NovaBotV2 runtime, broker,
order, scheduler, or live-cycle modules are imported or executed.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from core.tactic_event import EventType, SourceBot
from tools import run_tacticbot
from utils.source_provenance import derive_run_provenance


def _args(**overrides):
    base = {
        "nova_options_dir": None,
        "nova_botv2_dir": None,
        "source_dir": None,
        "report_dir": "unused",
        "report_name": "unused.md",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _sell_event(
    *,
    execution_mode: str = "LIVE_RECONCILED",
    trade_id: str = "TRD-1",
    exec_ids: str = "E1",
    netto_pnl: float = 4.25,
) -> dict:
    return {
        "event_type": "SELL_EXECUTED",
        "timestamp": "2026-06-11 01:18:44",
        "data": {
            "execution_mode": execution_mode,
            "strategy": "BREAKOUT",
            "setup_type": "TREND",
            "netto_pnl": netto_pnl,
            "ticker": "LUNR",
            "trade_id": trade_id,
            "exec_ids": exec_ids,
            "broker_source": "IBKR",
            "timestamp": "2026-06-11 01:18:44",
        },
    }


def _write_trade_events(nova_botv2_root: Path, records: list[dict]) -> Path:
    events_path = nova_botv2_root / "data" / "results" / "trade_events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return events_path


def test_runner_loads_nova_botv2_trade_adapter_when_flag_is_provided(tmp_path):
    nova_botv2_root = tmp_path / "NovaBotV2"
    _write_trade_events(nova_botv2_root, [_sell_event(), _sell_event(netto_pnl=8.5)])

    events, errors, diagnostics, supplementary = run_tacticbot.load_tactic_events(
        _args(nova_botv2_dir=nova_botv2_root)
    )

    assert errors == []
    assert diagnostics is None
    assert supplementary is None
    assert len(events) == 1
    event = events[0]
    assert event.source_bot == SourceBot.NOVA_BOT_V2
    assert event.event_type == EventType.TRADE_OUTCOME
    assert event.realized_pnl == 8.5
    assert event.metadata["data_is_real"] is True


def test_run_level_provenance_true_only_from_real_stock_outcomes(tmp_path):
    nova_botv2_root = tmp_path / "NovaBotV2"
    _write_trade_events(nova_botv2_root, [_sell_event(execution_mode="LIVE_RECONCILED")])
    events, _errors, _diagnostics, _supplementary = run_tacticbot.load_tactic_events(
        _args(nova_botv2_dir=nova_botv2_root)
    )

    result = derive_run_provenance(
        None,
        None,
        nova_botv2_dir=nova_botv2_root,
        events=events,
    )

    assert result.data_is_real is True


def test_paper_stock_outcomes_keep_run_level_provenance_false(tmp_path):
    nova_botv2_root = tmp_path / "NovaBotV2"
    _write_trade_events(nova_botv2_root, [_sell_event(execution_mode="DRY_RUN")])
    events, _errors, _diagnostics, _supplementary = run_tacticbot.load_tactic_events(
        _args(nova_botv2_dir=nova_botv2_root)
    )

    result = derive_run_provenance(
        None,
        None,
        nova_botv2_dir=nova_botv2_root,
        events=events,
    )

    assert events[0].metadata["data_is_real"] is False
    assert result.data_is_real is False


def test_runner_wiring_does_not_import_live_broker_order_or_scheduler_modules():
    runner_source = Path(run_tacticbot.__file__).read_text(encoding="utf-8")
    adapter_source = (Path(run_tacticbot.__file__).parents[1] / "adapters" / "nova_botv2_trade_adapter.py").read_text(
        encoding="utf-8"
    )
    forbidden_roots = {
        "ibapi",
        "ib_insync",
        "workflow.nova_scheduler",
        "utils.ib",
        "utils.ib_orders",
        "core.nova_koopbot",
        "core.nova_verkoopbot",
    }
    violations: list[str] = []
    for label, source in {"runner": runner_source, "adapter": adapter_source}.items():
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_roots:
                        violations.append(f"{label}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module in forbidden_roots:
                violations.append(f"{label}: from {node.module} import ...")

    assert violations == []
