"""Tests for utils/cross_run_trend_analyser.py.

Verifies win-rate detection, volume shift detection, strategy mix change,
insufficient history handling, and the TrendReport dataclass.
"""
import json
import tempfile
import unittest
from pathlib import Path

from utils.cross_run_trend_analyser import (
    WIN_RATE_SHIFT_THRESHOLD,
    VOLUME_SHIFT_THRESHOLD,
    CrossRunTrendAnalyser,
    TrendReport,
)


def _make_baseline(
    overall_win_rate: float | None = 0.60,
    total_events: int = 100,
    strategy_distribution: dict | None = None,
) -> dict:
    return {
        "overall_win_rate": overall_win_rate,
        "total_events": total_events,
        "strategy_distribution": strategy_distribution or {"MOMENTUM": 50, "MEAN_REV": 30, "BREAKOUT": 20},
        "schema_version": "1.0",
    }


def _write_baselines(path: Path, baselines: list[dict]) -> None:
    path.write_text(json.dumps(baselines), encoding="utf-8")


class TestTrendReport(unittest.TestCase):
    def test_has_significant_changes_false_when_no_flags(self):
        report = TrendReport()
        self.assertFalse(report.has_significant_changes())

    def test_schema_version(self):
        report = TrendReport()
        self.assertEqual(report.schema_version, "1.0")


class TestInsufficientHistory(unittest.TestCase):
    def test_single_baseline_returns_no_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bl_file = Path(tmpdir) / "analytics_baseline.json"
            hist_file = Path(tmpdir) / "run_history.json"
            _write_baselines(bl_file, [_make_baseline()])
            analyser = CrossRunTrendAnalyser(bl_file, hist_file)
            report = analyser.analyse()
            self.assertFalse(report.has_significant_changes())
            self.assertTrue(len(report.observations) > 0)

    def test_empty_baselines_returns_no_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bl_file = Path(tmpdir) / "analytics_baseline.json"
            hist_file = Path(tmpdir) / "run_history.json"
            _write_baselines(bl_file, [])
            analyser = CrossRunTrendAnalyser(bl_file, hist_file)
            report = analyser.analyse()
            self.assertFalse(report.has_significant_changes())


class TestWinRateTrend(unittest.TestCase):
    def _analyser_with_baselines(self, baselines: list[dict]) -> CrossRunTrendAnalyser:
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        return CrossRunTrendAnalyser(bl_file, hist_file)

    def test_no_flag_when_win_rate_stable(self):
        baselines = [_make_baseline(0.60) for _ in range(4)] + [_make_baseline(0.62)]
        report = self._analyser_with_baselines(baselines).analyse()
        flags = [f.flag for f in report.flags]
        self.assertNotIn("SIGNIFICANT_WIN_RATE_SHIFT", flags)

    def test_flag_when_win_rate_drops_significantly(self):
        prior = [_make_baseline(0.70) for _ in range(4)]
        current = _make_baseline(0.60)  # 10pp drop > 5pp threshold
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertIn("SIGNIFICANT_WIN_RATE_SHIFT", flags)

    def test_flag_when_win_rate_rises_significantly(self):
        prior = [_make_baseline(0.50) for _ in range(4)]
        current = _make_baseline(0.62)  # 12pp rise > 5pp threshold
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertIn("SIGNIFICANT_WIN_RATE_SHIFT", flags)

    def test_win_rate_delta_computed(self):
        prior = [_make_baseline(0.60) for _ in range(3)]
        current = _make_baseline(0.70)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertAlmostEqual(report.win_rate_delta, 0.10, places=2)

    def test_no_flag_when_win_rate_none(self):
        prior = [_make_baseline(None) for _ in range(3)]
        current = _make_baseline(None)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertIsNone(report.win_rate_delta)

    def test_current_win_rate_stored(self):
        prior = [_make_baseline(0.60)] * 3
        current = _make_baseline(0.80)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertAlmostEqual(report.current_win_rate, 0.80)

    def test_recent_avg_win_rate_stored(self):
        prior = [_make_baseline(0.60)] * 3
        current = _make_baseline(0.80)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertAlmostEqual(report.recent_avg_win_rate, 0.60, places=2)


class TestVolumeShift(unittest.TestCase):
    def _analyser_with_baselines(self, baselines: list[dict]) -> CrossRunTrendAnalyser:
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        return CrossRunTrendAnalyser(bl_file, hist_file)

    def test_no_flag_when_volume_stable(self):
        prior = [_make_baseline(total_events=100)] * 4
        current = _make_baseline(total_events=105)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertNotIn("SIGNIFICANT_VOLUME_SHIFT", flags)

    def test_flag_when_volume_drops_30_pct(self):
        prior = [_make_baseline(total_events=100)] * 4
        current = _make_baseline(total_events=60)  # 40% drop
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertIn("SIGNIFICANT_VOLUME_SHIFT", flags)

    def test_flag_when_volume_rises_50_pct(self):
        prior = [_make_baseline(total_events=100)] * 4
        current = _make_baseline(total_events=160)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertIn("SIGNIFICANT_VOLUME_SHIFT", flags)

    def test_event_count_delta_pct_computed(self):
        prior = [_make_baseline(total_events=100)] * 2
        current = _make_baseline(total_events=150)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertAlmostEqual(report.event_count_delta_pct, 0.50, places=2)


class TestStrategyMixChange(unittest.TestCase):
    def _analyser_with_baselines(self, baselines: list[dict]) -> CrossRunTrendAnalyser:
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        return CrossRunTrendAnalyser(bl_file, hist_file)

    def test_no_flag_when_strategy_mix_unchanged(self):
        dist = {"MOMENTUM": 50, "MEAN_REV": 30}
        prior = [_make_baseline(strategy_distribution=dist)] * 2
        current = _make_baseline(strategy_distribution=dist)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertNotIn("STRATEGY_MIX_CHANGE", flags)

    def test_flag_when_strategy_mix_changes(self):
        dist_a = {"MOMENTUM": 50, "MEAN_REV": 30, "BREAKOUT": 20}
        dist_b = {"MOMENTUM": 50, "SCALP": 30, "BREAKOUT": 20}  # MEAN_REV removed, SCALP added
        prior = [_make_baseline(strategy_distribution=dist_a)]
        current = _make_baseline(strategy_distribution=dist_b)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertIn("STRATEGY_MIX_CHANGE", flags)


class TestBaselinesCompared(unittest.TestCase):
    def test_baselines_compared_capped_at_lookback(self):
        baselines = [_make_baseline()] * 10
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        analyser = CrossRunTrendAnalyser(bl_file, hist_file, lookback=3)
        report = analyser.analyse()
        self.assertEqual(report.baselines_compared, 3)

    def test_no_observations_when_flags_present(self):
        prior = [_make_baseline(0.70)] * 4
        current = _make_baseline(0.55)  # big drop
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, prior + [current])
        report = CrossRunTrendAnalyser(bl_file, hist_file).analyse()
        self.assertTrue(report.has_significant_changes())


class TestThresholdConstants(unittest.TestCase):
    def test_win_rate_threshold(self):
        self.assertEqual(WIN_RATE_SHIFT_THRESHOLD, 0.05)

    def test_volume_threshold(self):
        self.assertEqual(VOLUME_SHIFT_THRESHOLD, 0.30)


if __name__ == "__main__":
    unittest.main()
