"""Tests for adapters/market_regime_adapter.py.

Verifies: export loading, event structure, regime mapping, score calculation,
allowlist enforcement, size guard, fallback to result_snapshot, and fail-closed.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from adapters.market_regime_adapter import (
    ALLOWED_SOURCE_DIRS,
    MAX_EXPORT_BYTES,
    MarketRegimeBotAdapter,
)
from core.tactic_event import EventType, SourceBot


NOW = datetime(2026, 6, 9, 13, 0, 0, tzinfo=timezone.utc)

BULL_EXPORT = {
    "schema_version": "regime_export.v1",
    "project": "MarketRegimeBot",
    "generated_at": "2026-06-09T12:00:00Z",
    "produced_at": "2026-06-09T12:00:00Z",
    "market_regime": "BULL",
    "confidence": 75,
    "risk_level": "NORMAL",
    "volatility_env": "LOW_VOL",
    "input_source": "yfinance",
    "data_is_real": True,
    "reason": ["Strong positive trend"],
    "dry_run": True,
    "read_only": True,
    "runtime_enabled": False,
}

HIGH_VOL_EXPORT = {
    **BULL_EXPORT,
    "market_regime": "HIGH_VOLATILITY",
    "confidence": 85,
    "risk_level": "HIGH",
    "volatility_env": "HIGH_VOL",
}

LEGACY_SNAPSHOT = {
    "project": "MarketRegimeBot",
    "status": "SAFE_DRY_RUN_REGIME",
    "market_regime": "BEAR",
    "confidence": 60,
    "risk_level": "HIGH",
    "volatility_env": "NORMAL",
    "input_source": "synthetic_fallback",
    "reason": ["Strong negative trend"],
    "dry_run": True,
}


def _allowed_dirs_for(path: Path) -> frozenset:
    return frozenset({path.resolve()})


def _write(directory: Path, filename: str, data: dict) -> None:
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")


class TestMarketRegimeBotAdapterLoadsEvent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        _write(self.tmpdir, "regime_export.json", BULL_EXPORT)
        self.adapter = MarketRegimeBotAdapter(
            self.tmpdir, allowed_dirs=_allowed_dirs_for(self.tmpdir), now=NOW
        )

    def test_loads_one_event(self):
        events = self.adapter.load()
        self.assertEqual(len(events), 1)

    def test_source_bot_is_market_regime_bot(self):
        events = self.adapter.load()
        self.assertEqual(events[0].source_bot, SourceBot.MARKET_REGIME_BOT)

    def test_event_type_is_regime_change(self):
        events = self.adapter.load()
        self.assertEqual(events[0].event_type, EventType.REGIME_CHANGE)

    def test_strategy_id_contains_regime(self):
        events = self.adapter.load()
        self.assertIn("bull", events[0].strategy_id)

    def test_score_from_confidence(self):
        events = self.adapter.load()
        self.assertAlmostEqual(events[0].score, 0.75)

    def test_regime_mapped_to_tactical_regime(self):
        events = self.adapter.load()
        self.assertEqual(events[0].regime, "BULL")

    def test_metadata_has_market_regime(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["market_regime"], "BULL")

    def test_metadata_has_volatility_env(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["volatility_env"], "LOW_VOL")

    def test_metadata_has_risk_level(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["risk_level"], "NORMAL")

    def test_metadata_has_input_source(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["input_source"], "yfinance")

    def test_metadata_has_generated_at(self):
        events = self.adapter.load()
        self.assertEqual(events[0].metadata["generated_at"], "2026-06-09T12:00:00Z")

    def test_metadata_read_only_true(self):
        events = self.adapter.load()
        self.assertTrue(events[0].metadata["read_only"])

    def test_metadata_always_includes_data_is_real(self):
        events = self.adapter.load()
        self.assertIn("data_is_real", events[0].metadata)
        self.assertTrue(events[0].metadata["data_is_real"])

    def test_real_fresh_payload_is_full_score(self):
        events = self.adapter.load()
        self.assertAlmostEqual(events[0].score, 0.75)
        self.assertFalse(events[0].metadata["unverified_regime"])
        self.assertEqual(events[0].metadata["regime_timestamp_status"], "fresh")

    def test_no_load_errors_on_valid_export(self):
        self.adapter.load()
        self.assertEqual(self.adapter.load_errors, [])


class TestRegimeRealnessFreshness(unittest.TestCase):
    def _event_for(self, payload: dict) -> object:
        tmpdir = Path(tempfile.mkdtemp())
        _write(tmpdir, "regime_export.json", payload)
        events = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        ).load()
        self.assertEqual(len(events), 1)
        return events[0]

    def test_real_stale_payload_emits_zero_score_unverified(self):
        event = self._event_for({
            **BULL_EXPORT,
            "produced_at": "2026-06-08T12:00:00Z",
            "generated_at": "2026-06-08T12:00:00Z",
        })
        self.assertEqual(event.score, 0.0)
        self.assertTrue(event.metadata["data_is_real"])
        self.assertTrue(event.metadata["unverified_regime"])
        self.assertEqual(event.metadata["regime_timestamp_status"], "stale")

    def test_fake_payload_emits_zero_score_unverified(self):
        event = self._event_for({**BULL_EXPORT, "data_is_real": False})
        self.assertEqual(event.score, 0.0)
        self.assertFalse(event.metadata["data_is_real"])
        self.assertTrue(event.metadata["unverified_regime"])
        self.assertEqual(event.metadata["regime_timestamp_status"], "fresh")

    def test_undated_payload_emits_zero_score_unverified(self):
        payload = dict(BULL_EXPORT)
        payload.pop("produced_at")
        payload.pop("generated_at")
        event = self._event_for(payload)
        self.assertEqual(event.score, 0.0)
        self.assertTrue(event.metadata["data_is_real"])
        self.assertTrue(event.metadata["unverified_regime"])
        self.assertEqual(event.metadata["regime_timestamp_status"], "missing")

    def test_unparseable_timestamp_emits_zero_score_unverified(self):
        event = self._event_for({
            **BULL_EXPORT,
            "produced_at": "not-a-timestamp",
        })
        self.assertEqual(event.score, 0.0)
        self.assertTrue(event.metadata["data_is_real"])
        self.assertTrue(event.metadata["unverified_regime"])
        self.assertEqual(event.metadata["regime_timestamp_status"], "unparseable")

    def test_generated_at_used_when_produced_at_absent(self):
        payload = dict(BULL_EXPORT)
        payload.pop("produced_at")
        event = self._event_for(payload)
        self.assertAlmostEqual(event.score, 0.75)
        self.assertFalse(event.metadata["unverified_regime"])
        self.assertEqual(event.metadata["regime_timestamp_status"], "fresh")


class TestRegimeMapping(unittest.TestCase):
    def _load(self, regime: str, risk="NORMAL", vol="NORMAL", conf=60) -> list:
        tmpdir = Path(tempfile.mkdtemp())
        export = {**BULL_EXPORT, "market_regime": regime,
                  "risk_level": risk, "volatility_env": vol, "confidence": conf}
        _write(tmpdir, "regime_export.json", export)
        return MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        ).load()

    def test_bull_maps_to_bull(self):
        events = self._load("BULL")
        self.assertEqual(events[0].regime, "BULL")

    def test_bear_maps_to_bear(self):
        events = self._load("BEAR", risk="HIGH")
        self.assertEqual(events[0].regime, "BEAR")

    def test_sideways_maps_to_normal(self):
        events = self._load("SIDEWAYS")
        self.assertEqual(events[0].regime, "NORMAL")

    def test_high_volatility_maps_to_high_vol(self):
        events = self._load("HIGH_VOLATILITY", risk="HIGH", vol="HIGH_VOL", conf=80)
        self.assertEqual(events[0].regime, "HIGH_VOL")

    def test_unknown_regime_maps_to_unknown(self):
        events = self._load("UNKNOWN", conf=0)
        self.assertEqual(events[0].regime, "UNKNOWN")


class TestLegacySnapshotFallback(unittest.TestCase):
    def test_falls_back_to_result_snapshot(self):
        tmpdir = Path(tempfile.mkdtemp())
        _write(tmpdir, "result_snapshot.json", LEGACY_SNAPSHOT)
        adapter = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        )
        events = adapter.load()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].metadata["market_regime"], "BEAR")

    def test_prefers_export_over_snapshot_when_both_exist(self):
        tmpdir = Path(tempfile.mkdtemp())
        _write(tmpdir, "regime_export.json", BULL_EXPORT)
        _write(tmpdir, "result_snapshot.json", LEGACY_SNAPSHOT)
        adapter = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        )
        events = adapter.load()
        self.assertEqual(events[0].metadata["market_regime"], "BULL")


class TestFailClosed(unittest.TestCase):
    def test_missing_files_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        adapter = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        )
        events = adapter.load()
        self.assertEqual(events, [])
        self.assertTrue(len(adapter.load_errors) > 0)

    def test_invalid_json_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "regime_export.json").write_text("not json }", encoding="utf-8")
        adapter = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        )
        events = adapter.load()
        self.assertEqual(events, [])

    def test_too_large_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "regime_export.json").write_bytes(b"x" * (MAX_EXPORT_BYTES + 1))
        adapter = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir)
        )
        events = adapter.load()
        self.assertEqual(events, [])

    def test_allowlist_reject_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        _write(tmpdir, "regime_export.json", BULL_EXPORT)
        adapter = MarketRegimeBotAdapter(tmpdir, allowed_dirs=frozenset())
        events = adapter.load()
        self.assertEqual(events, [])
        self.assertTrue(len(adapter.load_errors) > 0)

    def test_non_dict_json_returns_empty(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "regime_export.json").write_text(json.dumps([1, 2]), encoding="utf-8")
        adapter = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir)
        )
        events = adapter.load()
        self.assertEqual(events, [])


class TestNoBrokerImports(unittest.TestCase):
    def test_no_broker_imports(self):
        import ast
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "adapters" / "market_regime_adapter.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        broker_modules = {"ib_insync", "ibapi", "TWS"}
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertFalse(imports & broker_modules)

    def test_source_bot_is_market_regime_bot(self):
        self.assertEqual(MarketRegimeBotAdapter.SOURCE_BOT, SourceBot.MARKET_REGIME_BOT)


class TestNonFiniteConfidenceFailsClosed(unittest.TestCase):
    """A non-finite confidence (NaN/+-Infinity, parsed by json.loads from a regime
    export) must not crash the load; int(inf) raised OverflowError before."""

    def _event_for(self, confidence) -> object:
        tmpdir = Path(tempfile.mkdtemp())
        _write(tmpdir, "regime_export.json", {**BULL_EXPORT, "confidence": confidence})
        events = MarketRegimeBotAdapter(
            tmpdir, allowed_dirs=_allowed_dirs_for(tmpdir), now=NOW
        ).load()
        return events

    def test_infinity_confidence_does_not_crash(self):
        events = self._event_for(float("inf"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].score, 0.0)

    def test_nan_and_neg_infinity_confidence_fail_closed(self):
        for bad in (float("nan"), float("-inf")):
            events = self._event_for(bad)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].score, 0.0)

    def test_finite_confidence_unchanged(self):
        events = self._event_for(75)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].score, 0.75)


if __name__ == "__main__":
    unittest.main()
