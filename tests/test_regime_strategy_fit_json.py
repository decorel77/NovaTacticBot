"""Tests for research/regime_strategy_fit_json.py (TACTIC-RA-003 export layer).

Deterministic, synthetic-only, broker-free. The serializer must be ASCII-safe,
reflect (never invent) provenance/status, serialize withheld cells as null, and
fail closed on error fits.
"""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent
from research import regime_strategy_fit_json as fitjson
from research.regime_strategy_fit import MIN_SAMPLE, RegimeStrategyFit, build_regime_strategy_fit
from research.regime_strategy_fit_json import SCHEMA_VERSION, fit_to_dict, to_json

FIXED_TIME = "2026-06-15T00:00:00+00:00"


def _outcome(strategy_id, regime, outcome, n=0):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id=strategy_id,
        timestamp=datetime(2026, 6, 1 + (n % 27), 12, 0, 0, tzinfo=timezone.utc),
        regime=regime,
        outcome=outcome,
    )


def _wins(strategy_id, regime, n):
    return [_outcome(strategy_id, regime, Outcome.WIN, i) for i in range(n)]


class MetaBlockTests(unittest.TestCase):
    def test_meta_flags_reflected(self):
        d = fit_to_dict(build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5)))
        meta = d["meta"]
        self.assertEqual(SCHEMA_VERSION, meta["schema_version"])
        self.assertTrue(meta["research_only"])
        self.assertTrue(meta["diagnostic_only"])
        self.assertEqual("disabled", meta["broker_execution"])
        self.assertEqual(MIN_SAMPLE, meta["min_sample"])
        self.assertEqual("INSUFFICIENT_SAMPLE", meta["status"])

    def test_data_is_real_reflected_not_invented(self):
        false_fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5))
        self.assertFalse(fit_to_dict(false_fit)["meta"]["data_is_real"])
        true_fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5), data_is_real=True)
        self.assertTrue(fit_to_dict(true_fit)["meta"]["data_is_real"])

    def test_generated_at_only_present_when_supplied(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5))
        self.assertNotIn("generated_at", fit_to_dict(fit)["meta"])
        self.assertEqual(FIXED_TIME, fit_to_dict(fit, generated_at=FIXED_TIME)["meta"]["generated_at"])

    def test_non_fit_raises(self):
        with self.assertRaises(TypeError):
            fit_to_dict({"not": "a fit"})  # type: ignore[arg-type]


class PayloadTests(unittest.TestCase):
    def test_withheld_cell_serializes_null(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5))
        parsed = json.loads(to_json(fit))
        key = RegimeStrategyFit.cell_key(Regime.BULL, "momentum")
        cell = parsed["fit"]["cells"][key]
        self.assertIsNone(cell["win_rate"])  # withheld -> null
        self.assertEqual("INSUFFICIENT_SAMPLE", cell["win_rate_status"])

    def test_at_floor_cell_serializes_rate(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, MIN_SAMPLE))
        parsed = json.loads(to_json(fit))
        key = RegimeStrategyFit.cell_key(Regime.BULL, "momentum")
        self.assertEqual(1.0, parsed["fit"]["cells"][key]["win_rate"])
        self.assertEqual("DIAGNOSTIC_ONLY", parsed["meta"]["status"])

    def test_error_fit_serializes_failed_closed(self):
        parsed = json.loads(to_json(build_regime_strategy_fit([])))
        self.assertEqual({}, parsed["fit"]["cells"])
        self.assertIn("no events provided", parsed["fit"]["errors"])
        self.assertEqual("INSUFFICIENT_SAMPLE", parsed["meta"]["status"])

    def test_output_is_ascii_safe(self):
        events = _wins("momentum", Regime.BULL, 30) + [_outcome("x", "WEIRD_REGIME", Outcome.WIN, 0)]
        self.assertTrue(to_json(build_regime_strategy_fit(events)).isascii())

    def test_determinism(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 30))
        self.assertEqual(to_json(fit), to_json(fit))


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(fitjson.__file__).read_text(encoding="utf-8")
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
        runner = Path(fitjson.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("regime_strategy_fit_json", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
