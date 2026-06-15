"""Tests for the offline pattern recognition report layer (NEXT-PR-002).

Deterministic, fixture-driven, broker-free. No network, no live path. The report
layer only formats a PatternScanReport; it adds no capability and asserts no
realness.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research import pattern_recognition as pr
from research import pattern_report as rep
from research.pattern_recognition import PatternConfig, scan_patterns
from research.pattern_report import (
    DEFAULT_TITLE,
    build_markdown_report,
    report_from_dict,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "patterns"
FIXED_TIME = "2026-06-15T00:00:00+00:00"


def _bar(date, o, h, l, c, v=None):
    return pr.PatternBar(date=date, open=o, high=h, low=l, close=c, volume=v)


def _detected_report():
    bars, outcomes, symbol, _ = pr.load_dataset(FIXTURES / "outcomes_clusters.json")
    cfg = PatternConfig(
        consolidation_window=6, volume_spike_window=6, trend_window=6,
        lookback=8, cluster_min_outcomes=6, cluster_min_len=3,
    )
    return scan_patterns(bars, cfg, symbol=symbol, outcomes=outcomes)


def _run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rep.main(argv)
    return rc, buf.getvalue()


# --------------------------------------------------------------------------- #
# Markdown structure
# --------------------------------------------------------------------------- #
class MarkdownStructureTests(unittest.TestCase):
    def setUp(self):
        self.md = build_markdown_report(_detected_report(), generated_at=FIXED_TIME)

    def test_metadata_block(self):
        self.assertIn(f"# {DEFAULT_TITLE}", self.md)
        self.assertIn(f"- **generated_at:** {FIXED_TIME}", self.md)
        self.assertIn("- **research_only:** true", self.md)
        self.assertIn("- **data_is_real:** false", self.md)
        self.assertIn("- **broker_execution:** disabled", self.md)
        self.assertIn("- **status:** OK", self.md)

    def test_input_quality_section(self):
        self.assertIn("## Input quality", self.md)
        self.assertIn("| symbol | CLU |", self.md)
        self.assertIn("| bars_analysed | 8 |", self.md)

    def test_detected_patterns_table(self):
        self.assertIn("## Detected patterns", self.md)
        self.assertIn("| Pattern | Confidence | data_is_real | Evidence (summary) |", self.md)
        self.assertIn("breakout_after_consolidation", self.md)
        self.assertIn("volume_spike", self.md)
        self.assertIn("win_loss_clusters", self.md)

    def test_not_detected_table_has_no_match_rows(self):
        self.assertIn("## Not detected / fail-closed patterns", self.md)
        self.assertTrue(
            any("gap_continuation_risk" in ln and "no-match" in ln for ln in self.md.splitlines())
        )

    def test_evidence_summary_section(self):
        self.assertIn("## Evidence summary", self.md)
        self.assertIn("### breakout_after_consolidation", self.md)
        self.assertIn("consolidation_high:", self.md)

    def test_missing_data_warnings_none_when_complete(self):
        self.assertIn("## Missing-data warnings", self.md)
        # outcomes_clusters fixture has full volume + enough bars -> no warnings.
        section = self.md.split("## Missing-data warnings", 1)[1]
        self.assertIn("_None._", section.split("##", 1)[0])

    def test_notes_section_carries_unrecognized_label(self):
        self.assertIn("## Notes", self.md)
        self.assertIn("MYSTERY", self.md)

    def test_disclaimer_and_future_notes(self):
        self.assertIn("Not trading advice", self.md)
        self.assertIn("## Future integration notes", self.md)
        self.assertIn(">=30-per-setup gate", self.md)


# --------------------------------------------------------------------------- #
# Fail-closed rendering
# --------------------------------------------------------------------------- #
class FailClosedRenderTests(unittest.TestCase):
    def test_dataset_failed_closed_report(self):
        bars = [
            _bar("2024-01-01", 100, 101, 99, 100, 1000),
            _bar("2024-01-02", 100, 90, 100, 95, 1000),  # high < low -> invalid
            _bar("2024-01-03", 95, 97, 94, 96, 1000),
        ]
        report = scan_patterns(bars, symbol="X", data_is_real=True)
        md = build_markdown_report(report, generated_at=FIXED_TIME)
        self.assertIn("- **status:** FAILED_CLOSED", md)
        self.assertIn("- **data_is_real:** false", md)  # forced false despite caller asserting true
        self.assertIn("## Dataset errors (failed closed)", md)
        self.assertIn("_No patterns detected in this window._", md)
        self.assertIn("_No detector results (dataset failed closed)._", md)
        self.assertIn("Not trading advice", md)

    def test_insufficient_data_shows_fail_closed_rows_and_reasons(self):
        # Three valid bars under default config -> most detectors fail closed.
        bars = [
            _bar("2024-01-01", 100, 101, 99, 100, 1000),
            _bar("2024-01-02", 100, 102, 99, 101, 1000),
            _bar("2024-01-03", 101, 103, 100, 102, 1000),
        ]
        report = scan_patterns(bars, symbol="X")
        md = build_markdown_report(report, generated_at=FIXED_TIME)
        self.assertTrue(
            any("breakout_after_consolidation" in ln and "fail-closed" in ln
                for ln in md.splitlines())
        )
        self.assertIn("insufficient", md)


# --------------------------------------------------------------------------- #
# data_is_real propagation (never invented)
# --------------------------------------------------------------------------- #
class DataIsRealPropagationTests(unittest.TestCase):
    def _scan(self, data_is_real):
        bars, _, symbol, _ = pr.load_dataset(FIXTURES / "breakout_volume.json")
        cfg = PatternConfig(consolidation_window=6, volume_spike_window=6, trend_window=6, lookback=8)
        return scan_patterns(bars, cfg, symbol=symbol, data_is_real=data_is_real)

    def test_true_is_propagated_into_report_and_rows(self):
        md = build_markdown_report(self._scan(True), generated_at=FIXED_TIME)
        self.assertIn("- **data_is_real:** true", md)
        self.assertTrue(
            any("breakout_after_consolidation" in ln and "| true |" in ln
                for ln in md.splitlines())
        )

    def test_false_is_never_upgraded(self):
        md = build_markdown_report(self._scan(False), generated_at=FIXED_TIME)
        self.assertIn("- **data_is_real:** false", md)
        self.assertTrue(
            any("breakout_after_consolidation" in ln and "| false |" in ln
                for ln in md.splitlines())
        )


# --------------------------------------------------------------------------- #
# No broker / order / live-action wording in the rendered report
# --------------------------------------------------------------------------- #
class NoActionWordingTests(unittest.TestCase):
    FORBIDDEN = [
        "place order", "submit order", "cancel order", "market order", "limit order",
        "go long", "go short", "execute trade", "execute order", " buy ", " sell ",
    ]

    def test_report_has_no_action_wording(self):
        md = build_markdown_report(_detected_report(), generated_at=FIXED_TIME).lower()
        for token in self.FORBIDDEN:
            with self.subTest(token=token):
                self.assertNotIn(token, md)

    def test_report_states_research_only_and_not_advice(self):
        md = build_markdown_report(_detected_report(), generated_at=FIXED_TIME).lower()
        self.assertIn("not trading advice", md)
        self.assertIn("research_only", md)


# --------------------------------------------------------------------------- #
# Serialized round-trip fidelity
# --------------------------------------------------------------------------- #
class RoundTripTests(unittest.TestCase):
    def test_report_from_dict_round_trips_to_identical_markdown(self):
        report = _detected_report()
        restored = report_from_dict(pr.report_to_dict(report))
        md1 = build_markdown_report(report, generated_at=FIXED_TIME)
        md2 = build_markdown_report(restored, generated_at=FIXED_TIME)
        self.assertEqual(md1, md2)

    def test_report_from_dict_defaults_data_is_real_false(self):
        # A malformed/partial dict must not invent realness.
        restored = report_from_dict({"signals": [], "research_only": True})
        self.assertFalse(restored.data_is_real)
        self.assertEqual("disabled", restored.broker_execution)


# --------------------------------------------------------------------------- #
# CLI (offline, synthetic by default)
# --------------------------------------------------------------------------- #
class CliTests(unittest.TestCase):
    def test_cli_on_dataset_fixture_does_not_assert_realness(self):
        rc, out = _run_cli([
            str(FIXTURES / "outcomes_clusters.json"),
            "--consolidation-window", "6", "--volume-window", "6",
            "--trend-window", "6", "--lookback", "8",
        ])
        self.assertEqual(0, rc)
        self.assertIn(f"# {DEFAULT_TITLE}", out)
        self.assertIn("- **data_is_real:** false", out)
        self.assertIn("## Detected patterns", out)
        self.assertIn("breakout_after_consolidation", out)

    def test_cli_on_serialized_report(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "scan_report.json"
            path.write_text(json.dumps(pr.report_to_dict(_detected_report())), encoding="utf-8")
            rc, out = _run_cli([str(path)])
        self.assertEqual(0, rc)
        self.assertIn("Pattern Recognition Research Report", out)
        self.assertIn("win_loss_clusters", out)

    def test_cli_rejects_unknown_input_shape(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text(json.dumps({"foo": 1}), encoding="utf-8")
            rc, _ = _run_cli([str(path)])
        self.assertEqual(2, rc)


# --------------------------------------------------------------------------- #
# Safety: no broker / network / runtime imports; not wired into the runner
# --------------------------------------------------------------------------- #
class SafetyTests(unittest.TestCase):
    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(rep.__file__).read_text(encoding="utf-8")
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
        runner = Path(rep.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("pattern_report", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
