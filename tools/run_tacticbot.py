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
    parser.add_argument(
        "--warn-broker-env",
        action="store_true",
        default=False,
        help=(
            "DEVELOPMENT ONLY: log a WARNING instead of blocking when broker packages "
            "are found in the environment. Use this when running on a developer machine "
            "that also hosts NovaBotV2Options. NovaTacticBot itself still imports nothing "
            "from broker packages. Do NOT use in production."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # ── Step 1: Guardrails ─────────────────────────────────────────────────────
    logger.info("=== NovaTacticBot starting — ADVISORY ONLY MODE ===")
    try:
        run_all_checks()
    except GuardrailViolation as e:
        if args.warn_broker_env:
            logger.warning(
                "DEVELOPMENT MODE: broker packages found in environment but continuing "
                "because --warn-broker-env was specified. NovaTacticBot code imports "
                "nothing from broker packages. Violation: %s", e
            )
        else:
            logger.critical("Guardrail check failed: %s", e)
            logger.critical(
                "If running on a developer machine with other NOVA bots installed, "
                "use --warn-broker-env to continue with a warning instead of blocking."
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
    written_path = generator.generate(
        result,
        output_path=report_path,
        diagnostics=diagnostics,
        supplementary=supplementary,
    )
    logger.info("Report written: %s", written_path)

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
