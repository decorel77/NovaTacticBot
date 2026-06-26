"""Tests for the offline RESEARCH-ONLY indicator prototypes (TA-004).

Deterministic, broker-free, stdlib-only. Pins fail-closed behaviour on
NaN/inf/insufficient/wrong-type input, determinism, basic correctness
properties, and import-isolation (no broker/network/pandas; not wired into the
runner).
"""
import math
import unittest
from pathlib import Path

from research import research_indicators as ri
from research.research_indicators import (
    STATUS_FAIL_CLOSED,
    STATUS_OK,
    ResearchIndicatorConfig,
    compute_bollinger,
    compute_macd,
    compute_research_indicators,
    compute_volume_trend,
)

# Tiny periods so short synthetic series exercise the real code paths.
CFG = ResearchIndicatorConfig(
    macd_fast=2, macd_slow=4, macd_signal=2, bb_period=4, bb_k=2.0, vol_short=2, vol_long=4
)

RISING = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
FLAT = [100.0] * 8


class MacdTests(unittest.TestCase):
    def test_macd_ok_and_histogram_consistent(self):
        r = compute_macd(RISING, CFG)
        self.assertEqual(STATUS_OK, r.status)
        self.assertTrue(r.research_only)
        self.assertAlmostEqual(r.histogram, round(r.macd - r.signal, 6), places=6)

    def test_rising_series_has_positive_macd(self):
        # Fast EMA leads a monotonic uptrend -> MACD line above the slow EMA.
        self.assertGreater(compute_macd(RISING, CFG).macd, 0.0)

    def test_flat_series_macd_is_zero(self):
        r = compute_macd(FLAT, CFG)
        self.assertEqual(STATUS_OK, r.status)
        self.assertEqual(0.0, r.macd)
        self.assertEqual(0.0, r.histogram)

    def test_insufficient_length_fails_closed(self):
        r = compute_macd([1.0, 2.0, 3.0], CFG)  # need macd_slow+signal = 6
        self.assertEqual(STATUS_FAIL_CLOSED, r.status)
        self.assertIsNone(r.macd)
        self.assertIn("insufficient", r.fail_closed_reason)

    def test_non_finite_fails_closed(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                series = RISING[:-1] + [bad]
                r = compute_macd(series, CFG)
                self.assertEqual(STATUS_FAIL_CLOSED, r.status)
                self.assertIsNone(r.macd)

    def test_bool_value_fails_closed(self):
        series = RISING[:-1] + [True]  # bool is not a valid price
        self.assertEqual(STATUS_FAIL_CLOSED, compute_macd(series, CFG).status)

    def test_invalid_periods_fail_closed(self):
        bad = ResearchIndicatorConfig(macd_fast=10, macd_slow=5)  # fast >= slow
        self.assertEqual(STATUS_FAIL_CLOSED, compute_macd(RISING, bad).status)


class BollingerTests(unittest.TestCase):
    def test_bollinger_ok_ordering(self):
        r = compute_bollinger([10.0, 12.0, 11.0, 13.0, 12.0, 14.0], CFG)
        self.assertEqual(STATUS_OK, r.status)
        self.assertLess(r.lower, r.mid)
        self.assertLess(r.mid, r.upper)
        self.assertIsNotNone(r.percent_b)

    def test_zero_variance_fails_closed(self):
        r = compute_bollinger([50.0, 50.0, 50.0, 50.0], CFG)
        self.assertEqual(STATUS_FAIL_CLOSED, r.status)
        self.assertIsNone(r.percent_b)
        self.assertIn("zero variance", r.fail_closed_reason)

    def test_insufficient_length_fails_closed(self):
        self.assertEqual(STATUS_FAIL_CLOSED, compute_bollinger([1.0, 2.0], CFG).status)

    def test_non_finite_fails_closed(self):
        self.assertEqual(
            STATUS_FAIL_CLOSED,
            compute_bollinger([10.0, 11.0, float("nan"), 13.0], CFG).status,
        )


class VolumeTrendTests(unittest.TestCase):
    def test_rising_volume(self):
        r = compute_volume_trend([1.0, 1.0, 1.0, 1.0, 5.0, 5.0], CFG)
        self.assertEqual(STATUS_OK, r.status)
        self.assertEqual("rising", r.direction)
        self.assertGreater(r.ratio, 1.0)

    def test_falling_volume(self):
        r = compute_volume_trend([5.0, 5.0, 5.0, 5.0, 1.0, 1.0], CFG)
        self.assertEqual("falling", r.direction)
        self.assertLess(r.ratio, 1.0)

    def test_flat_volume(self):
        r = compute_volume_trend([4.0, 4.0, 4.0, 4.0, 4.0, 4.0], CFG)
        self.assertEqual("flat", r.direction)
        self.assertEqual(1.0, r.ratio)

    def test_negative_volume_fails_closed(self):
        r = compute_volume_trend([1.0, 1.0, 1.0, 1.0, -5.0, 5.0], CFG)
        self.assertEqual(STATUS_FAIL_CLOSED, r.status)
        self.assertIn("negative", r.fail_closed_reason)

    def test_non_finite_volume_fails_closed(self):
        self.assertEqual(
            STATUS_FAIL_CLOSED,
            compute_volume_trend([1.0, 2.0, float("inf"), 4.0], CFG).status,
        )

    def test_insufficient_length_fails_closed(self):
        self.assertEqual(STATUS_FAIL_CLOSED, compute_volume_trend([1.0, 2.0], CFG).status)


class AggregateAndDeterminismTests(unittest.TestCase):
    def test_all_ok_report(self):
        report = compute_research_indicators(RISING, [1.0] * 4 + [5.0, 5.0], CFG)
        self.assertEqual(STATUS_OK, report.status)
        self.assertTrue(report.research_only)
        self.assertEqual("disabled", report.broker_execution)
        self.assertTrue(any("RESEARCH-ONLY" in n for n in report.notes))

    def test_missing_volumes_marks_report_fail_closed(self):
        report = compute_research_indicators(RISING, None, CFG)
        self.assertEqual(STATUS_FAIL_CLOSED, report.status)  # volume_trend fails closed
        self.assertEqual(STATUS_OK, report.macd.status)       # but MACD still computed

    def test_determinism(self):
        a = compute_research_indicators(RISING, [1.0] * 4 + [5.0, 5.0], CFG)
        b = compute_research_indicators(RISING, [1.0] * 4 + [5.0, 5.0], CFG)
        self.assertEqual(a, b)  # frozen dataclasses compare by value


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(ri.__file__).read_text(encoding="utf-8")
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
            "import pandas",
            "import numpy",
            "place_order",
            "submit_order",
            "cancel_order",
            "nova_koopbot",
            "nova_verkoopbot",
            "workflow.nova_scheduler",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_module_is_not_wired_into_runner(self):
        runner = Path(ri.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("research_indicators", runner.read_text(encoding="utf-8"))

    def test_module_does_not_import_novabotv2_live_indicator_path(self):
        # Scan import lines only — the docstring legitimately names the live-path
        # functions to say this module must NOT be added to them.
        source = Path(ri.__file__).read_text(encoding="utf-8")
        import_lines = "\n".join(
            ln for ln in source.splitlines()
            if ln.strip().startswith(("import ", "from "))
        )
        for token in ("build_indicator_frame", "detect_setup", "nova_market_scanner",
                      "market_data_utils", "signal_setup_utils"):
            with self.subTest(token=token):
                self.assertNotIn(token, import_lines)


if __name__ == "__main__":
    unittest.main()
