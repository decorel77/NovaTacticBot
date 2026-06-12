"""POST-005 tests: data_is_real derives from trusted provenance, never from
the mere presence of a CLI source directory.

Queue-required cases:
  - dummy dir            => data_is_real false
  - generic source       => data_is_real false
  - real trusted Options => true only when inputs exist, real-flagged, fresh
  - stale trusted source => false (degraded)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.source_provenance import (
    DEFAULT_MAX_SOURCE_AGE_HOURS,
    GENERIC_SOURCE,
    MIXED_SOURCE,
    MIXED_STOCK_GENERIC_SOURCE,
    MIXED_STOCK_OPTIONS_SOURCE,
    NO_SOURCE,
    TRUSTED_SOURCE_NOVA_BOTV2,
    TRUSTED_SOURCE_NOVA_OPTIONS,
    assess_nova_botv2_stock_outcomes,
    assess_nova_options_source,
    derive_run_provenance,
)
from core.tactic_event import EventType, SourceBot, TacticalEvent

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _build_trusted_dir(
    root: Path,
    *,
    snapshot: dict | None = None,
    with_audit_trail: bool = True,
    with_snapshot: bool = True,
) -> Path:
    if with_audit_trail:
        audit = root / "data" / "logs" / "decision_audit_trail.jsonl"
        audit.parent.mkdir(parents=True, exist_ok=True)
        audit.write_text('{"event": "DECISION"}\n', encoding="utf-8")
    if with_snapshot:
        snap_path = root / "data" / "system" / "result_snapshot.json"
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot if snapshot is not None else _real_flagged_snapshot()
        snap_path.write_text(json.dumps(payload), encoding="utf-8")
    return root


def _real_flagged_snapshot(age_hours: float = 1.0, **overrides) -> dict:
    snap = {
        "project": "NovaBotV2Options",
        "broker_execution_enabled": False,
        "portfolio_fidelity_source": "REPAIR-006 persisted advisory ledger",
        "open_paper_positions": 3,
        "updated_at_utc": (NOW - timedelta(hours=age_hours)).isoformat(),
    }
    snap.update(overrides)
    return snap


def _stock_root(root: Path) -> Path:
    events = root / "data" / "results" / "trade_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text('{"event_type": "SELL_EXECUTED"}\n', encoding="utf-8")
    return root


def _stock_event(*, data_is_real: bool = True) -> TacticalEvent:
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id="BREAKOUT",
        metadata={"data_is_real": data_is_real},
    )


class TestDummyAndGenericSources:
    def test_dummy_dir_is_not_real(self, tmp_path):
        # A bare directory with random files: no adapter inputs, no snapshot.
        (tmp_path / "x.json").write_text('{"strategy": "x"}', encoding="utf-8")
        result = assess_nova_options_source(tmp_path, now=NOW)
        assert result.data_is_real is False
        assert any("missing" in r for r in result.reasons)

    def test_generic_source_dir_is_never_real(self, tmp_path):
        result = derive_run_provenance(None, tmp_path, now=NOW)
        assert result.data_is_real is False
        assert result.input_source == GENERIC_SOURCE

    def test_no_source_is_not_real(self):
        result = derive_run_provenance(None, None, now=NOW)
        assert result.data_is_real is False
        assert result.input_source == NO_SOURCE

    def test_nonexistent_trusted_dir_is_not_real(self, tmp_path):
        result = derive_run_provenance(tmp_path / "does_not_exist", None, now=NOW)
        assert result.data_is_real is False


class TestTrustedOptionsSource:
    def test_verified_fresh_real_flagged_options_source_is_diagnostic_only(self, tmp_path):
        _build_trusted_dir(tmp_path)
        result = derive_run_provenance(tmp_path, None, now=NOW)
        assert result.data_is_real is False
        assert result.input_source == TRUSTED_SOURCE_NOVA_OPTIONS
        assert any("paper/advisory" in r for r in result.reasons)

    def test_canonical_data_is_real_flag_also_accepted(self, tmp_path):
        snap = _real_flagged_snapshot()
        del snap["portfolio_fidelity_source"]
        snap["data_is_real"] = True
        _build_trusted_dir(tmp_path, snapshot=snap)
        assert assess_nova_options_source(tmp_path, now=NOW).data_is_real is True

    def test_missing_audit_trail_is_not_real(self, tmp_path):
        _build_trusted_dir(tmp_path, with_audit_trail=False)
        result = assess_nova_options_source(tmp_path, now=NOW)
        assert result.data_is_real is False
        assert any("decision_audit_trail" in r for r in result.reasons)

    def test_missing_source_snapshot_is_not_real(self, tmp_path):
        _build_trusted_dir(tmp_path, with_snapshot=False)
        assert assess_nova_options_source(tmp_path, now=NOW).data_is_real is False

    def test_dry_zero_snapshot_without_real_flags_is_not_real(self, tmp_path):
        # The plain dry-run autocycle overwrite: safe flags but no realness marker.
        snap = _real_flagged_snapshot()
        del snap["portfolio_fidelity_source"]
        _build_trusted_dir(tmp_path, snapshot=snap)
        result = assess_nova_options_source(tmp_path, now=NOW)
        assert result.data_is_real is False
        assert any("real-data flags" in r for r in result.reasons)

    def test_stale_trusted_source_is_degraded_to_false(self, tmp_path):
        _build_trusted_dir(
            tmp_path,
            snapshot=_real_flagged_snapshot(age_hours=DEFAULT_MAX_SOURCE_AGE_HOURS + 10),
        )
        result = assess_nova_options_source(tmp_path, now=NOW)
        assert result.data_is_real is False
        assert any("stale" in r for r in result.reasons)

    def test_broker_flag_not_declared_false_is_not_real(self, tmp_path):
        snap = _real_flagged_snapshot()
        del snap["broker_execution_enabled"]
        _build_trusted_dir(tmp_path, snapshot=snap)
        assert assess_nova_options_source(tmp_path, now=NOW).data_is_real is False

    def test_corrupt_source_snapshot_fails_closed(self, tmp_path):
        _build_trusted_dir(tmp_path)
        (tmp_path / "data" / "system" / "result_snapshot.json").write_text(
            "{not json", encoding="utf-8"
        )
        assert assess_nova_options_source(tmp_path, now=NOW).data_is_real is False

    def test_missing_freshness_timestamp_is_not_real(self, tmp_path):
        snap = _real_flagged_snapshot()
        del snap["updated_at_utc"]
        _build_trusted_dir(tmp_path, snapshot=snap)
        assert assess_nova_options_source(tmp_path, now=NOW).data_is_real is False


class TestMixedSources:
    def test_generic_dir_mixed_into_trusted_run_taints_to_false(self, tmp_path):
        trusted = _build_trusted_dir(tmp_path / "options")
        generic = tmp_path / "generic"
        generic.mkdir()
        result = derive_run_provenance(trusted, generic, now=NOW)
        assert result.data_is_real is False
        assert result.input_source == MIXED_SOURCE


class TestNovaBotV2StockOutcomeSource:
    def test_real_stock_outcome_makes_run_real(self, tmp_path):
        stock = _stock_root(tmp_path / "NovaBotV2")
        result = derive_run_provenance(None, None, nova_botv2_dir=stock, events=[_stock_event()])
        assert result.data_is_real is True
        assert result.input_source == TRUSTED_SOURCE_NOVA_BOTV2

    def test_paper_or_unloaded_stock_outcomes_fail_closed(self, tmp_path):
        stock = _stock_root(tmp_path / "NovaBotV2")
        paper = derive_run_provenance(
            None, None, nova_botv2_dir=stock, events=[_stock_event(data_is_real=False)]
        )
        unloaded = derive_run_provenance(None, None, nova_botv2_dir=stock, events=[])
        assert paper.data_is_real is False
        assert unloaded.data_is_real is False

    def test_stock_plus_options_uses_stock_realness_only(self, tmp_path):
        options = _build_trusted_dir(tmp_path / "options")
        stock = _stock_root(tmp_path / "NovaBotV2")
        result = derive_run_provenance(
            options, None, nova_botv2_dir=stock, events=[_stock_event()], now=NOW
        )
        assert result.data_is_real is True
        assert result.input_source == MIXED_STOCK_OPTIONS_SOURCE
        assert any("paper/advisory" in r for r in result.reasons)

    def test_generic_source_taints_real_stock_outcomes_to_false(self, tmp_path):
        stock = _stock_root(tmp_path / "NovaBotV2")
        generic = tmp_path / "generic"
        generic.mkdir()
        result = derive_run_provenance(
            None, generic, nova_botv2_dir=stock, events=[_stock_event()]
        )
        assert result.data_is_real is False
        assert result.input_source == MIXED_STOCK_GENERIC_SOURCE

    def test_stock_source_requires_expected_readonly_input_file(self, tmp_path):
        stock = tmp_path / "NovaBotV2"
        stock.mkdir()
        result = assess_nova_botv2_stock_outcomes(stock, events=[_stock_event()])
        assert result.data_is_real is False
        assert any("trade_events.jsonl" in r for r in result.reasons)
