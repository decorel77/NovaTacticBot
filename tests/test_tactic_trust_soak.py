"""TACTIC-TRUST-001 — reproducible TacticBot edge/soak tracking study.

Pins the diagnostic-only trust-gate behaviour: a synthetic tactic — no matter how
good its backtest looks — can never be approved STRONG (it always carries
``data_not_real``), and below the 30-sample floor it is additionally gated on
sample size. This makes the ~1/30 trust posture an enforced, visible property, and
confirms the soak machinery stays unwired. Runs under the broker-free pytest venv.
"""
from __future__ import annotations

import unittest

from research.tactic_trust_soak import build_tactic_trust_soak


def _soak(n, **kw):
    return build_tactic_trust_soak(
        n_signals=n, generated_at="2026-06-29T00:00:00+00:00", **kw
    )


class SoakReportShapeTest(unittest.TestCase):
    def test_research_and_unwired_markers(self) -> None:
        s = _soak(40)
        self.assertTrue(s["research_only"])
        self.assertTrue(s["diagnostic_only"])
        self.assertIs(s["wired_into_execution"], False)
        self.assertIs(s["data_is_real"], False)

    def test_backtest_summary_present_and_positive_edge(self) -> None:
        s = _soak(40)
        self.assertIsNotNone(s["backtest_summary"])
        self.assertGreater(s["backtest_summary"]["expectancy_pct"], 0.0)


class FailClosedTrustGateTest(unittest.TestCase):
    def test_synthetic_never_approved_strong(self) -> None:
        # Across sample sizes and edge strengths, synthetic data is never STRONG.
        for kw in ({"n": 8}, {"n": 40}, {"n": 40, "drift": 0.006, "noise": 0.004}):
            n = kw.pop("n")
            v = _soak(n, **kw)["floor_verdict"]
            self.assertFalse(v["approved"])
            self.assertEqual(v["strength"], "DIAGNOSTIC_ONLY")
            self.assertIn("data_not_real", v["refusal_reasons"])

    def test_below_floor_is_gated_on_sample_size(self) -> None:
        s = _soak(8)
        self.assertFalse(s["soak_progress"]["sample_floor_met"])
        self.assertEqual(s["soak_progress"]["samples_remaining"], 22)
        self.assertTrue(
            any(r.startswith("sample_size_below_floor")
                for r in s["floor_verdict"]["refusal_reasons"])
        )

    def test_sample_floor_met_drops_sample_refusal(self) -> None:
        s = _soak(40)
        self.assertTrue(s["soak_progress"]["sample_floor_met"])
        self.assertEqual(s["soak_progress"]["samples_remaining"], 0)
        self.assertFalse(
            any(r.startswith("sample_size_below_floor")
                for r in s["floor_verdict"]["refusal_reasons"])
        )

    def test_high_edge_clean_leaves_only_real_data_and_regime_blockers(self) -> None:
        # A synthetic tactic that clears sample + win-rate + edge floors still
        # cannot be approved: the irreducible blockers are data_not_real +
        # regime_not_verified. This is the honest trust ceiling for research data.
        v = _soak(40, drift=0.006, noise=0.004)["floor_verdict"]
        self.assertEqual(
            set(v["refusal_reasons"]), {"data_not_real", "regime_not_verified"}
        )


if __name__ == "__main__":
    unittest.main()
