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


class TestFailClosedPartialRecords(unittest.TestCase):
    """Partial/empty baseline records must not crash or invent flags.

    Verifies the analyser stays fail-closed when comparators are absent:
    missing metrics are skipped, never coerced into a fabricated trend.
    """

    def _analyser_with_baselines(self, baselines: list[dict]) -> CrossRunTrendAnalyser:
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        return CrossRunTrendAnalyser(bl_file, hist_file)

    def test_empty_dict_records_fail_closed(self):
        # Two structurally-empty snapshots: enough to pass the <2 guard, but
        # every metric is absent. Must not crash and must invent no flags.
        report = self._analyser_with_baselines([{}, {}]).analyse()
        self.assertFalse(report.has_significant_changes())
        self.assertIsNone(report.win_rate_delta)
        self.assertEqual(report.current_event_count, 0)
        self.assertTrue(len(report.observations) > 0)

    def test_missing_keys_do_not_fabricate_flags(self):
        # Prior missing win_rate + strategy_distribution; current carries only an
        # event count. No flag may be invented from absent comparators.
        prior = {"total_events": 100}
        current = {"total_events": 110}
        report = self._analyser_with_baselines([prior, current]).analyse()
        flags = [f.flag for f in report.flags]
        self.assertNotIn("SIGNIFICANT_WIN_RATE_SHIFT", flags)
        self.assertNotIn("STRATEGY_MIX_CHANGE", flags)
        self.assertIsNone(report.win_rate_delta)

    def test_partial_win_rate_averages_only_present_values(self):
        # win_rate present on only some priors: the average is taken over the
        # present values; absent ones are skipped, never coerced to 0.
        prior = [_make_baseline(0.60), _make_baseline(None), _make_baseline(0.60)]
        current = _make_baseline(0.61)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertAlmostEqual(report.recent_avg_win_rate, 0.60, places=2)


class TestFailClosedMalformedRecords(unittest.TestCase):
    """Present-but-malformed metrics must fail closed, never crash (HARDEN-SWEEP-007).

    Before the fix a single corrupt baseline record (``total_events: null`` /
    ``"oops"`` or a non-numeric / non-finite ``overall_win_rate``) raised a
    TypeError and took down the whole trend pass. Now such values are treated as
    absent.
    """

    def _analyser_with_baselines(self, baselines: list[dict]) -> CrossRunTrendAnalyser:
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        return CrossRunTrendAnalyser(bl_file, hist_file)

    def test_current_total_events_none_does_not_crash(self):
        report = self._analyser_with_baselines(
            [_make_baseline(total_events=10), {"overall_win_rate": 0.5, "total_events": None}]
        ).analyse()
        self.assertEqual(report.current_event_count, 0)

    def test_prior_total_events_string_is_skipped(self):
        # A garbage prior count must be skipped from the average, not crash.
        prior = [{"overall_win_rate": 0.5, "total_events": "oops"},
                 _make_baseline(0.5, total_events=10)]
        current = _make_baseline(0.5, total_events=11)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        # only the one finite prior count (10) averaged
        self.assertAlmostEqual(report.recent_avg_event_count, 10.0, places=6)

    def test_string_win_rate_is_treated_as_absent(self):
        prior = [{"overall_win_rate": "bad", "total_events": 10},
                 _make_baseline(0.60, total_events=12)]
        current = _make_baseline(0.61, total_events=12)
        report = self._analyser_with_baselines(prior + [current]).analyse()
        # the malformed prior win_rate is skipped; average rests on the one good value
        self.assertAlmostEqual(report.recent_avg_win_rate, 0.60, places=6)

    def test_non_finite_win_rate_is_treated_as_absent(self):
        prior = [{"overall_win_rate": float("inf"), "total_events": 10},
                 _make_baseline(0.60, total_events=12)]
        current = {"overall_win_rate": float("nan"), "total_events": 12}
        report = self._analyser_with_baselines(prior + [current]).analyse()
        self.assertIsNone(report.current_win_rate)           # NaN current -> absent
        self.assertAlmostEqual(report.recent_avg_win_rate, 0.60, places=6)
        self.assertIsNone(report.win_rate_delta)             # no delta without a current

    def test_bool_total_events_is_not_treated_as_number(self):
        # bool is an int subclass; True must not masquerade as 1 event.
        report = self._analyser_with_baselines(
            [_make_baseline(total_events=10), {"total_events": True}]
        ).analyse()
        self.assertEqual(report.current_event_count, 0)


class TestSmallSampleVisibility(unittest.TestCase):
    """The report must expose how few baselines a verdict rests on."""

    def _analyser_with_baselines(self, baselines: list[dict]) -> CrossRunTrendAnalyser:
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        _write_baselines(bl_file, baselines)
        return CrossRunTrendAnalyser(bl_file, hist_file)

    def test_baselines_compared_is_one_with_two_baselines(self):
        # Only a single prior snapshot to compare against: baselines_compared
        # must reflect that small sample so consumers treat it as diagnostic,
        # even when a threshold-crossing shift is flagged.
        report = self._analyser_with_baselines(
            [_make_baseline(0.70), _make_baseline(0.55)]
        ).analyse()
        self.assertEqual(report.baselines_compared, 1)


class TestDeterminism(unittest.TestCase):
    """Same input must yield identical flags + observations.

    The analyser uses no wall-clock and no randomness, so repeated passes over
    identical synthetic baselines must produce byte-stable summaries.
    """

    def test_repeated_analysis_is_deterministic(self):
        tmpdir = tempfile.mkdtemp()
        bl_file = Path(tmpdir) / "analytics_baseline.json"
        hist_file = Path(tmpdir) / "run_history.json"
        baselines = (
            [_make_baseline(
                0.70, total_events=100,
                strategy_distribution={"MOMENTUM": 50, "MEAN_REV": 30, "BREAKOUT": 20},
            )] * 3
            + [_make_baseline(
                0.55, total_events=160,
                strategy_distribution={"MOMENTUM": 50, "SCALP": 30, "BREAKOUT": 20},
            )]
        )
        _write_baselines(bl_file, baselines)

        r1 = CrossRunTrendAnalyser(bl_file, hist_file).analyse()
        r2 = CrossRunTrendAnalyser(bl_file, hist_file).analyse()

        self.assertEqual(
            [(f.flag, f.detail) for f in r1.flags],
            [(f.flag, f.detail) for f in r2.flags],
        )
        self.assertEqual(r1.observations, r2.observations)


if __name__ == "__main__":
    unittest.main()
