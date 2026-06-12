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
