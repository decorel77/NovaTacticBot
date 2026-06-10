"""
NovaTacticBot Runner

Workflow:
  1. Guardrail checks
  2. Load adapters
  3. Load tactical events
  4. Run analytics
  5. Generate report
  6. Exit

READ-ONLY. No trades. No modifications. No broker access.

Usage:
    # Real NovaBotV2Options directory:
    python tools/run_tacticbot.py --nova-options-dir C:/NovaGPT/Apps/NovaBotV2Options

    # Generic source directory (JSON/CSV/log files):
    python tools/run_tacticbot.py --source-dir PATH

    # Both:
    python tools/run_tacticbot.py --nova-options-dir PATH --source-dir PATH2
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when running directly
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.guardrails import run_all_checks, GuardrailViolation
from adapters.options_adapter import OptionsAdapter
from adapters.nova_options_adapter import NovaBotV2OptionsAdapter
from core.tactic_analytics_engine import TacticAnalyticsEngine
from core.tactic_event import TacticalEvent
from utils.tactic_report_generator import TacticReportGenerator

# Run-path artifact writers (REPAIR-004 — previously orphan modules).
from utils.tactic_snapshot_writer import TacticSnapshotWriter, snapshot_from_result
from utils.run_history_tracker import RunHistoryTracker, RunHistoryEntry
from utils.analytics_baseline_writer import (
    AnalyticsBaselineWriter,
    snapshot_from_result as baseline_from_result,
)
from utils.tactic_run_log_writer import TacticRunLogWriter, RunLogEntry
from utils.adapter_error_logger import AdapterErrorLogger, AdapterErrorEntry
from utils.source_provenance import derive_run_provenance
from workflow.tactic_html_dashboard import TacticHtmlDashboard

_SYSTEM_DIR = _PROJECT_ROOT / "data" / "system"
_LOGS_DIR = _PROJECT_ROOT / "data" / "logs"
_REPORTS_DIR = _PROJECT_ROOT / "data" / "reports"

# Canonical required keys (REPAIR-003 NovaBridge schema). Checked inline so the
# runner stays decoupled from NovaBridge; the test suite runs the real validator.
_CANONICAL_REQUIRED_KEYS = (
    "schema_version", "producer_id", "produced_at", "fresh_until",
    "input_source", "data_is_real", "advisory_only", "broker_execution",
    "live_trading_active", "status", "payload",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("run_tacticbot")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NovaTacticBot — read-only tactical intelligence runner"
    )
    parser.add_argument(
        "--nova-options-dir",
        default=None,
        help="Root directory of NovaBotV2Options repository (reads data/logs/ and data/reports/)",
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Generic source directory containing JSON/CSV/log files (OptionsAdapter)",
    )
    parser.add_argument(
        "--report-dir",
        default=str(_PROJECT_ROOT / "data" / "reports"),
        help="Directory to write the intelligence report",
    )
    parser.add_argument(
        "--report-name",
        default="tacticbot_report.md",
        help="Report file name",
    )
    # NOTE (REPAIR-011): the former --warn-broker-env escape hatch was removed.
    # The broker guardrail is now HARD: if a broker package is importable the run
    # is aborted, with no bypass. Run NovaTacticBot inside its broker-free venv
    # (see setup_venv.ps1 / setup_venv.sh) instead of weakening the guardrail.
    return parser.parse_args()


def _check_canonical_conformance(snapshot: dict) -> list[str]:
    """Lightweight, dependency-free canonical conformance check.

    Mirrors the REPAIR-003 rejection rules for the fields this producer controls,
    without importing NovaBridge at runtime. The test suite runs the real
    NovaBridge validator for the authoritative check.
    """
    problems = []
    for key in _CANONICAL_REQUIRED_KEYS:
        if snapshot.get(key) is None:
            problems.append(f"missing {key}")
    if snapshot.get("schema_version") != "1.0":
        problems.append("schema_version must be '1.0'")
    if snapshot.get("data_is_real") is not True:
        problems.append("data_is_real must be true")
    if snapshot.get("broker_execution") is not False:
        problems.append("broker_execution must be false")
    if snapshot.get("live_trading_active") is not False:
        problems.append("live_trading_active must be false")
    return problems


def persist_run_artifacts(
    result,
    events,
    adapter_errors,
    *,
    input_source: str,
    data_is_real: bool,
    duration_seconds: float,
    diagnostics=None,
    system_dir: Path = _SYSTEM_DIR,
    logs_dir: Path = _LOGS_DIR,
    reports_dir: Path = _REPORTS_DIR,
) -> tuple[dict, dict]:
    """Write the six run-path artifacts from an executed analysis run.

    Returns (snapshot_dict, paths). Pure file writes under data/; no broker,
    no network. Parametrised on output dirs so tests can target a tmp dir.
    """
    system_dir = Path(system_dir)
    logs_dir = Path(logs_dir)
    reports_dir = Path(reports_dir)
    paths: dict[str, Path] = {}

    # 1. result_snapshot.json (canonical envelope per REPAIR-003).
    snap = snapshot_from_result(result, input_source=input_source, data_is_real=data_is_real)
    paths["result_snapshot"] = TacticSnapshotWriter(
        system_dir / "result_snapshot.json"
    ).write(snap)

    # 2. run_history.json
    history = RunHistoryTracker(system_dir / "run_history.json")
    run_entry = RunHistoryEntry(
        events_processed=len(events),
        reports_generated=1,
        errors=list(adapter_errors),
    )
    history.append(run_entry)
    paths["run_history"] = system_dir / "run_history.json"

    # 3. analytics_baseline.json
    AnalyticsBaselineWriter(system_dir / "analytics_baseline.json").append(
        baseline_from_result(result, run_id=run_entry.run_id)
    )
    paths["analytics_baseline"] = system_dir / "analytics_baseline.json"

    # 4. tactic_run_log.jsonl
    event_counts: dict[str, int] = {}
    for ev in events:
        et = getattr(ev, "event_type", "EVENT")
        event_counts[et] = event_counts.get(et, 0) + 1
    TacticRunLogWriter(logs_dir / "tactic_run_log.jsonl").write(
        RunLogEntry(
            run_id=run_entry.run_id,
            sources_ingested=1 if input_source else 0,
            event_counts=event_counts,
            duration_seconds=round(float(duration_seconds), 4),
            reports_generated=1,
            warnings=list(adapter_errors),
        )
    )
    paths["tactic_run_log"] = logs_dir / "tactic_run_log.jsonl"

    # 5. tactic_adapter_errors.jsonl — real errors plus a per-run boundary line
    #    so the log is non-empty and auditable even on a clean run.
    err_logger = AdapterErrorLogger(logs_dir / "tactic_adapter_errors.jsonl")
    for msg in adapter_errors:
        err_logger.log(AdapterErrorEntry(
            adapter_name="run_path", file_path="-",
            error_type="AdapterError", error_message=str(msg),
        ))
    skipped = getattr(diagnostics, "records_skipped", 0) if diagnostics is not None else 0
    err_logger.log(AdapterErrorEntry(
        adapter_name="(run-summary)", file_path="-", error_type="NONE",
        error_message=f"{len(adapter_errors)} adapter error(s); {skipped} record(s) skipped this run",
        event_count_impact=0, event_type="RUN_SUMMARY",
    ))
    paths["tactic_adapter_errors"] = logs_dir / "tactic_adapter_errors.jsonl"

    # 6. tactic_dashboard.html
    paths["tactic_dashboard"] = TacticHtmlDashboard(
        reports_dir / "tactic_dashboard.html"
    ).write(result)

    return snap.to_dict(), paths


def main() -> int:
    args = parse_args()
    _run_started = time.monotonic()

    # ── Step 1: Guardrails ─────────────────────────────────────────────────────
    logger.info("=== NovaTacticBot starting — ADVISORY ONLY MODE ===")
    try:
        run_all_checks()
    except GuardrailViolation as e:
        # HARD guardrail (REPAIR-011): no escape hatch. NovaTacticBot is
        # advisory-only and must run in a broker-free environment.
        logger.critical("Guardrail check failed: %s", e)
        logger.critical(
            "NovaTacticBot must run in its isolated, broker-free virtualenv. "
            "Create it with setup_venv.ps1 (or setup_venv.sh) and run this script "
            "with that venv's interpreter. The previous --warn-broker-env bypass "
            "was removed in REPAIR-011."
        )
        return 1
    except Exception as e:
        logger.critical("Guardrail check failed: %s", e)
        return 1

    # ── Step 2 & 3: Load adapters and events ───────────────────────────────────
    events: list[TacticalEvent] = []
    adapter_errors: list[str] = []
    diagnostics = None
    supplementary = None

    # Real NovaBotV2Options directory (preferred)
    if args.nova_options_dir:
        nova_adapter = NovaBotV2OptionsAdapter(source_dir=args.nova_options_dir)
        nova_events = nova_adapter.load()
        events.extend(nova_events)
        adapter_errors.extend(nova_adapter.load_errors)
        diagnostics = nova_adapter.diagnostics
        supplementary = {
            "strategy_performance": nova_adapter.strategy_performance,
            "regime_performance": nova_adapter.regime_performance,
            "lifecycle_summary": nova_adapter.lifecycle_summary,
        }
        logger.info(
            "NovaBotV2OptionsAdapter: %d events (diagnostics: %d skipped, %d errors)",
            len(nova_events),
            nova_adapter.diagnostics.records_skipped,
            len(nova_adapter.diagnostics.parse_errors),
        )

    # Generic source directory (OptionsAdapter — JSON/CSV/log)
    if args.source_dir:
        options_adapter = OptionsAdapter(source_dir=args.source_dir)
        options_events = options_adapter.load()
        events.extend(options_events)
        adapter_errors.extend(options_adapter.load_errors)
        logger.info("OptionsAdapter: %d events", len(options_events))

    if not args.nova_options_dir and not args.source_dir:
        logger.warning(
            "No source directory specified. Pass --nova-options-dir or --source-dir. "
            "Generating empty report."
        )

    logger.info("Total events loaded: %d", len(events))
    if adapter_errors:
        logger.warning("%d adapter errors encountered", len(adapter_errors))
        for err in adapter_errors:
            logger.warning("  - %s", err)

    # ── Step 4: Analytics ──────────────────────────────────────────────────────
    engine = TacticAnalyticsEngine()
    result = engine.run(events)
    logger.info(
        "Analytics complete — %d strategies, %d regimes",
        len(result.strategy_stats),
        len(result.regime_stats),
    )

    # ── Step 5: Report generation ──────────────────────────────────────────────
    report_path = Path(args.report_dir) / args.report_name
    generator = TacticReportGenerator()
    diag_path = Path(args.report_dir) / "adapter_diagnostics.md"
    written_path = generator.generate(
        result,
        output_path=report_path,
        diagnostics=diagnostics,
        supplementary=supplementary,
        diagnostics_path=diag_path,
    )
    logger.info("Report written: %s", written_path)
    if diagnostics is not None:
        logger.info("Diagnostics written: %s", diag_path)

    # ── Step 5b: Persist run-path artifacts (REPAIR-004) ───────────────────────
    # POST-005: data_is_real is derived from trusted adapter provenance, not from
    # whether a source directory was passed. Generic/dummy input stays false.
    provenance = derive_run_provenance(args.nova_options_dir, args.source_dir)
    input_source = provenance.input_source
    data_is_real = provenance.data_is_real
    for reason in provenance.reasons:
        logger.info("data_is_real provenance: %s", reason)

    snapshot_dict, artifact_paths = persist_run_artifacts(
        result,
        events,
        adapter_errors,
        input_source=input_source,
        data_is_real=data_is_real,
        duration_seconds=time.monotonic() - _run_started,
        diagnostics=diagnostics,
    )
    for name, path in artifact_paths.items():
        logger.info("Artifact written: %-22s %s", name, path)

    conformance = _check_canonical_conformance(snapshot_dict)
    if data_is_real and not conformance:
        logger.info("result_snapshot conforms to the REPAIR-003 canonical schema (1.0)")
    elif conformance:
        logger.warning(
            "result_snapshot is not canonical (expected for a no-source/empty run): %s",
            conformance,
        )

    # ── Step 6: Summary ────────────────────────────────────────────────────────
    logger.info("=== NovaTacticBot run complete ===")
    logger.info("  Events processed : %d", len(events))
    logger.info("  Adapter errors   : %d", len(adapter_errors))
    logger.info("  Observations     : %d", len(result.observations))
    logger.info("  Open questions   : %d", len(result.open_questions))
    logger.info("  Report           : %s", written_path)
    logger.info("  ADVISORY_ONLY    : True — no trades or modifications made")

    return 0


if __name__ == "__main__":
    sys.exit(main())
