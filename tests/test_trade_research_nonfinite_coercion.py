"""Non-finite fail-closed coverage for the trade / research numeric coercion.

Pure stdlib-unittest (no pytest) so it runs broker-free under
``python -S -m unittest``. The repo's existing test_nova_botv2_trade_adapter.py
and test_pattern_outcome_bridge.py modules are pytest-function style (they take
the ``tmp_path`` fixture) and are not collected by unittest, so this regression
lives in a separate module.

Regression: both ``_to_float`` helpers guarded only NaN (``f == f``), letting
+-Infinity leak. In the trade adapter that inf reached realized_pnl (via
_first_pnl), poisoning the analytics total_pnl sum and making _derive_outcome
misclassify (inf > 0 -> WIN). Both helpers now require math.isfinite.
"""
from __future__ import annotations

import unittest

from adapters.nova_botv2_trade_adapter import (
    _derive_outcome,
    _first_pnl,
    _to_float as trade_to_float,
)
from research.pattern_outcome_bridge import _to_float as pattern_to_float
from core.tactic_event import Outcome


class TestTradeAdapterToFloatFailsClosed(unittest.TestCase):
    def test_non_finite_returns_none(self):
        for bad in (float("inf"), float("-inf"), float("nan"), "Infinity", "-Infinity"):
            self.assertIsNone(trade_to_float(bad), f"{bad!r} should coerce to None")

    def test_valid_values_preserved(self):
        self.assertEqual(trade_to_float("2.5"), 2.5)
        self.assertEqual(trade_to_float(-3), -3.0)
        self.assertIsNone(trade_to_float(None))
        self.assertIsNone(trade_to_float(""))

    def test_infinite_pnl_field_does_not_leak_or_misclassify(self):
        # inf in a pnl field -> _first_pnl None -> outcome PENDING (not WIN)
        self.assertIsNone(_first_pnl({"netto_pnl": float("inf")}))
        self.assertEqual(
            _derive_outcome(_first_pnl({"netto_pnl": float("inf")})), Outcome.PENDING
        )
        # a finite pnl still classifies normally
        self.assertEqual(_derive_outcome(_first_pnl({"netto_pnl": 5.0})), Outcome.WIN)


class TestPatternBridgeToFloatFailsClosed(unittest.TestCase):
    def test_non_finite_returns_none(self):
        for bad in (float("inf"), float("-inf"), float("nan"), "Infinity"):
            self.assertIsNone(pattern_to_float(bad), f"{bad!r} should coerce to None")

    def test_valid_values_preserved(self):
        self.assertEqual(pattern_to_float("3.0"), 3.0)
        self.assertEqual(pattern_to_float(1), 1.0)
        self.assertIsNone(pattern_to_float(None))


if __name__ == "__main__":
    unittest.main()
