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
    python tools/run_tacticbot.py [--source-dir PATH] [--report-dir PATH]
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

from utils.guardrails import run_all_checks
from adapters.options_adapter import OptionsAdapter
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
        "--source-dir",
        default=None,
        help="Directory containing NovaBotV2Options output files",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # ── Step 1: Guardrails ─────────────────────────────────────────────────────
    logger.info("=== NovaTacticBot starting — ADVISORY ONLY MODE ===")
    try:
        run_all_checks()
    except Exception as e:
        logger.critical("Guardrail check failed: %s", e)
        return 1

    # ── Step 2 & 3: Load adapters and events ───────────────────────────────────
    events: list[TacticalEvent] = []
    adapter_errors: list[str] = []

    options_adapter = OptionsAdapter(source_dir=args.source_dir)
    options_events = options_adapter.load()
    events.extend(options_events)
    adapter_errors.extend(options_adapter.load_errors)

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
    written_path = generator.generate(result, output_path=report_path)
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
