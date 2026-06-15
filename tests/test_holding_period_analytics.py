"""Tests for research/holding_period_analytics.py (TACTIC-HA-007).

Deterministic, synthetic-only, broker-free. Descriptive holding-period summary
that never fabricates timestamps, fails closed on no valid spans, stays
diagnostic-only, and propagates (never invents) data_is_real.
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent
from research import holding_period_analytics as hpa
from research.holding_period_analytics import (
    DEFAULT_MIN_SAMPLE,
    STATUS_DIAGNOSTIC,
    STATUS_INSUFFICIENT,
    build_holding_period_analysis,
)


def _trade(strategy_id, entry, exit_, n=0, event_type=EventType.TRADE_OUTCOME):
    md = {}
    if entry is not None:
        md["entry_time"] = entry
    if exit_ is not None:
        md["exit_time"] = exit_
    return TacticalEvent(
        source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
        event_type=event_type,
        strategy_id=strategy_id,
        timestamp=datetime(2026, 6, 1 + (n % 27), 12, 0, 0, tzinfo=timezone.utc),
        outcome=Outcome.WIN,
        metadata=md,
    )


class BasicStatsTests(unittest.TestCase):
    def setUp(self):
        # holding periods: 2 days, 4 days, 6 days -> mean 4, median 4
        self.events = [
            _trade("s", "2026-06-01T00:00:00", "2026-06-03T00:00:00", n=0),
            _trade("s", "2026-06-01T00:00:00", "2026-06-05T00:00:00", n=1),
            _trade("s", "2026-06-01T00:00:00", "2026-06-07T00:00:00", n=2),
        ]
        self.an = build_holding_period_analysis(self.events)

    def test_descriptive_stats(self):
        self.assertEqual(3, self.an.sample_count)
        self.assertAlmostEqual(4.0, self.an.mean_days)
        self.assertAlmostEqual(4.0, self.an.median_days)
        self.assertAlmostEqual(2.0, self.an.min_days)
        self.assertAlmostEqual(6.0, self.an.max_days)

    def test_per_strategy(self):
        s = self.an.by_strategy["s"]
        self.assertEqual(3, s.sample_count)
        self.assertAlmostEqual(4.0, s.mean_days)

    def test_diagnostic_only(self):
        self.assertTrue(self.an.diagnostic_only)
        self.assertTrue(any("DIAGNOSTIC_ONLY" in n for n in self.an.notes))


class FailClosedTests(unittest.TestCase):
    def test_empty_fails_closed(self):
        an = build_holding_period_analysis([])
        self.assertFalse(an.ok)
        self.assertEqual(("no events provided",), an.errors)

    def test_missing_timestamps_skipped_and_fail_closed_when_none_valid(self):
        events = [_trade("s", None, None, n=0), _trade("s", "2026-06-01T00:00:00", None, n=1)]
        an = build_holding_period_analysis(events)
        self.assertFalse(an.ok)
        self.assertTrue(any("no valid holding periods" in e for e in an.errors))
        self.assertEqual(2, an.skipped_missing)

    def test_invalid_span_skipped_never_negative(self):
        # exit before entry -> non-positive span -> skipped, never a negative duration
        events = [
            _trade("s", "2026-06-10T00:00:00", "2026-06-05T00:00:00", n=0),  # invalid
            _trade("s", "2026-06-01T00:00:00", "2026-06-04T00:00:00", n=1),  # valid 3d
        ]
        an = build_holding_period_analysis(events)
        self.assertEqual(1, an.sample_count)
        self.assertEqual(1, an.skipped_invalid_span)
        self.assertAlmostEqual(3.0, an.min_days)
        self.assertGreater(an.min_days, 0.0)

    def test_unparseable_timestamp_skipped(self):
        events = [
            _trade("s", "not-a-date", "2026-06-05T00:00:00", n=0),
            _trade("s", "2026-06-01T00:00:00", "2026-06-03T00:00:00", n=1),
        ]
        an = build_holding_period_analysis(events)
        self.assertEqual(1, an.sample_count)
        self.assertEqual(1, an.skipped_missing)

    def test_mismatched_tz_awareness_skipped(self):
        # naive entry, aware exit -> subtraction TypeError -> skipped invalid span
        events = [_trade("s", "2026-06-01T00:00:00", "2026-06-05T00:00:00+00:00", n=0)]
        an = build_holding_period_analysis(events)
        self.assertFalse(an.ok)
        self.assertEqual(1, an.skipped_invalid_span)


class ScopeAndProvenanceTests(unittest.TestCase):
    def test_non_outcome_events_ignored(self):
        events = [
            _trade("s", "2026-06-01T00:00:00", "2026-06-03T00:00:00", n=0),
            _trade("s", "2026-06-01T00:00:00", "2026-06-09T00:00:00", n=1,
                   event_type=EventType.RECOMMENDATION),  # ignored
        ]
        an = build_holding_period_analysis(events)
        self.assertEqual(1, an.sample_count)

    def test_accepts_datetime_objects(self):
        events = [
            _trade("s", datetime(2026, 6, 1, tzinfo=timezone.utc),
                   datetime(2026, 6, 6, tzinfo=timezone.utc), n=0),
        ]
        an = build_holding_period_analysis(events)
        self.assertEqual(1, an.sample_count)
        self.assertAlmostEqual(5.0, an.mean_days)

    def test_data_is_real_propagated_not_invented(self):
        events = [_trade("s", "2026-06-01T00:00:00", "2026-06-03T00:00:00", n=0)]
        self.assertFalse(build_holding_period_analysis(events).data_is_real)
        self.assertTrue(build_holding_period_analysis(events, data_is_real=True).data_is_real)


class SampleFloorTests(unittest.TestCase):
    def test_below_floor_insufficient(self):
        events = [_trade("s", "2026-06-01T00:00:00", "2026-06-03T00:00:00", n=i) for i in range(5)]
        an = build_holding_period_analysis(events)
        self.assertEqual(STATUS_INSUFFICIENT, an.status)
        self.assertIsNotNone(an.mean_days)

    def test_at_floor_diagnostic(self):
        events = [
            _trade("s", "2026-06-01T00:00:00", "2026-06-03T00:00:00", n=i)
            for i in range(DEFAULT_MIN_SAMPLE)
        ]
        an = build_holding_period_analysis(events)
        self.assertEqual(STATUS_DIAGNOSTIC, an.status)


class DeterminismTests(unittest.TestCase):
    def test_same_events_yield_equal_analysis(self):
        events = [
            _trade("s", "2026-06-01T00:00:00", f"2026-06-{3 + (i % 5):02d}T00:00:00", n=i)
            for i in range(10)
        ]
        self.assertEqual(
            build_holding_period_analysis(events),
            build_holding_period_analysis(events),
        )


class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(hpa.__file__).read_text(encoding="utf-8")
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
        runner = Path(hpa.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("holding_period_analytics", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
