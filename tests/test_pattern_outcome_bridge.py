"""Tests for the offline trade-outcome -> diagnostic bridge (NEXT-PR-003).

Deterministic, fixture-driven, broker-free. No network, no live path. Conclusions
stay DIAGNOSTIC_ONLY / INSUFFICIENT_SAMPLE on small samples; no OHLCV bars are
ever fabricated from trade outcomes.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research import pattern_outcome_bridge as bridge
from research import pattern_report as rep
from research.pattern_outcome_bridge import (
    DEFAULT_MIN_SAMPLE,
    DEFAULT_TITLE,
    STATUS_DIAGNOSTIC,
    STATUS_INSUFFICIENT,
    OutcomeRecord,
    build_diagnostic_markdown,
    load_outcomes_dataset,
    outcomes_from_events,
    summarize_outcomes,
    to_scan_report,
)
from research.pattern_recognition import PATTERN_NAMES

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "patterns"
FIXED_TIME = "2026-06-15T00:00:00+00:00"
PRICE_DETECTOR_NAMES = frozenset(n for n in PATTERN_NAMES if n != "win_loss_clusters")


def _summ(fixture, **kw):
    records, src, _ = load_outcomes_dataset(FIXTURES / fixture)
    return summarize_outcomes(records, input_source=src, **kw)


class _FakeEvent:
    """Duck-typed stand-in for a TacticalEvent from the read-only adapter."""

    def __init__(self, event_type, outcome, strategy_id, metadata, timestamp=None):
        self.event_type = event_type
        self.outcome = outcome
        self.strategy_id = strategy_id
        self.metadata = metadata
        self.timestamp = timestamp


def _run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = bridge.main(argv)
    return rc, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# Insufficient sample stays DIAGNOSTIC_ONLY / INSUFFICIENT_SAMPLE
# --------------------------------------------------------------------------- #
class InsufficientSampleTests(unittest.TestCase):
    def setUp(self):
        self.diag = _summ("outcomes_bridge_insufficient.json")

    def test_status_insufficient(self):
        self.assertEqual(STATUS_INSUFFICIENT, self.diag.status)
        self.assertTrue(self.diag.diagnostic_only)

    def test_win_rate_withheld_below_threshold(self):
        s = self.diag.by_setup["BREAKOUT"]
        self.assertEqual(4, s.sample_count)
        self.assertIsNone(s.win_rate)
        self.assertEqual(STATUS_INSUFFICIENT, s.win_rate_status)
        self.assertIsNone(s.average_return_pct)

    def test_no_bars_fabricated(self):
        self.assertEqual(0, self.diag.bars_analysed)
        self.assertFalse(self.diag.ohlcv_used)

    def test_default_threshold_is_30(self):
        self.assertEqual(30, DEFAULT_MIN_SAMPLE)
        self.assertEqual(30, self.diag.min_sample)


# --------------------------------------------------------------------------- #
# data_is_real is propagated, never invented
# --------------------------------------------------------------------------- #
class DataIsRealPropagationTests(unittest.TestCase):
    def test_synthetic_stays_false(self):
        diag = _summ("outcomes_bridge_clusters.json")
        self.assertFalse(diag.data_is_real)
        for s in diag.by_setup.values():
            self.assertFalse(s.data_is_real)

    def test_real_like_propagates_true_but_still_insufficient(self):
        diag = _summ("outcomes_bridge_reallike.json")
        self.assertTrue(diag.data_is_real)  # all records flagged real -> propagated
        self.assertEqual(STATUS_INSUFFICIENT, diag.status)  # but sample < 30
        self.assertTrue(diag.by_setup["TREND_PULLBACK"].data_is_real)

    def test_mixed_real_flags_fail_closed_to_false(self):
        records = [
            OutcomeRecord("2024-01-01", "BREAKOUT", "WIN", 1.0, True),
            OutcomeRecord("2024-01-02", "BREAKOUT", "LOSS", -1.0, False),
        ]
        diag = summarize_outcomes(records)
        self.assertFalse(diag.data_is_real)  # one synthetic record taints the group
        self.assertFalse(diag.by_setup["BREAKOUT"].data_is_real)

    def test_events_propagate_metadata_real_flag(self):
        events = [
            _FakeEvent("TRADE_OUTCOME", "WIN", "TREND_PULLBACK",
                       {"data_is_real": True, "pnl_pct": 2.0, "setup_type": "TREND_PULLBACK"}),
            _FakeEvent("RECOMMENDATION", "PENDING", "X", {}),  # ignored (not an outcome)
        ]
        records = outcomes_from_events(events)
        self.assertEqual(1, len(records))
        self.assertTrue(records[0].data_is_real)
        self.assertEqual("WIN", records[0].outcome)


# --------------------------------------------------------------------------- #
# No OHLCV/price patterns fabricated from outcomes
# --------------------------------------------------------------------------- #
class NoFabricationTests(unittest.TestCase):
    def test_scan_report_has_no_price_signals_and_zero_bars(self):
        diag = _summ("outcomes_bridge_clusters.json")
        report = to_scan_report(diag)
        self.assertEqual(0, report.bars_analysed)
        self.assertEqual(1, len(report.signals))
        self.assertEqual("trade_outcome_clusters", report.signals[0].pattern_name)
        names = {s.pattern_name for s in report.signals}
        self.assertEqual(set(), names & PRICE_DETECTOR_NAMES)

    def test_markdown_states_no_bars(self):
        md = build_diagnostic_markdown(_summ("outcomes_bridge_clusters.json"), generated_at=FIXED_TIME)
        self.assertIn("ohlcv_bars_used:** 0", md)
        self.assertIn("no price bars were read or fabricated", md)


# --------------------------------------------------------------------------- #
# Setup grouping + longest clusters
# --------------------------------------------------------------------------- #
class GroupingAndClusterTests(unittest.TestCase):
    def setUp(self):
        self.diag = _summ("outcomes_bridge_clusters.json")

    def test_setup_grouping_sorted_and_normalized(self):
        self.assertEqual(("RSI_CROSS_UP", "TREND_PULLBACK"), self.diag.setup_labels)
        tp = self.diag.by_setup["TREND_PULLBACK"]
        self.assertEqual(4, tp.sample_count)
        self.assertEqual(3, tp.win_count)
        self.assertEqual(1, tp.loss_count)
        rsi = self.diag.by_setup["RSI_CROSS_UP"]  # lowercase in fixture, normalized
        self.assertEqual(5, rsi.sample_count)
        self.assertEqual(1, rsi.win_count)
        self.assertEqual(4, rsi.loss_count)

    def test_longest_clusters(self):
        tp = self.diag.by_setup["TREND_PULLBACK"]
        self.assertEqual(3, tp.longest_win_cluster)
        self.assertEqual(1, tp.longest_loss_cluster)
        rsi = self.diag.by_setup["RSI_CROSS_UP"]
        self.assertEqual(1, rsi.longest_win_cluster)
        self.assertEqual(2, rsi.longest_loss_cluster)

    def test_breakeven_resets_both_streaks(self):
        records = [
            OutcomeRecord("2024-01-01", "BREAKOUT", "WIN"),
            OutcomeRecord("2024-01-02", "BREAKOUT", "BREAKEVEN"),
            OutcomeRecord("2024-01-03", "BREAKOUT", "WIN"),
            OutcomeRecord("2024-01-04", "BREAKOUT", "WIN"),
        ]
        diag = summarize_outcomes(records)
        s = diag.by_setup["BREAKOUT"]
        self.assertEqual(2, s.longest_win_cluster)  # the breakeven splits the runs
        self.assertEqual(1, s.breakeven_count)


# --------------------------------------------------------------------------- #
# Missing / unknown setup labels fail closed to UNKNOWN
# --------------------------------------------------------------------------- #
class MissingLabelTests(unittest.TestCase):
    def setUp(self):
        self.diag = _summ("outcomes_bridge_missing_label.json")

    def test_all_collapse_to_unknown(self):
        self.assertEqual(("UNKNOWN",), self.diag.setup_labels)
        self.assertEqual(3, self.diag.by_setup["UNKNOWN"].sample_count)

    def test_unrecognized_label_noted_not_attributed(self):
        self.assertTrue(any("MYSTERY" in n for n in self.diag.notes))
        # MYSTERY never becomes a real setup family.
        self.assertNotIn("MYSTERY", self.diag.by_setup)


# --------------------------------------------------------------------------- #
# Threshold upper branch (>= min_sample) — still DIAGNOSTIC_ONLY, never trusted
# --------------------------------------------------------------------------- #
class ThresholdTests(unittest.TestCase):
    def _real_wins(self, n):
        return [
            OutcomeRecord(f"2024-07-{i + 1:02d}", "TREND_PULLBACK", "WIN", 1.0, True)
            for i in range(n)
        ]

    def test_at_threshold_win_rate_appears_but_status_stays_diagnostic(self):
        diag = summarize_outcomes(self._real_wins(30), min_sample=30)
        s = diag.by_setup["TREND_PULLBACK"]
        self.assertEqual(1.0, s.win_rate)
        self.assertEqual("OK", s.win_rate_status)
        self.assertEqual(1.0, s.average_return_pct)
        self.assertEqual(STATUS_DIAGNOSTIC, diag.status)  # diagnostic, never "trusted edge"

    def test_below_threshold_win_rate_withheld(self):
        diag = summarize_outcomes(self._real_wins(29), min_sample=30)
        self.assertIsNone(diag.by_setup["TREND_PULLBACK"].win_rate)
        self.assertEqual(STATUS_INSUFFICIENT, diag.status)


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #
class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.md = build_diagnostic_markdown(
            _summ("outcomes_bridge_insufficient.json"), generated_at=FIXED_TIME
        )

    def test_metadata_and_banners(self):
        self.assertIn(f"# {DEFAULT_TITLE}", self.md)
        self.assertIn(f"- **generated_at:** {FIXED_TIME}", self.md)
        self.assertIn("- **research_only:** true", self.md)
        self.assertIn("- **diagnostic_only:** true", self.md)
        self.assertIn("- **status:** INSUFFICIENT_SAMPLE", self.md)
        self.assertIn("- **data_is_real:** false", self.md)
        self.assertIn("**INSUFFICIENT_SAMPLE.**", self.md)

    def test_per_setup_table_withholds_win_rate(self):
        self.assertIn("## Per-setup outcome summary", self.md)
        self.assertTrue(
            any("BREAKOUT" in ln and "INSUFFICIENT_SAMPLE" in ln for ln in self.md.splitlines())
        )

    def test_disclaimer_and_sections(self):
        self.assertIn("Not trading advice", self.md)
        self.assertIn("## What this is NOT", self.md)
        self.assertIn("## Future integration", self.md)

    def test_no_action_wording(self):
        low = self.md.lower()
        for token in ["place order", "submit order", "cancel order", "market order",
                      "limit order", "go long", "go short", "execute trade", " buy ", " sell "]:
            with self.subTest(token=token):
                self.assertNotIn(token, low)


# --------------------------------------------------------------------------- #
# PatternScanReport-compatible path renders via pattern_report
# --------------------------------------------------------------------------- #
class ScanReportCompatTests(unittest.TestCase):
    def test_renders_via_pattern_report(self):
        diag = _summ("outcomes_bridge_insufficient.json")
        md = rep.build_markdown_report(to_scan_report(diag), generated_at=FIXED_TIME)
        self.assertIn("trade_outcome_clusters", md)
        self.assertIn("| bars_analysed | 0 |", md)
        self.assertIn("INSUFFICIENT_SAMPLE", md)  # carried as the signal's fail-closed reason


# --------------------------------------------------------------------------- #
# CLI (offline, synthetic by default)
# --------------------------------------------------------------------------- #
class CliTests(unittest.TestCase):
    def test_cli_returns_zero_and_marks_insufficient(self):
        rc, out, _ = _run_cli([str(FIXTURES / "outcomes_bridge_clusters.json")])
        self.assertEqual(0, rc)
        self.assertIn(DEFAULT_TITLE, out)
        self.assertIn("INSUFFICIENT_SAMPLE", out)
        self.assertIn("- **data_is_real:** false", out)  # CLI never asserts realness

    def test_cli_scan_report_flag(self):
        rc, out, _ = _run_cli([str(FIXTURES / "outcomes_bridge_clusters.json"), "--scan-report"])
        self.assertEqual(0, rc)
        self.assertIn("trade_outcome_clusters", out)

    def test_cli_explicit_empty_nova_dir_is_read_only_and_finds_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = _run_cli(["--nova-botv2-dir", d])
        self.assertEqual(1, rc)  # no records -> fail closed
        self.assertIn("READ-ONLY", err)

    def test_cli_requires_a_source(self):
        with self.assertRaises(SystemExit):
            _run_cli([])


# --------------------------------------------------------------------------- #
# Safety: no broker / network / runtime imports; not wired into the runner
# --------------------------------------------------------------------------- #
class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(bridge.__file__).read_text(encoding="utf-8")
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
            "nova_koopbot",
            "nova_verkoopbot",
            "workflow.nova_scheduler",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_not_wired_into_runner(self):
        runner = Path(bridge.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("pattern_outcome_bridge", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
