"""Consolidated fail-closed regression contract for the pure tactic analytics.

A single cross-module tripwire over the three pure, broker-free analytics
entrypoints — it pins that empty / malformed / non-finite inputs never produce a
fabricated statistic and never raise:

* ``build_pnl_distribution`` → 0 sample_count, fail-closed status;
* ``build_holding_period_analysis`` → 0 sample_count, ``mean_days`` None;
* ``compute_strategy_correlation`` → ``computed=False``, ``correlation=None``.

These behaviours are already covered per-module; this is the canonical
cross-cutting regression guard so a future change cannot loosen one of them.

Hermeticity: imports only the pure analytics modules + stdlib. No broker, no
network, no I/O, no runtime read/write. Broker-free under
``python -S -m unittest tests.test_tactic_analytics_failclosed_contract``.
"""
from __future__ import annotations

import unittest

from research.pnl_distribution import build_pnl_distribution
from research.holding_period_analytics import build_holding_period_analysis
from core.strategy_correlation import compute_strategy_correlation

# Event lists that contain no usable trade outcome.
_BAD_EVENT_LISTS = ([], [None], ["x"], [{}], [{"type": "GARBAGE"}], [None, "x", {}])


class PnlDistributionFailClosedTest(unittest.TestCase):
    def test_no_usable_data_never_fabricates_a_sample(self) -> None:
        for events in _BAD_EVENT_LISTS:
            with self.subTest(events=events):
                result = build_pnl_distribution(events, min_sample=30)
                self.assertEqual(result.sample_count, 0)
                self.assertEqual(result.wins + result.losses + result.breakevens, 0)


class HoldingPeriodFailClosedTest(unittest.TestCase):
    def test_no_usable_data_yields_none_metrics(self) -> None:
        for events in _BAD_EVENT_LISTS:
            with self.subTest(events=events):
                result = build_holding_period_analysis(events, min_sample=30)
                self.assertEqual(result.sample_count, 0)
                self.assertIsNone(result.mean_days)


class StrategyCorrelationFailClosedTest(unittest.TestCase):
    def test_empty_or_malformed_streams_compute_nothing(self) -> None:
        for a, b in (([], []), ([None, "x"], [{}]), ([], [None])):
            with self.subTest(a=a, b=b):
                result = compute_strategy_correlation(a, b)
                self.assertFalse(result.computed)
                self.assertIsNone(result.correlation)


if __name__ == "__main__":
    unittest.main()
