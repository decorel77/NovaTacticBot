"""Tests for the offline pattern recognition prototype (NEXT-PR-001).

Deterministic, fixture-driven, broker-free. No network, no live path. Every
detector is pinned with small synthetic inputs and exact expected numbers.
"""
import unittest
from pathlib import Path

from research import pattern_recognition as pr
from research.pattern_recognition import (
    PatternBar,
    PatternConfig,
    TradeOutcome,
    detect_breakout_after_consolidation,
    detect_drawdown_recovery,
    detect_failed_breakout,
    detect_gap_continuation_risk,
    detect_higher_high_higher_low,
    detect_mean_reversion_candidate,
    detect_trend_continuation,
    detect_volume_spike,
    detect_win_loss_clusters,
    load_dataset,
    scan_patterns,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "patterns"


def _bar(date, o, h, l, c, v=None):
    return PatternBar(date=date, open=o, high=h, low=l, close=c, volume=v)


def _by_name(report):
    return {s.pattern_name: s for s in report.signals}


# --------------------------------------------------------------------------- #
# Fixture-level scan
# --------------------------------------------------------------------------- #
class BreakoutVolumeFixtureScanTests(unittest.TestCase):
    def setUp(self):
        bars, _, symbol, _ = load_dataset(FIXTURES / "breakout_volume.json")
        cfg = PatternConfig(
            consolidation_window=6, volume_spike_window=6, trend_window=6, lookback=8
        )
        self.report = scan_patterns(bars, cfg, symbol=symbol)
        self.sig = _by_name(self.report)

    def test_provenance_flags(self):
        self.assertTrue(self.report.research_only)
        self.assertEqual("disabled", self.report.broker_execution)
        self.assertFalse(self.report.data_is_real)
        self.assertEqual("fixture", self.report.input_source)
        self.assertEqual((), self.report.errors)
        self.assertEqual(8, self.report.bars_analysed)

    def test_all_price_detectors_present(self):
        # Eight price-series detectors, no cluster signal (no outcomes passed).
        self.assertEqual(8, len(self.report.signals))
        self.assertNotIn("win_loss_clusters", self.sig)

    def test_breakout_detected_with_evidence(self):
        s = self.sig["breakout_after_consolidation"]
        self.assertTrue(s.detected)
        self.assertAlmostEqual(0.696, s.confidence_score, places=3)
        self.assertEqual(101.0, s.evidence["consolidation_high"])
        self.assertTrue(s.evidence["consolidated"])
        self.assertAlmostEqual(2.0, s.evidence["consolidation_range_pct"])
        self.assertTrue(s.research_only)

    def test_volume_spike_detected(self):
        s = self.sig["volume_spike"]
        self.assertTrue(s.detected)
        self.assertAlmostEqual(0.75, s.confidence_score)
        self.assertEqual(1000.0, s.evidence["baseline_volume"])
        self.assertEqual(3000.0, s.evidence["last_volume"])
        self.assertAlmostEqual(3.0, s.evidence["ratio"])


# --------------------------------------------------------------------------- #
# Breakout after consolidation
# --------------------------------------------------------------------------- #
class BreakoutTests(unittest.TestCase):
    def _flat(self):
        return [
            _bar("2024-01-01", 100, 101, 99, 100),
            _bar("2024-01-02", 100, 101, 99, 100),
            _bar("2024-01-03", 100, 101, 99, 100),
        ]

    def test_no_breakout_when_close_inside_range(self):
        bars = self._flat() + [_bar("2024-01-04", 100, 101, 99, 100.5)]
        s = detect_breakout_after_consolidation(bars, PatternConfig(consolidation_window=3))
        self.assertFalse(s.detected)
        self.assertEqual(0.0, s.confidence_score)
        self.assertTrue(s.evidence["consolidated"])

    def test_insufficient_bars_fails_closed(self):
        s = detect_breakout_after_consolidation(self._flat(), PatternConfig(consolidation_window=10))
        self.assertFalse(s.detected)
        self.assertIsNotNone(s.fail_closed_reason)
        self.assertTrue(any("insufficient" in m for m in s.missing_data))
        self.assertFalse(s.data_is_real)  # fail-closed never vouches for realness


# --------------------------------------------------------------------------- #
# Volume spike
# --------------------------------------------------------------------------- #
class VolumeSpikeTests(unittest.TestCase):
    def _bars(self, last_vol, window_vol=100):
        return [
            _bar("2024-01-01", 100, 101, 99, 100, window_vol),
            _bar("2024-01-02", 100, 101, 99, 100, window_vol),
            _bar("2024-01-03", 100, 101, 99, 100, window_vol),
            _bar("2024-01-04", 100, 101, 99, 100, last_vol),
        ]

    def test_spike_detected(self):
        s = detect_volume_spike(self._bars(400), PatternConfig(volume_spike_window=3))
        self.assertTrue(s.detected)
        self.assertAlmostEqual(4.0, s.evidence["ratio"])

    def test_no_spike_below_multiple(self):
        s = detect_volume_spike(self._bars(150), PatternConfig(volume_spike_window=3))
        self.assertFalse(s.detected)

    def test_missing_volume_fails_closed(self):
        bars = self._bars(400)
        bars[1] = _bar("2024-01-02", 100, 101, 99, 100, None)
        s = detect_volume_spike(bars, PatternConfig(volume_spike_window=3))
        self.assertFalse(s.detected)
        self.assertIn("volume", s.missing_data)
        self.assertIsNotNone(s.fail_closed_reason)


# --------------------------------------------------------------------------- #
# Trend continuation
# --------------------------------------------------------------------------- #
class TrendContinuationTests(unittest.TestCase):
    def test_clean_uptrend_continuation(self):
        bars = [
            _bar("2024-01-0%d" % (i + 1), c, c + 1, c - 1, c)
            for i, c in enumerate([100, 101, 102, 103, 104, 105, 106])
        ]
        s = detect_trend_continuation(bars, PatternConfig(trend_window=6))
        self.assertTrue(s.detected)
        self.assertEqual("up", s.evidence["direction"])
        self.assertAlmostEqual(1.0, s.confidence_score)
        self.assertAlmostEqual(6.0, s.evidence["net_return_pct"])

    def test_choppy_series_not_continuation(self):
        closes = [100, 102, 99, 103, 98, 104, 100]
        bars = [
            _bar("2024-01-0%d" % (i + 1), c, c + 2, c - 2, c)
            for i, c in enumerate(closes)
        ]
        s = detect_trend_continuation(bars, PatternConfig(trend_window=6))
        self.assertFalse(s.detected)


# --------------------------------------------------------------------------- #
# Mean reversion candidate
# --------------------------------------------------------------------------- #
class MeanReversionTests(unittest.TestCase):
    def _bars(self, closes):
        return [
            _bar("2024-01-0%d" % (i + 1), c, c + 1, c - 1, c)
            for i, c in enumerate(closes)
        ]

    def test_overbought_extreme_detected(self):
        s = detect_mean_reversion_candidate(
            self._bars([100, 100, 100, 100, 110]), PatternConfig(lookback=5)
        )
        self.assertTrue(s.detected)
        self.assertEqual("overbought_reversion_down", s.evidence["direction"])
        self.assertAlmostEqual(2.0, s.evidence["zscore"], places=4)
        self.assertAlmostEqual(0.5, s.confidence_score)

    def test_oversold_extreme_detected(self):
        s = detect_mean_reversion_candidate(
            self._bars([100, 100, 100, 100, 90]), PatternConfig(lookback=5)
        )
        self.assertTrue(s.detected)
        self.assertEqual("oversold_reversion_up", s.evidence["direction"])
        self.assertAlmostEqual(-2.0, s.evidence["zscore"], places=4)

    def test_zero_variance_fails_closed(self):
        s = detect_mean_reversion_candidate(
            self._bars([100, 100, 100, 100, 100]), PatternConfig(lookback=5)
        )
        self.assertFalse(s.detected)
        self.assertIn("zero variance", s.fail_closed_reason)


# --------------------------------------------------------------------------- #
# Gap continuation risk
# --------------------------------------------------------------------------- #
class GapTests(unittest.TestCase):
    def test_gap_up_continuation_risk(self):
        bars = [
            _bar("2024-01-01", 100, 101, 99, 100),
            _bar("2024-01-02", 103, 105, 102, 104),  # opens 3% above prior close, closes up, not filled
        ]
        s = detect_gap_continuation_risk(bars, PatternConfig(gap_pct=2.0))
        self.assertTrue(s.detected)
        self.assertEqual("gap_up", s.evidence["direction"])
        self.assertAlmostEqual(3.0, s.evidence["gap_pct"])
        self.assertTrue(s.evidence["continuation_risk"])
        self.assertFalse(s.evidence["gap_filled"])
        self.assertAlmostEqual(0.75, s.confidence_score)

    def test_gap_down_detected(self):
        bars = [
            _bar("2024-01-01", 100, 101, 99, 100),
            _bar("2024-01-02", 97, 98, 95, 96),  # opens 3% below, closes down, not filled
        ]
        s = detect_gap_continuation_risk(bars, PatternConfig(gap_pct=2.0))
        self.assertTrue(s.detected)
        self.assertEqual("gap_down", s.evidence["direction"])

    def test_small_gap_not_detected(self):
        bars = [
            _bar("2024-01-01", 100, 101, 99, 100),
            _bar("2024-01-02", 100.5, 101, 100, 100.5),
        ]
        s = detect_gap_continuation_risk(bars, PatternConfig(gap_pct=2.0))
        self.assertFalse(s.detected)


# --------------------------------------------------------------------------- #
# Failed breakout
# --------------------------------------------------------------------------- #
class FailedBreakoutTests(unittest.TestCase):
    def test_failed_breakout_detected(self):
        bars = [
            _bar("2024-01-01", 100, 102, 99, 101),
            _bar("2024-01-02", 101, 102, 100, 101),
            _bar("2024-01-03", 101, 102, 100, 101),
            _bar("2024-01-04", 102, 106, 101, 105),  # pokes above 102
            _bar("2024-01-05", 104, 105, 100, 101),  # closes back below 102
        ]
        s = detect_failed_breakout(bars, PatternConfig(consolidation_window=3))
        self.assertTrue(s.detected)
        self.assertEqual(102.0, s.evidence["base_high"])
        self.assertEqual(106.0, s.evidence["breakout_high"])
        self.assertEqual(101.0, s.evidence["fail_close"])

    def test_held_breakout_not_failed(self):
        bars = [
            _bar("2024-01-01", 100, 102, 99, 101),
            _bar("2024-01-02", 101, 102, 100, 101),
            _bar("2024-01-03", 101, 102, 100, 101),
            _bar("2024-01-04", 102, 106, 101, 105),
            _bar("2024-01-05", 105, 107, 104, 106),  # closes above 102 -> held
        ]
        s = detect_failed_breakout(bars, PatternConfig(consolidation_window=3))
        self.assertFalse(s.detected)


# --------------------------------------------------------------------------- #
# Higher-high / higher-low structure
# --------------------------------------------------------------------------- #
class StructureTests(unittest.TestCase):
    def test_higher_high_higher_low(self):
        highs_lows = [(101, 99), (102, 100), (103, 101), (104, 102), (105, 103), (106, 104)]
        bars = [
            _bar("2024-01-0%d" % (i + 1), (h + l) / 2, h, l, (h + l) / 2)
            for i, (h, l) in enumerate(highs_lows)
        ]
        s = detect_higher_high_higher_low(bars, PatternConfig(trend_window=6))
        self.assertTrue(s.detected)
        self.assertEqual("HH_HL", s.evidence["structure"])

    def test_lower_high_lower_low(self):
        highs_lows = [(106, 104), (105, 103), (104, 102), (103, 101), (102, 100), (101, 99)]
        bars = [
            _bar("2024-01-0%d" % (i + 1), (h + l) / 2, h, l, (h + l) / 2)
            for i, (h, l) in enumerate(highs_lows)
        ]
        s = detect_higher_high_higher_low(bars, PatternConfig(trend_window=6))
        self.assertTrue(s.detected)
        self.assertEqual("LH_LL", s.evidence["structure"])

    def test_mixed_structure_not_detected(self):
        highs_lows = [(101, 95), (106, 100), (103, 97), (104, 96), (102, 98), (105, 99)]
        bars = [
            _bar("2024-01-0%d" % (i + 1), (h + l) / 2, h, l, (h + l) / 2)
            for i, (h, l) in enumerate(highs_lows)
        ]
        s = detect_higher_high_higher_low(bars, PatternConfig(trend_window=6))
        self.assertFalse(s.detected)
        self.assertEqual("mixed", s.evidence["structure"])


# --------------------------------------------------------------------------- #
# Drawdown / recovery
# --------------------------------------------------------------------------- #
class DrawdownRecoveryTests(unittest.TestCase):
    def test_drawdown_then_recovery_detected(self):
        closes = [100, 120, 90, 95, 100, 105, 108]
        bars = [
            _bar("2024-01-0%d" % (i + 1), c, c + 1, c - 1, c)
            for i, c in enumerate(closes)
        ]
        s = detect_drawdown_recovery(bars, PatternConfig(lookback=7))
        self.assertTrue(s.detected)
        self.assertEqual(120.0, s.evidence["peak"])
        self.assertEqual(90.0, s.evidence["trough"])
        self.assertAlmostEqual(-25.0, s.evidence["max_drawdown_pct"])
        self.assertAlmostEqual(0.6, s.evidence["recovered_frac"])
        self.assertAlmostEqual(0.8, s.confidence_score)

    def test_shallow_drawdown_not_detected(self):
        closes = [100, 101, 99, 100, 101, 102, 103]
        bars = [
            _bar("2024-01-0%d" % (i + 1), c, c + 1, c - 1, c)
            for i, c in enumerate(closes)
        ]
        s = detect_drawdown_recovery(bars, PatternConfig(lookback=7, drawdown_pct=10.0))
        self.assertFalse(s.detected)


# --------------------------------------------------------------------------- #
# Win/loss clusters by setup label
# --------------------------------------------------------------------------- #
class WinLossClusterTests(unittest.TestCase):
    def setUp(self):
        _, self.outcomes, _, _ = load_dataset(FIXTURES / "outcomes_clusters.json")
        self.cfg = PatternConfig(cluster_min_outcomes=6, cluster_min_len=3)

    def test_clusters_detected(self):
        s = detect_win_loss_clusters(self.outcomes, self.cfg)
        self.assertTrue(s.detected)
        self.assertAlmostEqual(0.5, s.confidence_score)

    def test_per_setup_streaks_and_sorted_keys(self):
        s = detect_win_loss_clusters(self.outcomes, self.cfg)
        by_setup = s.evidence["by_setup"]
        self.assertEqual(
            ["BREAKOUT", "RSI_CROSS_UP", "TREND_PULLBACK", "UNKNOWN"], list(by_setup)
        )
        self.assertEqual(3, by_setup["TREND_PULLBACK"]["longest_win_streak"])
        self.assertEqual(3, by_setup["RSI_CROSS_UP"]["longest_loss_streak"])

    def test_flagged_clusters(self):
        s = detect_win_loss_clusters(self.outcomes, self.cfg)
        flagged = s.evidence["flagged_clusters"]
        self.assertIn({"setup": "TREND_PULLBACK", "kind": "win", "length": 3}, flagged)
        self.assertIn({"setup": "RSI_CROSS_UP", "kind": "loss", "length": 3}, flagged)

    def test_unrecognized_label_recorded_not_attributed(self):
        s = detect_win_loss_clusters(self.outcomes, self.cfg)
        self.assertIn("MYSTERY", s.evidence["unrecognized_labels"])
        # The mystery outcome lands in UNKNOWN, never in a real setup family.
        self.assertEqual(1, s.evidence["by_setup"]["UNKNOWN"]["n"])

    def test_insufficient_outcomes_fails_closed(self):
        few = [
            TradeOutcome("2024-02-01", "TREND_PULLBACK", True),
            TradeOutcome("2024-02-02", "TREND_PULLBACK", True),
        ]
        s = detect_win_loss_clusters(few, self.cfg)
        self.assertFalse(s.detected)
        self.assertIsNotNone(s.fail_closed_reason)
        self.assertTrue(any("insufficient" in m for m in s.missing_data))


# --------------------------------------------------------------------------- #
# Top-level scan integration + provenance propagation
# --------------------------------------------------------------------------- #
class ScanIntegrationTests(unittest.TestCase):
    def test_scan_includes_cluster_signal_and_notes_when_outcomes_supplied(self):
        bars, outcomes, symbol, _ = load_dataset(FIXTURES / "outcomes_clusters.json")
        cfg = PatternConfig(
            consolidation_window=6, volume_spike_window=6, trend_window=6,
            lookback=8, cluster_min_outcomes=6, cluster_min_len=3,
        )
        report = scan_patterns(bars, cfg, symbol=symbol, outcomes=outcomes)
        names = [s.pattern_name for s in report.signals]
        self.assertEqual(9, len(report.signals))
        self.assertIn("win_loss_clusters", names)
        self.assertTrue(any("MYSTERY" in n for n in report.notes))

    def test_data_is_real_propagates_into_detected_signals(self):
        bars, _, symbol, _ = load_dataset(FIXTURES / "breakout_volume.json")
        # lookback huge so mean_reversion/drawdown fail closed; small price windows
        # so breakout detects.
        cfg = PatternConfig(
            consolidation_window=6, volume_spike_window=6, trend_window=6, lookback=50
        )
        report = scan_patterns(bars, cfg, symbol=symbol, data_is_real=True)
        sig = _by_name(report)
        self.assertTrue(report.data_is_real)
        self.assertTrue(sig["breakout_after_consolidation"].detected)
        self.assertTrue(sig["breakout_after_consolidation"].data_is_real)
        # A fail-closed (insufficient) signal forces data_is_real False.
        self.assertIsNotNone(sig["mean_reversion_candidate"].fail_closed_reason)
        self.assertFalse(sig["mean_reversion_candidate"].data_is_real)

    def test_determinism(self):
        bars, outcomes, symbol, _ = load_dataset(FIXTURES / "outcomes_clusters.json")
        cfg = PatternConfig(consolidation_window=6, volume_spike_window=6, trend_window=6, lookback=8)
        r1 = scan_patterns(bars, cfg, symbol=symbol, outcomes=outcomes)
        r2 = scan_patterns(bars, cfg, symbol=symbol, outcomes=outcomes)
        self.assertEqual(pr.report_to_dict(r1), pr.report_to_dict(r2))


# --------------------------------------------------------------------------- #
# Dataset-level fail-closed
# --------------------------------------------------------------------------- #
class FailClosedTests(unittest.TestCase):
    def _good(self):
        return [
            _bar("2024-01-01", 100, 101, 99, 100, 1000),
            _bar("2024-01-02", 100, 110, 100, 108, 1000),
            _bar("2024-01-03", 108, 112, 106, 110, 1000),
        ]

    def test_high_below_low_fails_closed(self):
        bars = self._good()
        bars[1] = _bar("2024-01-02", 100, 90, 100, 95, 1000)  # high < low
        report = scan_patterns(bars, symbol="X", data_is_real=True)
        self.assertFalse(report.ok)
        self.assertEqual((), report.signals)
        self.assertFalse(report.data_is_real)  # forced false even though caller asserted true

    def test_empty_bars_fail_closed(self):
        report = scan_patterns([], symbol="X")
        self.assertFalse(report.ok)
        self.assertIn("no price bars provided", report.errors)

    def test_negative_volume_fails_closed(self):
        bars = self._good()
        bars[0] = _bar("2024-01-01", 100, 101, 99, 100, -5)
        report = scan_patterns(bars, symbol="X")
        self.assertFalse(report.ok)
        self.assertTrue(any("volume must be >= 0" in e for e in report.errors))

    def test_non_increasing_dates_fail_closed(self):
        bars = self._good()
        bars[2] = _bar("2024-01-02", 108, 112, 106, 110, 1000)  # duplicate date
        report = scan_patterns(bars, symbol="X")
        self.assertFalse(report.ok)
        self.assertTrue(any("strictly increasing" in e for e in report.errors))


# --------------------------------------------------------------------------- #
# Rendering / CLI
# --------------------------------------------------------------------------- #
class RenderCliTests(unittest.TestCase):
    def test_render_marks_research_only(self):
        bars, _, symbol, _ = load_dataset(FIXTURES / "breakout_volume.json")
        report = scan_patterns(bars, PatternConfig(consolidation_window=6, volume_spike_window=6,
                                                   trend_window=6, lookback=8), symbol=symbol)
        text = pr.render_report_text(report)
        self.assertIn("RESEARCH ONLY", text)
        self.assertIn("research_only: True", text)
        self.assertIn("broker_execution: disabled", text)
        self.assertIn("NOT trade", text)

    def test_main_returns_zero_on_valid_fixture(self):
        rc = pr.main([str(FIXTURES / "breakout_volume.json"),
                      "--consolidation-window", "6", "--volume-window", "6", "--trend-window", "6"])
        self.assertEqual(0, rc)


# --------------------------------------------------------------------------- #
# Safety: no broker / network / runtime imports (mirrors the backtest harness)
# --------------------------------------------------------------------------- #
class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(pr.__file__).read_text(encoding="utf-8")
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
            "nova_koopbot",
            "nova_verkoopbot",
            "workflow.nova_scheduler",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_module_does_not_import_novabotv2_runtime(self):
        source = Path(pr.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import core.nova", source)
        self.assertNotIn("from core import nova", source)

    def test_module_is_not_wired_into_runner(self):
        # The advisory runner must not import the research module.
        runner = (Path(pr.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py")
        if runner.is_file():
            self.assertNotIn("pattern_recognition", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
