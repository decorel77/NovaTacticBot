"""Tests for research/analytics_json_export_cli.py (TACTIC-RP-002 CLI).

Offline, synthetic-only, broker-free. The CLI prints JSON to stdout, never
asserts realness, reads no real directory, and fails closed on bad fixtures.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research import analytics_json_export_cli as cli
from research.analytics_json_export_cli import main

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "analytics"
SYNTHETIC = FIXTURES / "events_synthetic.json"


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ValidFixtureTests(unittest.TestCase):
    def test_prints_json_and_returns_zero(self):
        rc, out, _ = _run([str(SYNTHETIC)])
        self.assertEqual(0, rc)
        parsed = json.loads(out)
        self.assertEqual(4, parsed["analytics"]["data_quality"]["total_events"])
        self.assertIn("covered_call", parsed["analytics"]["strategy_stats"])

    def test_data_is_real_always_false(self):
        _, out, _ = _run([str(SYNTHETIC)])
        self.assertFalse(json.loads(out)["meta"]["data_is_real"])

    def test_no_indent_flag_emits_compact_json(self):
        _, out, _ = _run([str(SYNTHETIC), "--no-indent"])
        self.assertEqual(1, len(out.strip().splitlines()))  # single line
        self.assertTrue(json.loads(out)["meta"]["research_only"])


class FailClosedTests(unittest.TestCase):
    def test_missing_file_fails_closed(self):
        rc, _, err = _run([str(FIXTURES / "does_not_exist.json")])
        self.assertEqual(2, rc)
        self.assertIn("failed closed", err)

    def test_malformed_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{not valid json", encoding="utf-8")
            rc, _, err = _run([str(bad)])
        self.assertEqual(2, rc)
        self.assertIn("failed closed", err)

    def test_event_missing_required_field_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad_events.json"
            # event missing the required strategy_id -> from_dict raises -> fail closed
            bad.write_text(
                json.dumps({"events": [{"source_bot": "X", "event_type": "TRADE_OUTCOME"}]}),
                encoding="utf-8",
            )
            rc, _, err = _run([str(bad)])
        self.assertEqual(2, rc)
        self.assertIn("failed closed", err)


class SafetyTests(unittest.TestCase):
    def test_no_real_dir_option_rejected(self):
        # There is no real-directory option: argparse must reject it.
        with self.assertRaises(SystemExit):
            _run(["--nova-botv2-dir", "whatever", str(SYNTHETIC)])

    def test_no_broker_or_network_imports(self):
        from utils.guardrails import _BANNED_PACKAGES

        source = Path(cli.__file__).read_text(encoding="utf-8")
        forbidden = []
        for pkg in _BANNED_PACKAGES:
            forbidden.append(f"import {pkg}")
            forbidden.append(f"from {pkg}")
        forbidden += [
            "import socket",
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
        runner = Path(cli.__file__).resolve().parents[1] / "tools" / "run_tacticbot.py"
        if runner.is_file():
            self.assertNotIn("analytics_json_export_cli", runner.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
