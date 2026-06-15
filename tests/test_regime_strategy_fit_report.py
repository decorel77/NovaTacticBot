"""Tests for research/regime_strategy_fit_report.py (TACTIC-RA-003 report layer).

Deterministic, synthetic-only, broker-free. The renderer must stay ASCII-safe,
diagnostic-only, fail closed on error fits, withhold below-floor win rates, and
emit no order/live-action wording.
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent
from research import regime_strategy_fit_report as report
from research.regime_strategy_fit import MIN_SAMPLE, build_regime_strategy_fit
from research.regime_strategy_fit_report import DEFAULT_TITLE, build_markdown

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


class MetadataTests(unittest.TestCase):
    def setUp(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5))
        self.md = build_markdown(fit, generated_at=FIXED_TIME)

    def test_metadata_block(self):
        self.assertIn(f"# {DEFAULT_TITLE}", self.md)
        self.assertIn(f"- **generated_at:** {FIXED_TIME}", self.md)
        self.assertIn("- **research_only:** true", self.md)
        self.assertIn("- **diagnostic_only:** true", self.md)
        self.assertIn("- **data_is_real:** false", self.md)
        self.assertIn(f"- **min_sample_threshold:** {MIN_SAMPLE}", self.md)

    def test_disclaimer_present(self):
        self.assertIn("Not trading advice", self.md)

    def test_generated_at_optional(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5))
        self.assertNotIn("generated_at", build_markdown(fit))


class WithheldVsShownTests(unittest.TestCase):
    def test_below_floor_renders_insufficient(self):
        md = build_markdown(build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5)))
        self.assertIn("INSUFFICIENT_SAMPLE", md)
        self.assertIn("**INSUFFICIENT_SAMPLE.**", md)  # the overview banner

    def test_at_floor_renders_win_rate(self):
        md = build_markdown(build_regime_strategy_fit(_wins("momentum", Regime.BULL, MIN_SAMPLE)))
        self.assertIn("100.0%", md)
        self.assertIn("## Win-rate grid (regime x strategy)", md)

    def test_missing_pair_renders_dash_in_grid(self):
        # momentum only in BULL; mean_rev only in BEAR -> each has a missing pair.
        events = _wins("momentum", Regime.BULL, 2) + _wins("mean_rev", Regime.BEAR, 2)
        md = build_markdown(build_regime_strategy_fit(events))
        grid = md.split("## Win-rate grid")[1]
        self.assertIn("| - |", grid)  # at least one missing (regime, strategy) pair


class FailClosedTests(unittest.TestCase):
    def test_error_fit_renders_failed_closed_and_no_tables(self):
        md = build_markdown(build_regime_strategy_fit([]))
        self.assertIn("## Errors (failed closed)", md)
        self.assertIn("no events provided", md)
        self.assertNotIn("## Per-cell summary", md)
        self.assertNotIn("## Win-rate grid", md)


class SafetyWordingTests(unittest.TestCase):
    def test_no_action_wording(self):
        md = build_markdown(build_regime_strategy_fit(_wins("momentum", Regime.BULL, 30))).lower()
        for token in ["place order", "submit order", "cancel order", "market order",
                      "limit order", "go long", "go short", "execute trade", " buy ", " sell "]:
            with self.subTest(token=token):
                self.assertNotIn(token, md)

    def test_ascii_safe(self):
        events = _wins("momentum", Regime.BULL, 30) + _wins("mean_rev", Regime.BEAR, 5)
        md = build_markdown(build_regime_strategy_fit(events), generated_at=FIXED_TIME)
        self.assertTrue(md.isascii())

    def test_unknown_regime_note_rendered(self):
        events = [_outcome("momentum", "WEIRD_REGIME", Outcome.WIN, 0)]
        md = build_markdown(build_regime_strategy_fit(events))
        self.assertIn("## Notes", md)
        self.assertIn("WEIRD_REGIME", md)


class DeterminismTests(unittest.TestCase):
    def test_same_fit_same_markdown(self):
        events = _wins("momentum", Regime.BULL, 30) + _wins("mean_rev", Regime.BEAR, 4)
        fit = build_regime_strategy_fit(events)
        self.assertEqual(
            build_markdown(fit, generated_at=FIXED_TIME),
            build_markdown(fit, generated_at=FIXED_TIME),
        )


class SafetyImportTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(report.__file__).read_text(encoding="utf-8")
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
        runner = Path(report.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("regime_strategy_fit_report", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
