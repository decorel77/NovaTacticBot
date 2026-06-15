"""Offline research-only Markdown report layer for pattern recognition (NEXT-PR-002).

Turns a ``PatternScanReport`` (from ``research/pattern_recognition.py``) into a
human-readable Markdown diagnostic. It is RESEARCH-ONLY and adds no new
capability beyond formatting:

  - it reads only in-memory results or local JSON (a pattern dataset fixture, or
    a serialized scan report dict from ``report_to_dict``),
  - it places no orders and connects to no broker / data feed / network,
  - it imports no broker / order / live-cycle / scheduler / subprocess modules,
  - it touches no risk, capital, or position-sizing settings,
  - it is NOT wired into ``tools/run_tacticbot.py`` or any scheduler,
  - it writes nothing by default (the CLI prints Markdown to stdout),
  - it PROPAGATES ``research_only`` and ``data_is_real`` from the input report
    and never invents realness; a dataset scanned through the CLI is always
    ``data_is_real=False``.

The output is descriptive evidence formatting, not a trade instruction. Nothing
here can influence a live decision, risk, or capital.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from research import pattern_recognition as pr
from research.pattern_recognition import (
    PatternConfig,
    PatternScanReport,
    PatternSignal,
    scan_patterns,
)

RESEARCH_ONLY: bool = True
DEFAULT_TITLE: str = "NovaTacticBot - Pattern Recognition Research Report"

# Static disclaimer / integration text. Deliberately avoids any action-instruction
# wording (no order/entry/exit imperatives); it only describes what the layer does
# NOT do.
_DISCLAIMER = (
    "> **Not trading advice.** This Markdown is a research-only diagnostic "
    "generated offline from sanitized data. It runs entirely offline, connects "
    "to no data feed, and is not wired into `tools/run_tacticbot.py` or any "
    "scheduler. It changes no risk or capital settings. Detected patterns are "
    "descriptive evidence only and never drive live decisions."
)

_FUTURE_NOTES = (
    "## Future integration notes\n\n"
    "This report is intentionally **not** part of any runtime cycle. A future "
    "*diagnostic-only* integration would, at most:\n\n"
    "- consume `report_to_dict(report)` read-only as a static research artifact "
    "alongside the existing TacticBot analytics;\n"
    "- run behind an explicit research/diagnostic flag - never by default in "
    "`tools/run_tacticbot.py` or any scheduler;\n"
    "- require a deliberate, human-reviewed promotion step (like the future-bot "
    "freeze) before any wiring;\n"
    "- surface results only after real, out-of-sample sample sizes pass the "
    ">=30-per-setup gate (NEXT-016).\n\n"
    "Even then it would stay descriptive only: it cannot influence live "
    "decisions, risk, or capital, and cannot reach a broker."
)


def _md_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _evidence_value(value: Any) -> str:
    if isinstance(value, bool):
        return _md_bool(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _evidence_inline(evidence: Mapping[str, Any]) -> str:
    """Compact one-line evidence summary for the detected-patterns table."""
    if not evidence:
        return "-"
    parts = [f"{k}={_evidence_value(v)}" for k, v in evidence.items()]
    text = "; ".join(parts)
    # Keep table cells readable; full evidence lives in its own section.
    return text if len(text) <= 160 else text[:157] + "..."


def _md_escape_cell(text: str) -> str:
    """Escape pipe characters so evidence never breaks a Markdown table."""
    return text.replace("|", "\\|")


# --------------------------------------------------------------------------- #
# Reconstruct a report from its serialized dict (report_to_dict output)
# --------------------------------------------------------------------------- #
def report_from_dict(data: Mapping[str, Any]) -> PatternScanReport:
    """Rebuild a ``PatternScanReport`` from ``report_to_dict`` output.

    Fails closed structurally: missing fields fall back to safe defaults
    (``data_is_real`` defaults False, never invented).
    """
    signals = tuple(
        PatternSignal(
            pattern_name=str(s.get("pattern_name", "unknown")),
            detected=bool(s.get("detected", False)),
            confidence_score=float(s.get("confidence_score", 0.0) or 0.0),
            evidence=dict(s.get("evidence") or {}),
            required_data_quality=dict(s.get("required_data_quality") or {}),
            missing_data=tuple(s.get("missing_data") or ()),
            fail_closed_reason=s.get("fail_closed_reason"),
            research_only=bool(s.get("research_only", True)),
            data_is_real=bool(s.get("data_is_real", False)),
        )
        for s in (data.get("signals") or ())
    )
    return PatternScanReport(
        research_only=bool(data.get("research_only", True)),
        broker_execution=str(data.get("broker_execution", "disabled")),
        data_is_real=bool(data.get("data_is_real", False)),
        input_source=str(data.get("input_source", "fixture")),
        symbol=str(data.get("symbol", "?")),
        bars_analysed=int(data.get("bars_analysed", 0) or 0),
        config=dict(data.get("config") or {}),
        signals=signals,
        errors=tuple(data.get("errors") or ()),
        notes=tuple(data.get("notes") or ()),
    )


# --------------------------------------------------------------------------- #
# Markdown builder
# --------------------------------------------------------------------------- #
def build_markdown_report(
    report: PatternScanReport,
    *,
    title: str = DEFAULT_TITLE,
    generated_at: str | None = None,
) -> str:
    """Render a ``PatternScanReport`` as a research-only Markdown diagnostic.

    ``generated_at`` may be supplied for deterministic output (tests); otherwise
    a UTC timestamp is used. ``research_only`` and ``data_is_real`` are taken
    verbatim from ``report`` — this layer never asserts realness.
    """
    when = generated_at if generated_at is not None else _utc_now_iso()
    detected = [s for s in report.signals if s.detected]
    fail_closed = [s for s in report.signals if s.fail_closed_reason]
    not_detected = [s for s in report.signals if not s.detected]

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **generated_at:** {when}")
    lines.append("- **research_only:** true")
    lines.append(f"- **data_is_real:** {_md_bool(report.data_is_real)}")
    lines.append(f"- **broker_execution:** {report.broker_execution}")
    lines.append(f"- **status:** {'OK' if report.ok else 'FAILED_CLOSED'}")
    lines.append("")
    lines.append(_DISCLAIMER)
    lines.append("")

    # Input quality summary.
    lines.append("## Input quality")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| symbol | {report.symbol} |")
    lines.append(f"| input_source | {report.input_source} |")
    lines.append(f"| bars_analysed | {report.bars_analysed} |")
    lines.append(f"| data_is_real | {_md_bool(report.data_is_real)} |")
    lines.append(f"| detectors_run | {len(report.signals)} |")
    lines.append(f"| detected | {len(detected)} |")
    lines.append(f"| fail_closed | {len(fail_closed)} |")
    lines.append(f"| dataset_errors | {len(report.errors)} |")
    lines.append("")

    # Dataset-level errors (fail closed): no detector results exist.
    if report.errors:
        lines.append("## Dataset errors (failed closed)")
        lines.append("")
        lines.append(
            "The scan failed closed on invalid data; no patterns were evaluated "
            "and `data_is_real` is forced false."
        )
        lines.append("")
        for e in report.errors:
            lines.append(f"- {e}")
        lines.append("")

    # Detected patterns table.
    lines.append("## Detected patterns")
    lines.append("")
    if detected:
        lines.append("| Pattern | Confidence | data_is_real | Evidence (summary) |")
        lines.append("|---|---|---|---|")
        for s in detected:
            ev = _md_escape_cell(_evidence_inline(s.evidence))
            lines.append(
                f"| {s.pattern_name} | {s.confidence_score} | "
                f"{_md_bool(s.data_is_real)} | {ev} |"
            )
    else:
        lines.append("_No patterns detected in this window._")
    lines.append("")

    # Non-detected / fail-closed patterns table.
    lines.append("## Not detected / fail-closed patterns")
    lines.append("")
    if not_detected:
        lines.append("| Pattern | Status | Reason | Missing data |")
        lines.append("|---|---|---|---|")
        for s in not_detected:
            status = "fail-closed" if s.fail_closed_reason else "no-match"
            reason = _md_escape_cell(s.fail_closed_reason) if s.fail_closed_reason else "-"
            missing = _md_escape_cell(", ".join(s.missing_data)) if s.missing_data else "-"
            lines.append(f"| {s.pattern_name} | {status} | {reason} | {missing} |")
    else:
        lines.append("_No detector results (dataset failed closed)._")
    lines.append("")

    # Evidence summary (per detected pattern).
    lines.append("## Evidence summary")
    lines.append("")
    if detected:
        for s in detected:
            lines.append(f"### {s.pattern_name} (confidence {s.confidence_score})")
            if s.evidence:
                for k, v in s.evidence.items():
                    lines.append(f"- {k}: {_evidence_value(v)}")
            else:
                lines.append("- (no evidence fields)")
            lines.append("")
    else:
        lines.append("_No detected-pattern evidence._")
        lines.append("")

    # Missing-data warnings.
    lines.append("## Missing-data warnings")
    lines.append("")
    warned = False
    for s in report.signals:
        if s.missing_data:
            warned = True
            lines.append(f"- {s.pattern_name}: {', '.join(s.missing_data)}")
    for e in report.errors:
        warned = True
        lines.append(f"- dataset: {e}")
    if not warned:
        lines.append("_None._")
    lines.append("")

    # Notes from the scan (e.g. unrecognized setup labels).
    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append(_FUTURE_NOTES)
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# CLI (offline, synthetic by default)
# --------------------------------------------------------------------------- #
def _looks_like_report(data: Any) -> bool:
    return isinstance(data, Mapping) and "signals" in data and "research_only" in data


def _looks_like_dataset(data: Any) -> bool:
    return isinstance(data, Mapping) and "bars" in data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Offline RESEARCH-ONLY pattern recognition report (no broker, no orders). "
            "Accepts a synthetic pattern dataset fixture (scanned with data_is_real=false) "
            "or a serialized scan-report JSON (from report_to_dict)."
        )
    )
    parser.add_argument("input", help="path to a synthetic dataset fixture or serialized scan report")
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--consolidation-window", type=int, default=None)
    parser.add_argument("--trend-window", type=int, default=None)
    parser.add_argument("--volume-window", type=int, default=None)
    parser.add_argument("--lookback", type=int, default=None)
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    if _looks_like_report(data):
        # Serialized scan report: render as-is, propagating its flags.
        report = report_from_dict(data)
    elif _looks_like_dataset(data):
        # Pattern dataset fixture: scan offline, never asserting realness.
        bars, outcomes, symbol, meta = pr.load_dataset(args.input)
        overrides: dict[str, Any] = {}
        if args.consolidation_window is not None:
            overrides["consolidation_window"] = args.consolidation_window
        if args.trend_window is not None:
            overrides["trend_window"] = args.trend_window
        if args.volume_window is not None:
            overrides["volume_spike_window"] = args.volume_window
        if args.lookback is not None:
            overrides["lookback"] = args.lookback
        cfg = PatternConfig(**overrides)
        report = scan_patterns(
            bars,
            cfg,
            symbol=symbol,
            input_source=str(meta.get("input_source", "fixture")),
            data_is_real=False,  # CLI never asserts realness; fixtures are research-only
            outcomes=outcomes or None,
        )
    else:
        print(
            "error: input is neither a pattern dataset (needs 'bars') nor a "
            "serialized scan report (needs 'signals' + 'research_only')",
            file=sys.stderr,
        )
        return 2

    print(build_markdown_report(report, title=args.title), end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
