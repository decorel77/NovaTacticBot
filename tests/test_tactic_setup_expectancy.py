"""TACTIC-TRUST-002 — expectancy-by-setup soak breakdown tests.

Pins the diagnostic-only, unwired, fail-closed-trust properties: a per-setup
synthetic expectancy table is produced, the spread localises an edge, yet EVERY
setup stays DIAGNOSTIC_ONLY (synthetic ⇒ never STRONG). Report is deterministic
and writes nothing. Broker-free: ``python -S -m unittest
tests.test_tactic_setup_expectancy``.
"""
from __future__ import annotations

import unittest

from research.stock_tactics_backtest import KNOWN_SETUP_LABELS
from research.tactic_setup_expectancy import (
    SETUP_PROFILES,
    run_setup_expectancy_study,
)


def _study(**kw):
    return run_setup_expectancy_study(generated_at="2026-06-30T00:00:00+00:00", **kw)


class MarkersTest(unittest.TestCase):
    def test_research_and_unwired_markers(self) -> None:
        s = _study()
        self.assertTrue(s["research_only"])
        self.assertTrue(s["diagnostic_only"])
        self.assertFalse(s["wired_into_execution"])
        self.assertFalse(s["data_is_real"])
        self.assertEqual(s["schema_version"], "tactic_setup_expectancy.v1")

    def test_profiles_are_known_setups(self) -> None:
        self.assertTrue(set(SETUP_PROFILES) <= set(KNOWN_SETUP_LABELS))


class PerSetupTableTest(unittest.TestCase):
    def test_one_row_per_setup(self) -> None:
        rows = _study()["per_setup"]
        self.assertEqual({r["setup"] for r in rows}, set(SETUP_PROFILES))
        for r in rows:
            self.assertIn("expectancy_pct", r)
            self.assertIn("win_rate", r)
            self.assertGreater(r["trades"], 0)

    def test_expectancy_spreads_and_localises_edge(self) -> None:
        s = _study()
        ec = s["edge_concentration"]
        # The positive-drift trend/breakout families carry the (synthetic) edge;
        # the negative-drift rebound does not.
        self.assertIn("TREND_CONTINUATION", ec["positive_expectancy_setups"])
        self.assertIn("OVERSOLD_REBOUND", ec["negative_expectancy_setups"])
        # Ranking is best-first and well-formed.
        self.assertEqual(set(ec["ranked_by_expectancy"]), set(SETUP_PROFILES))
        self.assertEqual(ec["best_setup"], ec["ranked_by_expectancy"][0])


class FailClosedTrustTest(unittest.TestCase):
    def test_no_setup_is_ever_approved_strong(self) -> None:
        s = _study()
        self.assertFalse(s["edge_concentration"]["any_setup_approved_strong"])
        for r in s["per_setup"]:
            self.assertFalse(r["floor_approved"], r["setup"])
            self.assertFalse(r["floor_verdict"]["approved"], r["setup"])


class DeterminismTest(unittest.TestCase):
    def test_report_is_reproducible(self) -> None:
        self.assertEqual(_study(), _study())


if __name__ == "__main__":
    unittest.main()
