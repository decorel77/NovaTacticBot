"""Tests for research/pnl_distribution.py (TACTIC-HA-006).

Deterministic, synthetic-only, broker-free. Descriptive realized-PnL distribution
that fails closed on no data, skips NaN, stays diagnostic-only, and propagates
(never invents) data_is_real.
"""
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent
from research import pnl_distribution as pnl
from research.pnl_distribution import (
    DEFAULT_MIN_SAMPLE,
    STATUS_DIAGNOSTIC,
    STATUS_INSUFFICIENT,
    build_pnl_distribution,
)


def _outcome(strategy_id, realized_pnl, outcome, regime="BULL", n=0):
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=EventType.TRADE_OUTCOME,
        strategy_id=strategy_id,
        timestamp=datetime(2026, 6, 1 + (n % 27), 12, 0, 0, tzinfo=timezone.utc),
        regime=regime,
        realized_pnl=realized_pnl,
        outcome=outcome,
    )


class BasicStatsTests(unittest.TestCase):
    def setUp(self):
        # pnls: 1.0, -1.0, 2.0, 0.0  -> mean 0.5, median 0.5, min -1, max 2
        self.events = [
            _outcome("covered_call", 1.0, Outcome.WIN, n=0),
            _outcome("covered_call", -1.0, Outcome.LOSS, n=1),
            _outcome("long_call", 2.0, Outcome.WIN, n=2),
            _outcome("long_call", 0.0, Outcome.BREAKEVEN, n=3),
        ]
        self.dist = build_pnl_distribution(self.events, bucket_count=3)

    def test_descriptive_stats(self):
        self.assertEqual(4, self.dist.sample_count)
        self.assertAlmostEqual(0.5, self.dist.mean_pnl)
        self.assertAlmostEqual(0.5, self.dist.median_pnl)
        self.assertEqual(-1.0, self.dist.min_pnl)
        self.assertEqual(2.0, self.dist.max_pnl)
        self.assertEqual(2.0, self.dist.total_pnl)
        self.assertIsNotNone(self.dist.stdev_pnl)

    def test_win_loss_split(self):
        self.assertEqual(2, self.dist.wins)
        self.assertEqual(1, self.dist.losses)
        self.assertEqual(1, self.dist.breakevens)

    def test_buckets_sum_to_sample(self):
        self.assertEqual(self.dist.sample_count, sum(b.count for b in self.dist.buckets))

    def test_per_strategy_summary(self):
        cc = self.dist.by_strategy["covered_call"]
        self.assertEqual(2, cc.sample_count)
        self.assertEqual(1, cc.wins)
        self.assertEqual(1, cc.losses)
        self.assertAlmostEqual(0.0, cc.mean_pnl)
        self.assertAlmostEqual(0.0, cc.total_pnl)

    def test_diagnostic_only_flag(self):
        self.assertTrue(self.dist.diagnostic_only)
        self.assertTrue(any("DIAGNOSTIC_ONLY" in n for n in self.dist.notes))


class FailClosedTests(unittest.TestCase):
    def test_empty_fails_closed(self):
        d = build_pnl_distribution([])
        self.assertFalse(d.ok)
        self.assertEqual(("no events provided",), d.errors)
        self.assertEqual(STATUS_INSUFFICIENT, d.status)
        self.assertIsNone(d.mean_pnl)

    def test_no_realized_pnl_fails_closed(self):
        events = [_outcome("covered_call", None, Outcome.WIN, n=0)]
        d = build_pnl_distribution(events)
        self.assertFalse(d.ok)
        self.assertTrue(any("no realized PnL" in e for e in d.errors))
        self.assertEqual(0, d.sample_count)

    def test_nan_pnl_skipped(self):
        events = [
            _outcome("covered_call", 1.0, Outcome.WIN, n=0),
            _outcome("covered_call", float("nan"), Outcome.WIN, n=1),
            _outcome("covered_call", 3.0, Outcome.WIN, n=2),
        ]
        d = build_pnl_distribution(events)
        self.assertEqual(2, d.sample_count)  # NaN skipped, never counted
        self.assertAlmostEqual(2.0, d.mean_pnl)


class SampleFloorTests(unittest.TestCase):
    def test_below_floor_is_insufficient_but_stats_present(self):
        events = [_outcome("s", 1.0, Outcome.WIN, n=i) for i in range(5)]
        d = build_pnl_distribution(events)
        self.assertEqual(STATUS_INSUFFICIENT, d.status)
        self.assertIsNotNone(d.mean_pnl)  # descriptive facts still shown
        self.assertTrue(any("INSUFFICIENT_SAMPLE" in n for n in d.notes))

    def test_at_floor_is_diagnostic(self):
        events = [_outcome("s", 1.0, Outcome.WIN, n=i) for i in range(DEFAULT_MIN_SAMPLE)]
        d = build_pnl_distribution(events)
        self.assertEqual(STATUS_DIAGNOSTIC, d.status)


class DegenerateAndProvenanceTests(unittest.TestCase):
    def test_single_value_degenerate_bucket(self):
        events = [_outcome("s", 2.5, Outcome.WIN, n=0)]
        d = build_pnl_distribution(events)
        self.assertEqual(1, len(d.buckets))
        self.assertEqual(d.min_pnl, d.max_pnl)
        self.assertIsNone(d.stdev_pnl)  # stdev needs >= 2 values

    def test_data_is_real_defaults_false(self):
        d = build_pnl_distribution([_outcome("s", 1.0, Outcome.WIN, n=0)])
        self.assertFalse(d.data_is_real)

    def test_data_is_real_propagated_not_invented(self):
        d = build_pnl_distribution([_outcome("s", 1.0, Outcome.WIN, n=0)], data_is_real=True)
        self.assertTrue(d.data_is_real)

    def test_non_outcome_events_ignored(self):
        events = [
            _outcome("s", 1.0, Outcome.WIN, n=0),
            TacticalEvent(
                source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
                event_type=EventType.RECOMMENDATION,
                strategy_id="s",
                realized_pnl=999.0,  # must be ignored: not a TRADE_OUTCOME
            ),
        ]
        d = build_pnl_distribution(events)
        self.assertEqual(1, d.sample_count)
        self.assertEqual(1.0, d.max_pnl)


class DeterminismTests(unittest.TestCase):
    def test_same_events_yield_equal_distribution(self):
        events = [_outcome("s", float(i % 5) - 2.0, Outcome.WIN, n=i) for i in range(20)]
        self.assertEqual(build_pnl_distribution(events), build_pnl_distribution(events))


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(pnl.__file__).read_text(encoding="utf-8")
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
        runner = Path(pnl.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("pnl_distribution", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
