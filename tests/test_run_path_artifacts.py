"""Tests that the NovaTacticBot run path PRODUCES its artifacts (REPAIR-004).

The Phase 3/4/5/10/11 writers/adapters were orphan modules — present with green
unit tests but never wired into tools/run_tacticbot.py, so result_snapshot.json,
run_history.json, analytics_baseline.json, the two .jsonl logs, and
tactic_dashboard.html never existed on disk. These tests exercise the wired
persistence helper and assert all six artifacts are produced, parse, and that the
snapshot validates against the REPAIR-003 canonical schema.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.tactic_analytics_engine import AnalyticsResult, RegimeStats, StrategyStats
from tools.run_tacticbot import persist_run_artifacts, _check_canonical_conformance

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOVABRIDGE_DIR = PROJECT_ROOT.parent / "NovaBridge"


def _make_result() -> AnalyticsResult:
    r = AnalyticsResult()
    s = StrategyStats(strategy_id="PUT_SELL")
    s.trade_outcomes = 10
    s.wins = 7
    s.win_rate = 0.7
    r.strategy_stats["PUT_SELL"] = s
    reg = RegimeStats(regime="BULL")
    reg.trade_outcomes = 8
    r.regime_stats["BULL"] = reg
    r.data_quality.total_events = 23
    r.recommendation_quality.avg_score = 0.65
    return r


class _Diag:
    records_skipped = 309


def _events(n: int = 23):
    return [type("E", (), {"event_type": "TRADE_OUTCOME"})() for _ in range(n)]


def _persist(tmp_path: Path, adapter_errors=None):
    return persist_run_artifacts(
        _make_result(),
        _events(),
        adapter_errors or [],
        input_source="NovaBotV2Options",
        data_is_real=True,
        duration_seconds=0.01,
        diagnostics=_Diag(),
        system_dir=tmp_path / "system",
        logs_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
    )


def test_all_six_artifacts_produced_and_parse(tmp_path):
    _snap, paths = _persist(tmp_path)
    expected = {
        "result_snapshot", "run_history", "analytics_baseline",
        "tactic_run_log", "tactic_adapter_errors", "tactic_dashboard",
    }
    assert expected <= set(paths)
    for name, p in paths.items():
        p = Path(p)
        assert p.exists(), f"{name} missing"
        assert p.stat().st_size > 0, f"{name} is empty"

    # JSON system artifacts parse.
    json.loads(Path(paths["result_snapshot"]).read_text(encoding="utf-8"))
    assert isinstance(json.loads(Path(paths["run_history"]).read_text(encoding="utf-8")), list)
    assert isinstance(json.loads(Path(paths["analytics_baseline"]).read_text(encoding="utf-8")), list)

    # JSONL logs: every non-blank line is valid JSON.
    for key in ("tactic_run_log", "tactic_adapter_errors"):
        lines = [l for l in Path(paths[key]).read_text(encoding="utf-8").splitlines() if l.strip()]
        assert lines, f"{key} has no records"
        for line in lines:
            json.loads(line)

    # Dashboard renders HTML.
    html = Path(paths["tactic_dashboard"]).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html


def test_snapshot_is_canonically_conformant(tmp_path):
    snap, _ = _persist(tmp_path)
    assert _check_canonical_conformance(snap) == []
    assert snap["schema_version"] == "1.0"
    assert snap["producer_id"] == "NovaTacticBot"
    assert snap["data_is_real"] is True
    assert snap["advisory_only"] is True
    assert snap["broker_execution"] is False
    assert snap["live_trading_active"] is False
    assert isinstance(snap["payload"], dict)


def test_adapter_error_log_nonempty_on_clean_run(tmp_path):
    """Even with zero adapter errors, a run-boundary line keeps the log non-empty."""
    _snap, paths = _persist(tmp_path, adapter_errors=[])
    lines = [l for l in Path(paths["tactic_adapter_errors"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event_type"] == "RUN_SUMMARY"


def test_history_and_baseline_append_across_runs(tmp_path):
    _persist(tmp_path)
    _snap, paths = _persist(tmp_path)
    history = json.loads(Path(paths["run_history"]).read_text(encoding="utf-8"))
    baseline = json.loads(Path(paths["analytics_baseline"]).read_text(encoding="utf-8"))
    assert len(history) == 2
    assert history[-1]["run_count"] == 2
    assert len(baseline) == 2


@pytest.mark.skipif(
    not (NOVABRIDGE_DIR / "utils" / "snapshot_schema_validator.py").exists(),
    reason="NovaBridge REPAIR-003 validator not available",
)
def test_snapshot_validates_against_repair003_validator(tmp_path):
    """Authoritative check: run the real NovaBridge validator in its own context."""
    _snap, paths = _persist(tmp_path)
    snapshot_path = str(paths["result_snapshot"])
    script = (
        "import sys;"
        "from utils.snapshot_schema_validator import validate_snapshot_file;"
        "r=validate_snapshot_file(sys.argv[1]);"
        "print(r.verdict);"
        "print('\\n'.join(r.errors));"
        "sys.exit(0 if r.valid else 2)"
    )
    res = subprocess.run(
        [sys.executable, "-c", script, snapshot_path],
        cwd=str(NOVABRIDGE_DIR),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"validator rejected snapshot:\n{res.stdout}\n{res.stderr}"
    assert "VALID" in res.stdout
