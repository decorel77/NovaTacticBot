"""Tests for research/regime_strategy_fit.py (TACTIC-RA-003).

Deterministic, synthetic-only, broker-free. The fit matrix must withhold win
rates below the sample floor, stay diagnostic-only, fail closed on empty input
and unknown regimes, and propagate (never invent) ``data_is_real``.
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent
from research import regime_strategy_fit as rsf
from research.regime_strategy_fit import (
    MIN_SAMPLE,
    STATUS_DIAGNOSTIC,
    STATUS_INSUFFICIENT,
    RegimeStrategyFit,
    build_regime_strategy_fit,
)


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


class EmptyInputTests(unittest.TestCase):
    def test_empty_fails_closed(self):
        fit = build_regime_strategy_fit([])
        self.assertFalse(fit.ok)
        self.assertEqual(("no events provided",), fit.errors)
        self.assertEqual(STATUS_INSUFFICIENT, fit.status)
        self.assertFalse(fit.data_is_real)
        self.assertEqual({}, fit.cells)


class UnknownRegimeTests(unittest.TestCase):
    def test_none_and_unknown_regimes_collapse_to_unknown_bucket(self):
        events = [
            _outcome("momentum", None, Outcome.WIN, 0),
            _outcome("momentum", "WEIRD_REGIME", Outcome.LOSS, 1),
        ]
        fit = build_regime_strategy_fit(events)
        self.assertEqual((Regime.UNKNOWN,), fit.regimes)
        # No fabricated "WEIRD_REGIME" cell.
        self.assertNotIn("WEIRD_REGIME|momentum", fit.cells)
        self.assertIn(RegimeStrategyFit.cell_key(Regime.UNKNOWN, "momentum"), fit.cells)
        self.assertTrue(any("WEIRD_REGIME" in n for n in fit.notes))


class SampleFloorTests(unittest.TestCase):
    def test_win_rate_withheld_below_floor(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 5))
        cell = fit.cells[RegimeStrategyFit.cell_key(Regime.BULL, "momentum")]
        self.assertEqual(5, cell.sample_count)
        self.assertIsNone(cell.win_rate)
        self.assertEqual(STATUS_INSUFFICIENT, cell.win_rate_status)
        self.assertEqual(STATUS_INSUFFICIENT, cell.status)
        self.assertEqual(STATUS_INSUFFICIENT, fit.status)

    def test_win_rate_shown_at_floor_but_status_stays_diagnostic(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, MIN_SAMPLE))
        cell = fit.cells[RegimeStrategyFit.cell_key(Regime.BULL, "momentum")]
        self.assertEqual(MIN_SAMPLE, cell.sample_count)
        self.assertEqual(1.0, cell.win_rate)
        self.assertEqual("OK", cell.win_rate_status)
        # Crossing the floor lets a number show, but it is never a trusted edge.
        self.assertEqual(STATUS_DIAGNOSTIC, cell.status)
        self.assertEqual(STATUS_DIAGNOSTIC, fit.status)
        self.assertTrue(fit.diagnostic_only)

    def test_mixed_win_loss_rate_computed_at_floor(self):
        events = _wins("momentum", Regime.BEAR, 18) + [
            _outcome("momentum", Regime.BEAR, Outcome.LOSS, 18 + i) for i in range(12)
        ]
        fit = build_regime_strategy_fit(events)
        cell = fit.cells[RegimeStrategyFit.cell_key(Regime.BEAR, "momentum")]
        self.assertEqual(30, cell.sample_count)
        self.assertEqual(18, cell.wins)
        self.assertEqual(12, cell.losses)
        self.assertEqual(0.6, cell.win_rate)


class NonDecisiveTests(unittest.TestCase):
    def test_pending_and_recommendation_do_not_count_as_decisive(self):
        events = [
            _outcome("momentum", Regime.BULL, Outcome.PENDING, 0),
            TacticalEvent(
                source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
                event_type=EventType.RECOMMENDATION,
                strategy_id="momentum",
                regime=Regime.BULL,
            ),
        ]
        fit = build_regime_strategy_fit(events)
        cell = fit.cells[RegimeStrategyFit.cell_key(Regime.BULL, "momentum")]
        self.assertEqual(2, cell.total_events)
        self.assertEqual(0, cell.sample_count)  # neither is a decisive WIN/LOSS
        self.assertEqual(0, fit.total_decisive)


class ProvenanceTests(unittest.TestCase):
    def test_data_is_real_defaults_false(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 3))
        self.assertFalse(fit.data_is_real)

    def test_data_is_real_propagated_not_invented(self):
        fit = build_regime_strategy_fit(_wins("momentum", Regime.BULL, 3), data_is_real=True)
        self.assertTrue(fit.data_is_real)


class DeterminismTests(unittest.TestCase):
    def test_same_events_yield_equal_matrix(self):
        events = (
            _wins("momentum", Regime.BULL, 4)
            + _wins("mean_rev", Regime.BEAR, 3)
            + [_outcome("momentum", Regime.BULL, Outcome.LOSS, 9)]
        )
        self.assertEqual(
            build_regime_strategy_fit(events),
            build_regime_strategy_fit(events),
        )

    def test_regimes_and_strategies_sorted(self):
        events = (
            _wins("zeta", Regime.NORMAL, 1)
            + _wins("alpha", Regime.BULL, 1)
            + _wins("alpha", Regime.BEAR, 1)
        )
        fit = build_regime_strategy_fit(events)
        self.assertEqual((Regime.BEAR, Regime.BULL, Regime.NORMAL), fit.regimes)
        self.assertEqual(("alpha", "zeta"), fit.strategies)


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(rsf.__file__).read_text(encoding="utf-8")
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
        runner = Path(rsf.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("regime_strategy_fit", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
