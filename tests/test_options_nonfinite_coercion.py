"""Non-finite fail-closed coverage for the options adapters' numeric coercion.

Pure stdlib-unittest (no pytest / no pandas) so it runs broker-free under
``python -S -m unittest``. The repo's existing test_options_adapter.py /
test_nova_options_adapter.py modules import pytest, which is unavailable in the
broker-free env, so this regression lives in a separate module.

Regression: ``_to_float`` / ``_safe_float`` previously returned float(value)
for any parseable input, leaking a non-finite (NaN/+-Infinity, parsed by
json.loads from an upstream record) into TacticalEvent.expected_rr /
realized_pnl. Those fields are NOT range-checked at construction, so the
non-finite poisoned the analytics sums (total_pnl, avg_expected_rr,
avg_realized_pnl) downstream. Both helpers now fail closed to None.
"""
from __future__ import annotations

import math
import unittest

from adapters.options_adapter import _to_float
from adapters.nova_options_adapter import _safe_float
from core.tactic_analytics_engine import TacticAnalyticsEngine
from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent


class TestToFloatFailsClosed(unittest.TestCase):
    def test_non_finite_returns_none(self):
        for bad in (float("inf"), float("-inf"), float("nan"), "Infinity", "-Infinity", "NaN"):
            self.assertIsNone(_to_float(bad), f"{bad!r} should coerce to None")

    def test_valid_values_preserved(self):
        self.assertEqual(_to_float("1.5"), 1.5)
        self.assertEqual(_to_float(2), 2.0)
        self.assertEqual(_to_float(0), 0.0)
        self.assertIsNone(_to_float(None))
        self.assertIsNone(_to_float(""))


class TestSafeFloatFailsClosed(unittest.TestCase):
    def test_non_finite_returns_none(self):
        for bad in (float("inf"), float("-inf"), float("nan"), "Infinity", "NaN"):
            self.assertIsNone(_safe_float(bad), f"{bad!r} should coerce to None")

    def test_valid_values_preserved(self):
        self.assertEqual(_safe_float("3.2"), 3.2)
        self.assertEqual(_safe_float(4), 4.0)
        self.assertIsNone(_safe_float(None))
        self.assertIsNone(_safe_float(""))


class TestAnalyticsNotPoisonedByNonFinite(unittest.TestCase):
    """End-to-end: a non-finite record value can no longer reach the analytics
    sums via the coerced TacticalEvent fields."""

    def test_total_pnl_and_avgs_stay_finite_or_absent(self):
        ev = TacticalEvent(
            source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
            event_type=EventType.TRADE_OUTCOME,
            strategy_id="bull_spread",
            realized_pnl=_to_float(float("inf")),
            expected_rr=_to_float("Infinity"),
            outcome=Outcome.WIN,
        )
        # the coerced fields are now None, not inf
        self.assertIsNone(ev.realized_pnl)
        self.assertIsNone(ev.expected_rr)

        result = TacticAnalyticsEngine().run([ev])
        stats = result.strategy_stats["bull_spread"]
        # total_pnl stays at its finite default; avg_* are not poisoned with inf
        self.assertTrue(math.isfinite(stats.total_pnl))
        for avg in (stats.avg_expected_rr, getattr(stats, "avg_realized_pnl", None)):
            self.assertTrue(avg is None or math.isfinite(avg))


if __name__ == "__main__":
    unittest.main()
