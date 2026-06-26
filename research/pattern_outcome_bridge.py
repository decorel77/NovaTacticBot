"""Offline research-only bridge: NovaBotV2 trade outcomes -> diagnostic summary (NEXT-PR-003).

Takes already-ingested, sanitized **trade-outcome** records (or events produced
by the read-only ``NovaBotV2TradeAdapter``) and computes simple, DIAGNOSTIC-ONLY
outcome summaries grouped by setup/tactic label. It then renders a research
report (its own Markdown, or a ``PatternScanReport``-compatible object that
``research/pattern_report.py`` can render).

This is the *trade-outcome* counterpart to ``research/pattern_recognition.py``
(which detects *price* patterns over OHLCV bars). The two are deliberately
separate:

  - pattern_recognition reads price BARS and describes chart structure;
  - this bridge reads closed-trade OUTCOME LABELS and tallies win/loss structure.

It is RESEARCH-ONLY and separate from any live path:

  - it reads only in-memory records or local JSON fixtures by default,
  - it reads a real NovaBotV2 outcome directory ONLY when an explicit
    ``--nova-botv2-dir`` path is passed (read-only, manual; see the docs),
  - it places no orders and connects to no broker / data feed / network,
  - it imports no broker / order / live-cycle / scheduler / subprocess modules,
  - it touches no risk, capital, or position-sizing settings,
  - it is NOT wired into ``tools/run_tacticbot.py`` or any scheduler,
  - it writes nothing by default (the CLI prints Markdown to stdout),
  - it NEVER fabricates OHLCV bars from outcomes (``bars_analysed`` is always 0),
  - it PROPAGATES ``data_is_real`` from each record (from the adapter's
    provenance) and never invents realness,
  - it FAILS CLOSED to ``INSUFFICIENT_SAMPLE`` below a documented real-outcome
    threshold and never upgrades small-sample numbers to a trusted strategy edge.

The current real stock-outcome stream is tiny (~1 deduplicated real outcome), so
every conclusion here stays DIAGNOSTIC_ONLY until enough real outcomes exist.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from research.pattern_recognition import (
    PatternScanReport,
    PatternSignal,
    normalize_setup_label,
)
from research.pattern_report import build_markdown_report

RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"

# Documented minimum number of REAL outcomes before per-setup numbers are treated
# as anything but noise. Below this the report stays INSUFFICIENT_SAMPLE.
DEFAULT_MIN_SAMPLE: int = 30

STATUS_DIAGNOSTIC: str = "DIAGNOSTIC_ONLY"
STATUS_INSUFFICIENT: str = "INSUFFICIENT_SAMPLE"

DEFAULT_TITLE: str = "NovaTacticBot - Trade-Outcome Pattern Diagnostic (Research-Only)"

# Outcome labels we recognize. WIN/LOSS are the only decisive ones; everything
# else is non-decisive and breaks win/loss streaks and the win-rate denominator.
_DECISIVE = frozenset({"WIN", "LOSS"})
_KNOWN_OUTCOMES = frozenset({"WIN", "LOSS", "BREAKEVEN", "PARTIAL", "EXPIRED", "PENDING"})


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OutcomeRecord:
    """A single sanitized closed-trade outcome label.

    ``data_is_real`` is provenance carried from the source (the adapter derives
    it from ``execution_mode``); this module never sets it true on its own.
    """

    date: str
    setup_label: str
    outcome: str               # WIN | LOSS | BREAKEVEN | PARTIAL | EXPIRED | PENDING | other
    return_pct: float | None = None
    data_is_real: bool = False


@dataclass(frozen=True)
class SetupOutcomeSummary:
    setup_label: str
    sample_count: int
    real_sample_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    other_count: int
    win_rate: float | None          # None => INSUFFICIENT_SAMPLE (below threshold)
    win_rate_status: str            # "OK" | "INSUFFICIENT_SAMPLE"
    average_return_pct: float | None  # None => not enough sample or no returns
    longest_win_cluster: int
    longest_loss_cluster: int
    data_is_real: bool              # true only if EVERY record in the group is real
    status: str                     # DIAGNOSTIC_ONLY | INSUFFICIENT_SAMPLE


@dataclass(frozen=True)
class OutcomeDiagnostic:
    research_only: bool
    broker_execution: str
    diagnostic_only: bool
    status: str                     # DIAGNOSTIC_ONLY | INSUFFICIENT_SAMPLE
    input_source: str
    data_is_real: bool
    min_sample: int
    total_sample_count: int
    total_real_sample_count: int
    bars_analysed: int              # always 0 — no OHLCV is read or fabricated
    ohlcv_used: bool                # always False
    setup_labels: tuple[str, ...]
    by_setup: dict[str, SetupOutcomeSummary]
    notes: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # Reject non-finite: a NaN-only guard let +-Infinity leak into return_pct and
    # the research outcome aggregates. Fail closed to None.
    return f if math.isfinite(f) else None


def normalize_outcome(raw: Any) -> str:
    """Normalize an outcome label, failing closed to UNKNOWN."""
    text = str(raw).strip().upper() if raw is not None else ""
    return text if text in _KNOWN_OUTCOMES else "UNKNOWN"


def _longest_clusters(outcomes: Sequence[str]) -> tuple[int, int]:
    """Return (longest_win_run, longest_loss_run). Non-decisive labels reset both."""
    longest_win = longest_loss = cur_win = cur_loss = 0
    for o in outcomes:
        if o == "WIN":
            cur_win += 1
            cur_loss = 0
        elif o == "LOSS":
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = cur_loss = 0
        longest_win = max(longest_win, cur_win)
        longest_loss = max(longest_loss, cur_loss)
    return longest_win, longest_loss


# --------------------------------------------------------------------------- #
# Input conversion
# --------------------------------------------------------------------------- #
def outcome_record_from_dict(d: Mapping[str, Any]) -> OutcomeRecord:
    return OutcomeRecord(
        date=str(d.get("date", "")),
        setup_label=str(d.get("setup_label", d.get("setup_type", ""))),
        outcome=str(d.get("outcome", "")),
        return_pct=_to_float(d.get("return_pct", d.get("pnl_pct"))),
        data_is_real=bool(d.get("data_is_real", False)),
    )


def outcomes_from_events(events: Iterable[Any]) -> list[OutcomeRecord]:
    """Convert read-only adapter TacticalEvents into sanitized OutcomeRecords.

    Duck-typed: accepts any object exposing ``event_type``, ``outcome``,
    ``strategy_id``, ``metadata``, and ``timestamp``. ``data_is_real`` is taken
    from ``metadata['data_is_real']`` — propagated, never invented.
    """
    records: list[OutcomeRecord] = []
    for e in events:
        if getattr(e, "event_type", None) != "TRADE_OUTCOME":
            continue
        md = getattr(e, "metadata", {}) or {}
        setup = getattr(e, "strategy_id", "") or md.get("setup_type") or ""
        ts = getattr(e, "timestamp", None)
        if isinstance(ts, datetime):
            date = ts.date().isoformat()
        elif ts:
            date = str(ts)[:10]
        else:
            date = "1970-01-01"
        records.append(
            OutcomeRecord(
                date=date,
                setup_label=str(setup),
                outcome=str(getattr(e, "outcome", "") or ""),
                return_pct=_to_float(md.get("pnl_pct")),
                data_is_real=bool(md.get("data_is_real", False)),
            )
        )
    return records


# --------------------------------------------------------------------------- #
# Summarize
# --------------------------------------------------------------------------- #
def summarize_outcomes(
    records: Sequence[OutcomeRecord],
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    input_source: str = "fixture",
) -> OutcomeDiagnostic:
    """Group outcomes by normalized setup label and compute diagnostic summaries.

    win_rate / average_return are reported only when a group's ``sample_count``
    reaches ``min_sample``; otherwise they are None (INSUFFICIENT_SAMPLE). The
    overall and per-setup ``status`` is INSUFFICIENT_SAMPLE whenever the REAL
    sample is below ``min_sample`` — small samples never become a trusted edge.
    """
    if not records:
        return OutcomeDiagnostic(
            research_only=RESEARCH_ONLY,
            broker_execution=BROKER_EXECUTION,
            diagnostic_only=True,
            status=STATUS_INSUFFICIENT,
            input_source=input_source,
            data_is_real=False,
            min_sample=min_sample,
            total_sample_count=0,
            total_real_sample_count=0,
            bars_analysed=0,
            ohlcv_used=False,
            setup_labels=(),
            by_setup={},
            notes=("no outcome records provided",),
            errors=("no outcome records provided",),
        )

    # Deterministic chronological order; ties broken by original index.
    ordered = [r for _, r in sorted(enumerate(records), key=lambda iv: (iv[1].date, iv[0]))]

    unrecognized_labels: list[str] = []
    by_label: dict[str, list[OutcomeRecord]] = {}
    for r in ordered:
        label, recognized = normalize_setup_label(r.setup_label)
        if not recognized and str(r.setup_label) not in unrecognized_labels:
            unrecognized_labels.append(str(r.setup_label))
        by_label.setdefault(label, []).append(r)

    by_setup: dict[str, SetupOutcomeSummary] = {}
    for label in sorted(by_label):
        recs = by_label[label]
        outcomes = [normalize_outcome(r.outcome) for r in recs]
        win = sum(1 for o in outcomes if o == "WIN")
        loss = sum(1 for o in outcomes if o == "LOSS")
        breakeven = sum(1 for o in outcomes if o == "BREAKEVEN")
        sample = len(recs)
        real = sum(1 for r in recs if r.data_is_real)
        other = sample - win - loss - breakeven
        decisive = win + loss

        if sample >= min_sample and decisive > 0:
            win_rate: float | None = round(win / decisive, 4)
            win_rate_status = "OK"
        else:
            win_rate = None
            win_rate_status = STATUS_INSUFFICIENT

        returns = [r.return_pct for r in recs if r.return_pct is not None]
        average_return = round(sum(returns) / len(returns), 4) if (sample >= min_sample and returns) else None

        longest_win, longest_loss = _longest_clusters(outcomes)
        group_real = bool(recs) and all(r.data_is_real for r in recs)
        group_status = STATUS_DIAGNOSTIC if real >= min_sample else STATUS_INSUFFICIENT

        by_setup[label] = SetupOutcomeSummary(
            setup_label=label,
            sample_count=sample,
            real_sample_count=real,
            win_count=win,
            loss_count=loss,
            breakeven_count=breakeven,
            other_count=other,
            win_rate=win_rate,
            win_rate_status=win_rate_status,
            average_return_pct=average_return,
            longest_win_cluster=longest_win,
            longest_loss_cluster=longest_loss,
            data_is_real=group_real,
            status=group_status,
        )

    total = len(ordered)
    total_real = sum(1 for r in ordered if r.data_is_real)
    overall_status = STATUS_DIAGNOSTIC if total_real >= min_sample else STATUS_INSUFFICIENT
    data_is_real = bool(ordered) and all(r.data_is_real for r in ordered)

    notes: list[str] = []
    if unrecognized_labels:
        notes.append(f"unrecognized setup labels treated as UNKNOWN: {unrecognized_labels}")
    notes.append(
        f"DIAGNOSTIC_ONLY: trade-outcome summary over {total} outcome(s) "
        f"({total_real} real); not a price pattern and not trading advice."
    )
    if overall_status == STATUS_INSUFFICIENT:
        notes.append(
            f"INSUFFICIENT_SAMPLE: {total_real} real outcome(s) < min_sample {min_sample}; "
            f"per-setup win rates are withheld and nothing here is a trusted edge."
        )

    return OutcomeDiagnostic(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        diagnostic_only=True,
        status=overall_status,
        input_source=input_source,
        data_is_real=data_is_real,
        min_sample=min_sample,
        total_sample_count=total,
        total_real_sample_count=total_real,
        bars_analysed=0,
        ohlcv_used=False,
        setup_labels=tuple(sorted(by_label)),
        by_setup=by_setup,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Render: dedicated diagnostic Markdown
# --------------------------------------------------------------------------- #
_NOT_THIS = (
    "## What this is NOT\n\n"
    "- It reads **no OHLCV bars** and **fabricates none**: this summarizes only "
    "closed-trade outcome labels (`bars_analysed = 0`).\n"
    "- It is **not** a price-pattern detection (that is `research/pattern_recognition.py`).\n"
    "- It is **not trading advice**: it runs offline, connects to nothing, changes "
    "no risk or capital, and is not wired into `tools/run_tacticbot.py` or any scheduler.\n"
    "- Small samples are **never** upgraded to a trusted strategy edge."
)

_FUTURE = (
    "## Future integration\n\n"
    "A future *diagnostic-only* step would, at most, surface this summary inside a "
    "research **report** (read-only) - never inside a trading decision. It stays "
    "DIAGNOSTIC_ONLY until the real, deduplicated, out-of-sample outcome count per "
    "setup passes the documented threshold (default >=30, the NEXT-016 gate). Even "
    "then it would remain descriptive: it cannot reach a broker, change risk or "
    "capital, or influence a live decision."
)


def _md_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _cell(value: Any) -> str:
    if value is None:
        return STATUS_INSUFFICIENT
    return str(value)


def build_diagnostic_markdown(
    diag: OutcomeDiagnostic,
    *,
    title: str = DEFAULT_TITLE,
    generated_at: str | None = None,
) -> str:
    """Render an OutcomeDiagnostic as a research-only Markdown report.

    All printed text is ASCII so it renders on any console codepage. ``status``
    and ``data_is_real`` are taken verbatim from ``diag`` (never upgraded here).
    """
    when = generated_at if generated_at is not None else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **generated_at:** {when}")
    lines.append("- **research_only:** true")
    lines.append("- **diagnostic_only:** true")
    lines.append(f"- **status:** {diag.status}")
    lines.append(f"- **data_is_real:** {_md_bool(diag.data_is_real)}")
    lines.append(f"- **broker_execution:** {diag.broker_execution}")
    lines.append(f"- **min_sample_threshold:** {diag.min_sample}")
    lines.append(f"- **ohlcv_bars_used:** {diag.bars_analysed} (no price bars were read or fabricated)")
    lines.append("")
    lines.append(
        "> **Not trading advice.** This is a trade-OUTCOME diagnostic, not a "
        "price-pattern detection. It is research-only, runs offline, connects to "
        "nothing, and never influences a live decision, risk, or capital."
    )
    lines.append("")

    if diag.errors:
        lines.append("## Errors (failed closed)")
        lines.append("")
        for e in diag.errors:
            lines.append(f"- {e}")
        lines.append("")

    # Sample overview.
    lines.append("## Sample overview")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| total_outcomes | {diag.total_sample_count} |")
    lines.append(f"| real_outcomes | {diag.total_real_sample_count} |")
    lines.append(f"| min_sample_threshold | {diag.min_sample} |")
    lines.append(f"| setups_present | {', '.join(diag.setup_labels) or '-'} |")
    lines.append(f"| status | {diag.status} |")
    lines.append("")

    if diag.status == STATUS_INSUFFICIENT:
        lines.append(
            f"> **INSUFFICIENT_SAMPLE.** Only {diag.total_real_sample_count} real "
            f"outcome(s) (< {diag.min_sample}). Every number below is DIAGNOSTIC_ONLY "
            f"and must NOT be read as a trusted edge or strategy signal. Per-setup "
            f"win rates are withheld until the real sample is large enough."
        )
        lines.append("")

    # Per-setup table.
    lines.append("## Per-setup outcome summary")
    lines.append("")
    if diag.by_setup:
        lines.append(
            "| Setup | Samples | Real | Wins | Losses | Win rate | Avg return % "
            "| Longest win | Longest loss | data_is_real | Status |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for label, s in diag.by_setup.items():
            lines.append(
                f"| {label} | {s.sample_count} | {s.real_sample_count} | {s.win_count} "
                f"| {s.loss_count} | {_cell(s.win_rate)} | {_cell(s.average_return_pct)} "
                f"| {s.longest_win_cluster} | {s.longest_loss_cluster} "
                f"| {_md_bool(s.data_is_real)} | {s.status} |"
            )
    else:
        lines.append("_No outcome records to summarize._")
    lines.append("")

    if diag.notes:
        lines.append("## Notes")
        lines.append("")
        for n in diag.notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append(_NOT_THIS)
    lines.append("")
    lines.append(_FUTURE)
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# PatternScanReport-compatible object (rendered by research/pattern_report.py)
# --------------------------------------------------------------------------- #
def to_scan_report(diag: OutcomeDiagnostic) -> PatternScanReport:
    """Wrap the diagnostic as a PatternScanReport so pattern_report can render it.

    ``bars_analysed`` is 0 (no OHLCV) and there are NO price-pattern signals -
    only a single non-detected ``trade_outcome_clusters`` diagnostic signal whose
    evidence carries the per-setup summary. ``data_is_real`` is propagated.
    """
    insufficient = diag.status == STATUS_INSUFFICIENT
    evidence: dict[str, Any] = {
        "diagnostic_only": True,
        "status": diag.status,
        "total_sample_count": diag.total_sample_count,
        "total_real_sample_count": diag.total_real_sample_count,
        "min_sample": diag.min_sample,
        "ohlcv_used": diag.ohlcv_used,
        "by_setup": {label: asdict(s) for label, s in diag.by_setup.items()},
    }
    signal = PatternSignal(
        pattern_name="trade_outcome_clusters",
        detected=False,  # a diagnostic summary, never a "detected" price pattern
        confidence_score=0.0,
        evidence=evidence,
        required_data_quality={
            "min_sample": diag.min_sample,
            "needs_bars": False,
            "diagnostic_only": True,
        },
        missing_data=(
            (f"real_sample {diag.total_real_sample_count} < min_sample {diag.min_sample}",)
            if insufficient
            else ()
        ),
        fail_closed_reason=(
            f"{STATUS_INSUFFICIENT}: {diag.total_real_sample_count} real outcomes "
            f"< {diag.min_sample}"
            if insufficient
            else None
        ),
        data_is_real=diag.data_is_real,
    )
    return PatternScanReport(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        data_is_real=diag.data_is_real,
        input_source=diag.input_source,
        symbol="(trade-outcomes)",
        bars_analysed=diag.bars_analysed,  # 0
        config={"min_sample": diag.min_sample, "source": "trade_outcomes"},
        signals=(signal,),
        errors=diag.errors,
        notes=diag.notes,
    )


# --------------------------------------------------------------------------- #
# Fixture loading (synthetic by default)
# --------------------------------------------------------------------------- #
def load_outcomes_dataset(path: str | Path) -> tuple[list[OutcomeRecord], str, dict[str, Any]]:
    """Load a JSON dataset: {input_source?, meta?, outcomes:[{...}]}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = [outcome_record_from_dict(o) for o in data.get("outcomes", [])]
    meta = dict(data.get("meta", {}))
    input_source = str(data.get("input_source", meta.get("input_source", "fixture")))
    return records, input_source, meta


