"""Tests for the offline stock-tactics backtest harness (NEXT-015).

Deterministic, fixture-driven, broker-free. No network, no live path.
"""
import unittest
from pathlib import Path

from research import stock_tactics_backtest as bt
from research.stock_tactics_backtest import (
    BacktestConfig,
    PriceBar,
    TacticSignal,
    load_dataset,
    run_backtest,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "backtest"


def _load(name):
    return load_dataset(FIXTURES / name)


class UptrendFixtureTests(unittest.TestCase):
    def setUp(self):
        bars, signals, symbol, _ = _load("sample_uptrend.json")
        self.report = run_backtest(
            bars, signals, BacktestConfig(holding_period_days=3), symbol=symbol
        )

    def test_provenance_flags(self):
        self.assertTrue(self.report.research_only)
        self.assertEqual("disabled", self.report.broker_execution)
        self.assertFalse(self.report.data_is_real)
        self.assertEqual("fixture", self.report.input_source)
        self.assertEqual((), self.report.errors)

    def test_single_trade_exact_values(self):
        self.assertEqual(1, len(self.report.trades))
        t = self.report.trades[0]
        self.assertEqual("2024-01-02", t.entry_date)
        self.assertEqual(100.0, t.entry_price)
        self.assertEqual("2024-01-04", t.exit_date)
        self.assertEqual(114.0, t.exit_price)
        self.assertEqual("holding_period", t.exit_reason)
        self.assertEqual(3, t.holding_period_days)
        self.assertAlmostEqual(14.0, t.return_pct)
        self.assertTrue(t.win)
        self.assertAlmostEqual(0.0, t.max_drawdown_pct)


class MixedFixtureTests(unittest.TestCase):
    def setUp(self):
        bars, signals, symbol, _ = _load("sample_mixed.json")
        self.report = run_backtest(
            bars, signals, BacktestConfig(holding_period_days=2), symbol=symbol
        )

    def test_two_trades_one_win_one_loss(self):
        self.assertEqual(2, len(self.report.trades))
        win, loss = self.report.trades
        self.assertAlmostEqual(7.0, win.return_pct)
        self.assertTrue(win.win)
        self.assertAlmostEqual(0.0, win.max_drawdown_pct)
        self.assertAlmostEqual(-10.0, loss.return_pct)
        self.assertFalse(loss.win)
        self.assertAlmostEqual(-20.0, loss.max_drawdown_pct)

    def test_summary_metrics_correct(self):
        s = self.report.summary
        self.assertIsNotNone(s)
        self.assertEqual(2, s.trades)
        self.assertEqual(1, s.wins)
        self.assertEqual(1, s.losses)
        self.assertAlmostEqual(0.5, s.win_rate)
        self.assertAlmostEqual(-1.5, s.avg_return_pct)
        self.assertAlmostEqual(-3.7, s.cumulative_return_pct)  # 1.07 * 0.90 - 1
        self.assertAlmostEqual(2.0, s.avg_holding_period_days)
        self.assertAlmostEqual(-20.0, s.max_drawdown_pct)
        self.assertAlmostEqual(-1.5, s.expectancy_pct)


class ExitRuleTests(unittest.TestCase):
    def setUp(self):
        self.bars, self.signals, self.symbol, _ = _load("sample_mixed.json")

    def test_stop_loss_exit(self):
        # signal #2 enters at 100 on 2024-03-05; low 90 crosses a 5% stop (95).
        report = run_backtest(
            self.bars,
            [TacticSignal("2024-03-04", "MIX")],
            BacktestConfig(holding_period_days=2, stop_loss_pct=0.05),
            symbol=self.symbol,
        )
        t = report.trades[0]
        self.assertEqual("stop_loss", t.exit_reason)
        self.assertEqual("2024-03-05", t.exit_date)
        self.assertAlmostEqual(95.0, t.exit_price)
        self.assertAlmostEqual(-5.0, t.return_pct)
        self.assertEqual(1, t.holding_period_days)

    def test_take_profit_exit(self):
        # signal #1 enters at 100 on 2024-03-02; high 106 crosses a 5% target (105).
        report = run_backtest(
            self.bars,
            [TacticSignal("2024-03-01", "MIX")],
            BacktestConfig(holding_period_days=2, take_profit_pct=0.05),
            symbol=self.symbol,
        )
        t = report.trades[0]
        self.assertEqual("take_profit", t.exit_reason)
        self.assertAlmostEqual(105.0, t.exit_price)
        self.assertAlmostEqual(5.0, t.return_pct)

    def test_stop_assumed_hit_before_target_when_both_crossed_in_same_bar(self):
        # Conservative intrabar ordering: the entry bar crosses BOTH the 5% stop
        # (low 90 <= 95) and the 5% target (high 110 >= 105); the stop must win.
        bars = [
            PriceBar("2024-02-01", 100, 101, 99, 100),
            PriceBar("2024-02-02", 100, 110, 90, 100),
            PriceBar("2024-02-03", 100, 102, 98, 101),
        ]
        report = run_backtest(
            bars,
            [TacticSignal("2024-02-01", "X")],
            BacktestConfig(holding_period_days=3, take_profit_pct=0.05, stop_loss_pct=0.05),
            symbol="X",
        )
        t = report.trades[0]
        self.assertEqual("stop_loss", t.exit_reason)
        self.assertEqual("2024-02-02", t.exit_date)
        self.assertAlmostEqual(95.0, t.exit_price)
        self.assertAlmostEqual(-5.0, t.return_pct)
        self.assertEqual(1, t.holding_period_days)

    def test_end_of_data_exit_when_holding_period_extends_past_series(self):
        # Uptrend fixture has 6 bars; signal on 2024-01-04 enters 2024-01-05 at
        # the open (114). A 5-bar hold extends past the data, so the trade exits
        # at the final close (117) and is labelled end_of_data, not holding_period.
        bars, _, symbol, _ = _load("sample_uptrend.json")
        report = run_backtest(
            bars,
            [TacticSignal("2024-01-04", "AAA")],
            BacktestConfig(holding_period_days=5),
            symbol=symbol,
        )
        t = report.trades[0]
        self.assertEqual("end_of_data", t.exit_reason)
        self.assertEqual("2024-01-05", t.entry_date)
        self.assertAlmostEqual(114.0, t.entry_price)
        self.assertEqual("2024-01-06", t.exit_date)
        self.assertAlmostEqual(117.0, t.exit_price)
        self.assertEqual(2, t.holding_period_days)
        self.assertAlmostEqual(2.631579, t.return_pct)
        self.assertAlmostEqual(-1.754386, t.max_drawdown_pct)


class DeterminismTests(unittest.TestCase):
    def test_repeated_runs_are_identical(self):
        bars, signals, symbol, _ = _load("sample_mixed.json")
        cfg = BacktestConfig(holding_period_days=2)
        r1 = run_backtest(bars, signals, cfg, symbol=symbol)
        r2 = run_backtest(bars, signals, cfg, symbol=symbol)
        self.assertEqual(bt.report_to_dict(r1), bt.report_to_dict(r2))


class FailClosedTests(unittest.TestCase):
    def _good_bars(self):
        return [
            PriceBar("2024-01-01", 100, 101, 99, 100),
            PriceBar("2024-01-02", 100, 110, 100, 108),
            PriceBar("2024-01-03", 108, 112, 106, 110),
        ]

    def test_negative_price_fails_closed(self):
        bars = self._good_bars()
        bars[1] = PriceBar("2024-01-02", -100, 110, 100, 108)
        report = run_backtest(bars, [TacticSignal("2024-01-01", "X")], symbol="X")
        self.assertFalse(report.ok)
        self.assertEqual((), report.trades)
        self.assertIsNone(report.summary)
        self.assertFalse(report.data_is_real)

    def test_non_increasing_dates_fail_closed(self):
        bars = self._good_bars()
        bars[2] = PriceBar("2024-01-02", 108, 112, 106, 110)  # duplicate date
        report = run_backtest(bars, [TacticSignal("2024-01-01", "X")], symbol="X")
        self.assertFalse(report.ok)
        self.assertTrue(any("strictly increasing" in e for e in report.errors))

    def test_close_outside_high_low_fails_closed(self):
        bars = self._good_bars()
        bars[0] = PriceBar("2024-01-01", 100, 101, 99, 130)  # close above high
        report = run_backtest(bars, [TacticSignal("2024-01-01", "X")], symbol="X")
        self.assertFalse(report.ok)

    def test_empty_bars_fail_closed(self):
        report = run_backtest([], [TacticSignal("2024-01-01", "X")], symbol="X")
        self.assertFalse(report.ok)
        self.assertIn("no price bars provided", report.errors)

    def test_invalid_data_forces_data_is_real_false_even_if_caller_asserts_true(self):
        bars = self._good_bars()
        bars[1] = PriceBar("2024-01-02", 100, 90, 100, 108)  # high < low
        report = run_backtest(
            bars, [TacticSignal("2024-01-01", "X")], symbol="X", data_is_real=True
        )
        self.assertFalse(report.ok)
        self.assertFalse(report.data_is_real)


class SignalHandlingTests(unittest.TestCase):
    def test_signal_on_last_bar_is_skipped(self):
        bars, _, symbol, _ = _load("sample_uptrend.json")
        report = run_backtest(
            bars, [TacticSignal("2024-01-06", "AAA")], symbol=symbol
        )
        self.assertEqual((), report.trades)
        self.assertTrue(any("no entry bar" in s for s in report.skipped))

    def test_symbol_mismatch_is_skipped(self):
        bars, _, symbol, _ = _load("sample_uptrend.json")
        report = run_backtest(
            bars, [TacticSignal("2024-01-01", "ZZZ")], symbol=symbol
        )
        self.assertEqual((), report.trades)
        self.assertTrue(any("!= series symbol" in s for s in report.skipped))


class SetupLabelTests(unittest.TestCase):
    """NEXT-015 follow-up: per-setup / strategy labels with fail-closed UNKNOWN."""

    def setUp(self):
        bars, signals, symbol, _ = _load("sample_setups.json")
        self.report = run_backtest(
            bars, signals, BacktestConfig(holding_period_days=2), symbol=symbol
        )

    def test_known_labels_are_assigned_and_normalized(self):
        self.assertEqual(4, len(self.report.trades))
        labels = [t.setup_type for t in self.report.trades]
        # Two explicit TREND_PULLBACK, one lowercase rsi_cross_up normalized
        # to uppercase, and one unlabeled signal failing closed to UNKNOWN.
        self.assertEqual(
            ["TREND_PULLBACK", "TREND_PULLBACK", "RSI_CROSS_UP", "UNKNOWN"], labels
        )
        self.assertEqual((), self.report.notes)  # nothing unrecognized in fixture

    def test_unrecognized_label_fails_closed_to_unknown_with_note(self):
        bars, _, symbol, _ = _load("sample_setups.json")
        report = run_backtest(
            bars,
            [bt.TacticSignal("2024-05-01", "SET", setup_type="MYSTERY_SETUP")],
            BacktestConfig(holding_period_days=2),
            symbol=symbol,
        )
        self.assertEqual(1, len(report.trades))
        self.assertEqual("UNKNOWN", report.trades[0].setup_type)
        self.assertEqual(["UNKNOWN"], list(report.summary_by_setup))
        self.assertTrue(any("MYSTERY_SETUP" in n and "UNKNOWN" in n for n in report.notes))

    def test_normalize_setup_label_table(self):
        cases = [
            ("TREND_PULLBACK", ("TREND_PULLBACK", True)),
            ("  breakout  ", ("BREAKOUT", True)),
            ("oversold_rebound", ("OVERSOLD_REBOUND", True)),
            ("TREND_CONTINUATION", ("TREND_CONTINUATION", True)),
            ("UNKNOWN", ("UNKNOWN", True)),
            ("", ("UNKNOWN", True)),
            (None, ("UNKNOWN", True)),
            ("DIP_BUY", ("UNKNOWN", False)),       # not a NovaBotV2 setup family
            ("MYSTERY_SETUP", ("UNKNOWN", False)),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, bt.normalize_setup_label(raw))

    def test_summary_metrics_are_grouped_per_label(self):
        by_setup = self.report.summary_by_setup
        self.assertEqual(["RSI_CROSS_UP", "TREND_PULLBACK", "UNKNOWN"], list(by_setup))

        tp = by_setup["TREND_PULLBACK"]  # +10% win and -10% loss
        self.assertEqual(2, tp.trades)
        self.assertEqual(1, tp.wins)
        self.assertEqual(1, tp.losses)
        self.assertAlmostEqual(0.5, tp.win_rate)
        self.assertAlmostEqual(0.0, tp.avg_return_pct)
        self.assertAlmostEqual(-1.0, tp.cumulative_return_pct)  # 1.10 * 0.90 - 1
        self.assertAlmostEqual(-13.636364, tp.max_drawdown_pct)

        rsi = by_setup["RSI_CROSS_UP"]  # single +9% win
        self.assertEqual(1, rsi.trades)
        self.assertAlmostEqual(1.0, rsi.win_rate)
        self.assertAlmostEqual(9.0, rsi.avg_return_pct)
        self.assertAlmostEqual(9.0, rsi.expectancy_pct)
        self.assertAlmostEqual(-1.010101, rsi.max_drawdown_pct)

        unknown = by_setup["UNKNOWN"]  # single -2% loss (unlabeled signal)
        self.assertEqual(1, unknown.trades)
        self.assertAlmostEqual(0.0, unknown.win_rate)
        self.assertAlmostEqual(-2.0, unknown.avg_return_pct)
        self.assertAlmostEqual(-2.803738, unknown.max_drawdown_pct)

    def test_per_label_trades_sum_to_overall_summary(self):
        overall = self.report.summary
        self.assertIsNotNone(overall)
        self.assertEqual(
            overall.trades,
            sum(s.trades for s in self.report.summary_by_setup.values()),
        )
        self.assertEqual(
            overall.wins,
            sum(s.wins for s in self.report.summary_by_setup.values()),
        )
        self.assertEqual(4, overall.trades)
        self.assertAlmostEqual(1.75, overall.avg_return_pct)  # (10 - 10 + 9 - 2) / 4
        self.assertAlmostEqual(5.7518, overall.cumulative_return_pct)  # 1.1*0.9*1.09*0.98 - 1

    def test_failed_closed_report_has_empty_setup_summary(self):
        report = run_backtest(
            [], [bt.TacticSignal("2024-05-01", "SET", setup_type="TREND_PULLBACK")], symbol="SET"
        )
        self.assertFalse(report.ok)
        self.assertEqual({}, report.summary_by_setup)

    def test_labeled_runs_are_deterministic(self):
        bars, signals, symbol, _ = _load("sample_setups.json")
        cfg = BacktestConfig(holding_period_days=2)
        r1 = run_backtest(bars, signals, cfg, symbol=symbol)
        r2 = run_backtest(bars, signals, cfg, symbol=symbol)
        self.assertEqual(bt.report_to_dict(r1), bt.report_to_dict(r2))

    def test_render_includes_per_setup_section_and_sample_size_warning(self):
        text = bt.render_report_text(self.report)
        self.assertIn("summary by setup (small samples are NOT evidence of edge):", text)
        self.assertIn("TREND_PULLBACK: trades=2", text)
        self.assertIn("RSI_CROSS_UP: trades=1", text)
        self.assertIn("UNKNOWN: trades=1", text)
        self.assertIn("setup=TREND_PULLBACK", text)


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(bt.__file__).read_text(encoding="utf-8")
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
            "nova_koopbot",
            "nova_verkoopbot",
            "workflow.nova_scheduler",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_module_does_not_import_novabotv2_runtime(self):
        source = Path(bt.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import core.nova", source)
        self.assertNotIn("from core import nova", source)


if __name__ == "__main__":
    unittest.main()
