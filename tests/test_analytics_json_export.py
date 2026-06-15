"""Tests for research/analytics_json_export.py (TACTIC-RP-002).

Deterministic, synthetic-only, broker-free. The exporter must serialize an
AnalyticsResult faithfully, stay ASCII-safe, propagate (never invent)
``data_is_real``, and remain unwired from the runner.
"""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.tactic_analytics_engine import (
    AnalyticsResult,
    StrategyStats,
    TacticAnalyticsEngine,
)
from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent
from research import analytics_json_export as exporter
from research.analytics_json_export import RESEARCH_ONLY, SCHEMA_VERSION, result_to_dict, to_json

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _outcome(strategy_id, regime, outcome, pnl, score=0.6, n=0):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id=strategy_id,
        timestamp=datetime(2026, 6, 1 + (n % 27), 12, 0, 0, tzinfo=timezone.utc),
        regime=regime,
        score=score,
        realized_pnl=pnl,
        outcome=outcome,
        metadata={"symbol": "AAPL"},
    )


def _populated_result() -> AnalyticsResult:
    events = [
        _outcome("covered_call", "BULL", Outcome.WIN, 1.0, n=0),
        _outcome("covered_call", "BULL", Outcome.LOSS, -1.0, n=1),
        _outcome("long_call", "BEAR", Outcome.WIN, 2.0, n=2),
    ]
    return TacticAnalyticsEngine().run(events)


class MetaBlockTests(unittest.TestCase):
    def test_meta_flags_and_schema(self):
        d = result_to_dict(AnalyticsResult())
        meta = d["meta"]
        self.assertEqual(SCHEMA_VERSION, meta["schema_version"])
        self.assertTrue(meta["research_only"])
        self.assertTrue(meta["diagnostic_only"])
        self.assertEqual("disabled", meta["broker_execution"])

    def test_data_is_real_defaults_false(self):
        d = result_to_dict(AnalyticsResult())
        self.assertFalse(d["meta"]["data_is_real"])

    def test_data_is_real_propagated_when_true(self):
        d = result_to_dict(AnalyticsResult(), data_is_real=True)
        self.assertTrue(d["meta"]["data_is_real"])

    def test_generated_at_only_present_when_supplied(self):
        self.assertNotIn("generated_at", result_to_dict(AnalyticsResult())["meta"])
        d = result_to_dict(AnalyticsResult(), generated_at=NOW.isoformat())
        self.assertEqual(NOW.isoformat(), d["meta"]["generated_at"])

    def test_non_result_raises(self):
        with self.assertRaises(TypeError):
            result_to_dict({"not": "a result"})  # type: ignore[arg-type]


class SerializationTests(unittest.TestCase):
    def test_empty_result_round_trips(self):
        s = to_json(AnalyticsResult())
        parsed = json.loads(s)
        self.assertEqual({}, parsed["analytics"]["strategy_stats"])
        self.assertEqual(0, parsed["analytics"]["data_quality"]["total_events"])

    def test_populated_result_serializes_key_fields(self):
        result = _populated_result()
        parsed = json.loads(to_json(result, data_is_real=False))
        analytics = parsed["analytics"]
        self.assertEqual(3, analytics["data_quality"]["total_events"])
        self.assertIn("covered_call", analytics["strategy_stats"])
        cc = analytics["strategy_stats"]["covered_call"]
        self.assertEqual(2, cc["trade_outcomes"])
        self.assertEqual(1, cc["wins"])
        self.assertAlmostEqual(0.5, cc["win_rate"])

    def test_score_vs_outcome_outcomes_are_json_safe_strings(self):
        # RecommendationQuality.score_vs_outcome embeds the outcome label; verify
        # it serializes as a plain string (the "enums" are plain strings).
        result = _populated_result()
        parsed = json.loads(to_json(result))
        rows = parsed["analytics"]["recommendation_quality"]["score_vs_outcome"]
        self.assertTrue(rows)
        for row in rows:
            self.assertIn(row["outcome"], {"WIN", "LOSS", "BREAKEVEN", None})

    def test_output_is_ascii_safe(self):
        # Confidence-bucket labels contain an en-dash; ensure_ascii must escape it.
        s = to_json(_populated_result())
        self.assertTrue(s.isascii())

    def test_determinism(self):
        result = _populated_result()
        self.assertEqual(to_json(result), to_json(result))


class FieldCoverageTests(unittest.TestCase):
    """Drift guard: the exporter must serialize every top-level AnalyticsResult
    field, so a future analytics field cannot silently drop out of the export
    (e.g. if asdict is ever replaced by a hand-written serializer)."""

    def test_every_analytics_result_field_is_exported(self):
        from dataclasses import fields

        expected = {f.name for f in fields(AnalyticsResult)}
        exported = set(result_to_dict(_populated_result())["analytics"].keys())
        missing = expected - exported
        self.assertEqual(set(), missing, f"export dropped fields: {sorted(missing)}")

    def test_export_adds_no_unexpected_top_level_keys(self):
        from dataclasses import fields

        expected = {f.name for f in fields(AnalyticsResult)}
        exported = set(result_to_dict(AnalyticsResult())["analytics"].keys())
        extra = exported - expected
        self.assertEqual(set(), extra, f"export added unexpected keys: {sorted(extra)}")


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(exporter.__file__).read_text(encoding="utf-8")
        forbidden = []
        for pkg in _BANNED_PACKAGES:
            forbidden.append(f"import {pkg}")
            forbidden.append(f"from {pkg}")
        forbidden += [
            "import socket",
            "import subprocess",
            "import requests",
            "import urllib",
            "import http.client",
            "place_order",
            "submit_order",
            "cancel_order",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_not_wired_into_runner(self):
        runner = Path(exporter.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("analytics_json_export", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