# --------------------------------------------------------------------------- #
# CLI (offline, synthetic by default)
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Offline RESEARCH-ONLY trade-outcome diagnostic (no broker, no orders). "
            "Defaults to a synthetic outcomes fixture; reads a real NovaBotV2 outcome "
            "directory ONLY when --nova-botv2-dir is given (read-only, manual)."
        )
    )
    parser.add_argument(
        "input", nargs="?", default=None,
        help="path to a synthetic outcomes fixture JSON (default source)",
    )
    parser.add_argument(
        "--nova-botv2-dir", default=None,
        help="EXPLICIT, read-only path to a real NovaBotV2 results dir (manual research only)",
    )
    parser.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument(
        "--scan-report", action="store_true",
        help="render via research/pattern_report.py (PatternScanReport-compatible path)",
    )
    args = parser.parse_args(argv)

    if args.nova_botv2_dir:
        # Explicit, manual, read-only access to real outcomes. Lazy import so the
        # default synthetic path never even imports the adapter.
        print(
            f"[research] reading NovaBotV2 outcomes READ-ONLY from {args.nova_botv2_dir} "
            f"(manual research; no writes, no broker)",
            file=sys.stderr,
        )
        from adapters.nova_botv2_trade_adapter import NovaBotV2TradeAdapter

        adapter = NovaBotV2TradeAdapter(source_dir=args.nova_botv2_dir)
        events = adapter.load()
        records = outcomes_from_events(events)
        input_source = "NovaBotV2(real,read-only)"
    elif args.input:
        records, input_source, _meta = load_outcomes_dataset(args.input)
    else:
        parser.error("provide a synthetic outcomes fixture path, or --nova-botv2-dir")
        return 2  # unreachable; parser.error exits

    diag = summarize_outcomes(records, min_sample=args.min_sample, input_source=input_source)

    if args.scan_report:
        print(build_markdown_report(to_scan_report(diag), title=args.title), end="")
    else:
        print(build_diagnostic_markdown(diag, title=args.title), end="")
    return 0 if diag.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
