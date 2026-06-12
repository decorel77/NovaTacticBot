"""
Tactic Report Generator — converts AnalyticsResult into markdown reports.

Writes to data/reports/tacticbot_report.md (or a caller-specified path).
Also writes data/reports/adapter_diagnostics.md when diagnostics are provided.
Never writes outside the NovaTacticBot directory.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core.tactic_analytics_engine import AnalyticsResult

if TYPE_CHECKING:
    from adapters.nova_options_adapter import AdapterDiagnostics

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = Path("data/reports/tacticbot_report.md")
DEFAULT_DIAGNOSTICS_PATH = Path("data/reports/adapter_diagnostics.md")


class TacticReportGenerator:

    def generate(
        self,
        result: AnalyticsResult,
        output_path: Optional[Path] = None,
        source_description: str = "NovaBotV2Options",
        diagnostics: "Optional[AdapterDiagnostics]" = None,
        supplementary: "Optional[dict]" = None,
        diagnostics_path: Optional[Path] = None,
    ) -> Path:
        """
        Render the AnalyticsResult to markdown and write to output_path.
        Also writes a separate adapter_diagnostics.md when diagnostics are provided.
        Returns the path where the main report was written.
        """
        path = output_path or DEFAULT_REPORT_PATH
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        report = self._render(result, source_description, diagnostics, supplementary)
        path.write_text(report, encoding="utf-8")
        logger.info("Report written to %s", path)

        # Write separate diagnostics file
        if diagnostics is not None:
            diag_path = diagnostics_path or path.parent / DEFAULT_DIAGNOSTICS_PATH.name
            diag_path = Path(diag_path)
            diag_path.parent.mkdir(parents=True, exist_ok=True)
            diag_content = self._render_diagnostics(diagnostics, supplementary)
            diag_path.write_text(diag_content, encoding="utf-8")
            logger.info("Diagnostics report written to %s", diag_path)

        return path

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _render(
        self,
        result: AnalyticsResult,
        source: str,
        diagnostics: "Optional[AdapterDiagnostics]" = None,
        supplementary: "Optional[dict]" = None,
    ) -> str:
        sections = [
            self._header(source),
            self._executive_summary(result),
            self._symbol_concentration(result),
            self._strategy_analysis(result),
            self._regime_analysis(result),
            self._confidence_distribution(result),
            self._candidate_ranking(result),
            self._recommendation_quality(result),
            self._rejection_analysis(result),
            self._data_quality(result),
            self._supplementary_strategy_performance(supplementary),
            self._supplementary_regime_performance(supplementary),
            self._supplementary_statistical_floor(supplementary),
            self._supplementary_strategy_correlation(supplementary),
            self._tactical_observations(result),
            self._open_questions(result),
            self._footer(),
        ]
        return "\n\n".join(s for s in sections if s)

    # ── Sections ───────────────────────────────────────────────────────────────

    def _header(self, source: str) -> str:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"# NovaTacticBot Intelligence Report\n\n"
            f"**Generated:** {ts}  \n"
            f"**Source:** {source}  \n"
            f"**Mode:** ADVISORY ONLY — no trades, no modifications  "
        )

    def _executive_summary(self, result: AnalyticsResult) -> str:
        dq = result.data_quality
        total = dq.total_events
        strategy_count = len(result.strategy_stats)
        regime_count = len(result.regime_stats)

        overall_wins = sum(s.wins for s in result.strategy_stats.values())
        overall_trades = sum(s.trade_outcomes for s in result.strategy_stats.values())
        overall_pnl = sum(s.total_pnl for s in result.strategy_stats.values())
        overall_wr = f"{overall_wins / overall_trades:.1%}" if overall_trades else "N/A"

        lines = [
            "## Executive Summary",
            "",
            f"- **Total events loaded:** {total}",
            f"- **Strategies observed:** {strategy_count}",
            f"- **Regimes observed:** {regime_count}",
            f"- **Completed trades:** {overall_trades}",
            f"- **Overall win rate:** {overall_wr}",
            f"- **Total realized PnL:** ${overall_pnl:,.2f}",
        ]
        if result.observations:
            lines += ["", f"- **Key observations:** {len(result.observations)} (see Observations section)"]
        if result.open_questions:
            lines += [f"- **Open questions:** {len(result.open_questions)} (see Open Questions section)"]
        return "\n".join(lines)

    def _strategy_analysis(self, result: AnalyticsResult) -> str:
        if not result.strategy_stats:
            return "## Strategy Analysis\n\n_No strategy data available._"

        lines = [
            "## Strategy Analysis",
            "",
            "| Strategy | Trades | Win Rate | Avg PnL | Avg Score | Avg E[R/R] | Top Regime |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in sorted(result.strategy_stats.values(), key=lambda x: -(x.trade_outcomes or 0)):
            wr = f"{s.win_rate:.1%}" if s.win_rate is not None else "—"
            avg_pnl = f"${s.avg_realized_pnl:+.2f}" if s.avg_realized_pnl is not None else "—"
            avg_score = f"{s.avg_score:.2f}" if s.avg_score is not None else "—"
            avg_rr = f"{s.avg_expected_rr:.2f}" if s.avg_expected_rr is not None else "—"
            top_regime = max(s.regimes, key=s.regimes.get) if s.regimes else "—"
            lines.append(
                f"| {s.strategy_id} | {s.trade_outcomes} | {wr} | {avg_pnl} "
                f"| {avg_score} | {avg_rr} | {top_regime} |"
            )
        return "\n".join(lines)

    def _regime_analysis(self, result: AnalyticsResult) -> str:
        if not result.regime_stats:
            return "## Regime Analysis\n\n_No regime data available._"

        lines = [
            "## Regime Analysis",
            "",
            "| Regime | Events | Trades | Win Rate | Avg PnL | Top Strategy |",
            "|---|---|---|---|---|---|",
        ]
        for r in sorted(result.regime_stats.values(), key=lambda x: -x.total_events):
            wr = f"{r.win_rate:.1%}" if r.win_rate is not None else "—"
            avg_pnl = f"${r.avg_pnl:+.2f}" if r.avg_pnl is not None else "—"
            top_strategy = max(r.strategies, key=r.strategies.get) if r.strategies else "—"
            lines.append(
                f"| {r.regime} | {r.total_events} | {r.trade_outcomes} "
                f"| {wr} | {avg_pnl} | {top_strategy} |"
            )
        return "\n".join(lines)

    def _recommendation_quality(self, result: AnalyticsResult) -> str:
        rq = result.recommendation_quality
        lines = [
            "## Recommendation Quality",
            "",
            f"- **Total recommendations:** {rq.total_recommendations}",
            f"- **Scored trade outcomes:** {rq.scored_recommendations}",
        ]
        if rq.avg_score is not None:
            lines.append(f"- **Average score:** {rq.avg_score:.3f}")
        if rq.high_score_win_rate is not None:
            lines.append(f"- **Win rate (score ≥ 0.7):** {rq.high_score_win_rate:.1%}")
        if rq.low_score_win_rate is not None:
            lines.append(f"- **Win rate (score < 0.5):** {rq.low_score_win_rate:.1%}")
        if rq.avg_score is None and rq.total_recommendations == 0:
            lines.append("\n_No recommendation quality data available._")
        return "\n".join(lines)

    def _rejection_analysis(self, result: AnalyticsResult) -> str:
        rs = result.rejection_stats
        lines = [
            "## Rejection Analysis",
            "",
            f"- **Total rejections:** {rs.total_rejections}",
        ]
        if rs.rejection_rate is not None:
            lines.append(f"- **Rejection rate:** {rs.rejection_rate:.1%} of actionable signals")
        if rs.by_strategy:
            lines += ["", "**Rejections by strategy:**", ""]
            for sid, count in sorted(rs.by_strategy.items(), key=lambda x: -x[1]):
                lines.append(f"- {sid}: {count}")
        if rs.by_regime:
            lines += ["", "**Rejections by regime:**", ""]
            for regime, count in sorted(rs.by_regime.items(), key=lambda x: -x[1]):
                lines.append(f"- {regime}: {count}")
        if rs.total_rejections == 0:
            lines.append("\n_No rejection events found in data._")
        return "\n".join(lines)

    def _data_quality(self, result: AnalyticsResult) -> str:
        dq = result.data_quality
        total = dq.total_events or 1  # avoid div/zero in report
        lines = [
            "## Data Quality",
            "",
            f"- **Total events:** {dq.total_events}",
            f"- **Missing regime:** {dq.missing_regime} ({dq.missing_regime / total:.0%})",
            f"- **Missing score:** {dq.missing_score} ({dq.missing_score / total:.0%})",
            f"- **Missing PnL:** {dq.missing_pnl} ({dq.missing_pnl / total:.0%})",
            f"- **Missing outcome:** {dq.missing_outcome} ({dq.missing_outcome / total:.0%})",
            f"- **Malformed events skipped:** {dq.malformed_events}",
        ]
        if dq.source_bot_counts:
            lines += ["", "**Events by source bot:**", ""]
            for bot, count in sorted(dq.source_bot_counts.items()):
                lines.append(f"- {bot}: {count}")
        return "\n".join(lines)

    def _symbol_concentration(self, result: AnalyticsResult) -> str:
        sc = result.symbol_concentration
        if not sc.by_symbol:
            return ""
        lines = [
            "## Symbol Concentration",
            "",
            "| Symbol | Total Events | Outcomes | Rejections | Total PnL |",
            "|---|---|---|---|---|",
        ]
        for sym in sc.top_symbols[:15]:
            outcomes = sc.outcomes_by_symbol.get(sym, 0)
            rejections = sc.rejections_by_symbol.get(sym, 0)
            pnl = sc.pnl_by_symbol.get(sym)
            pnl_str = f"${pnl:+.2f}" if pnl is not None else "—"
            lines.append(f"| {sym} | {sc.by_symbol[sym]} | {outcomes} | {rejections} | {pnl_str} |")
        return "\n".join(lines)

    def _confidence_distribution(self, result: AnalyticsResult) -> str:
        cd = result.confidence_distribution
        if not cd.buckets or cd.total_scored == 0:
            return ""
        lines = [
            "## Confidence (Score) Distribution",
            "",
            f"_Total scored events: {cd.total_scored}"
            + (f" | Average score: {cd.avg_score:.3f}" if cd.avg_score is not None else "")
            + "_",
            "",
            "| Score Range | Events | Win Rate |",
            "|---|---|---|",
        ]
        for b in cd.buckets:
            wr = f"{b.win_rate:.1%}" if b.win_rate is not None else "—"
            lines.append(f"| {b.label} | {b.count} | {wr} |")
        return "\n".join(lines)

    def _candidate_ranking(self, result: AnalyticsResult) -> str:
        ranking = result.candidate_ranking
        if not ranking.candidates:
            return ""
        lines = [
            "## Candidate Ranking",
            "",
            "_Ranked by composite score (avg_score × win_rate). Advisory only._",
            "",
            "| Rank | Symbol | Strategy | Composite | Events | Win Rate | Avg PnL | Avg Score |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, c in enumerate(ranking.candidates[:10], 1):
            wr = f"{c.win_rate:.1%}" if c.win_rate is not None else "—"
            pnl = f"${c.avg_pnl:+.2f}" if c.avg_pnl is not None else "—"
            sc = f"{c.avg_score:.3f}" if c.avg_score is not None else "—"
            lines.append(
                f"| {i} | {c.symbol} | {c.strategy_id} | {c.composite_score:.3f} "
                f"| {c.total_events} | {wr} | {pnl} | {sc} |"
            )
        return "\n".join(lines)

    def _tactical_observations(self, result: AnalyticsResult) -> str:
        lines = []
        if result.observations:
            lines += ["## Tactical Observations", ""]
            for obs in result.observations:
                lines.append(f"- {obs}")
        return "\n".join(lines) if lines else ""

    def _open_questions(self, result: AnalyticsResult) -> str:
        if not result.open_questions:
            return ""
        lines = ["## Open Questions / Missing Data Warnings", ""]
        for q in result.open_questions:
            lines.append(f"- {q}")
        return "\n".join(lines)

    def _render_diagnostics(
        self,
        diagnostics: "AdapterDiagnostics",
        supplementary: "Optional[dict]" = None,
    ) -> str:
        """Render a standalone adapter_diagnostics.md report."""
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        sections = [
            f"# NovaTacticBot — Adapter Diagnostics\n\n"
            f"**Generated:** {ts}  \n"
            f"**Source directory:** `{diagnostics.source_dir}`  \n"
            f"**Mode:** ADVISORY ONLY",
            self._diagnostics_summary(diagnostics),
            self._diagnostics_files(diagnostics),
            self._diagnostics_records(diagnostics),
            self._diagnostics_errors(diagnostics),
            self._diagnostics_lifecycle(supplementary),
            "---\n\n_NovaTacticBot diagnostics — no trades, no modifications made._",
        ]
        return "\n\n".join(s for s in sections if s)

    def _diagnostics_summary(self, diagnostics: "AdapterDiagnostics") -> str:
        return "\n".join([
            "## Summary",
            "",
            f"- **Events parsed:** {diagnostics.events_parsed}",
            f"- **Records skipped:** {diagnostics.records_skipped}",
            f"- **Files found:** {len(diagnostics.files_found)}",
            f"- **Files missing:** {len(diagnostics.files_missing)}",
            f"- **Schema mismatches:** {len(diagnostics.schema_mismatches)}",
            f"- **Parse errors:** {len(diagnostics.parse_errors)}",
        ])

    def _diagnostics_files(self, diagnostics: "AdapterDiagnostics") -> str:
        lines = ["## Files Discovered"]
        if diagnostics.files_found:
            lines += ["", "**Found (parsed):**"]
            for f in diagnostics.files_found:
                lines.append(f"  - `{f}` ✓")
        if diagnostics.files_missing:
            lines += ["", "**Missing (expected but not found):**"]
            for f in diagnostics.files_missing:
                lines.append(f"  - `{f}` ✗")
        if diagnostics.files_skipped:
            lines += ["", "**Skipped:**"]
            for f in diagnostics.files_skipped:
                lines.append(f"  - `{f}`")
        if diagnostics.source_breakdown:
            lines += ["", "**Events by source file:**"]
            for src, cnt in sorted(diagnostics.source_breakdown.items()):
                lines.append(f"  - {src}: {cnt}")
        return "\n".join(lines)

    def _diagnostics_records(self, diagnostics: "AdapterDiagnostics") -> str:
        lines = ["## Records Parsed"]
        lines += [
            "",
            f"- **Total events produced:** {diagnostics.events_parsed}",
            f"- **Records skipped (duplicates / malformed):** {diagnostics.records_skipped}",
        ]
        if diagnostics.schema_mismatches:
            lines += ["", f"**Schema mismatches ({len(diagnostics.schema_mismatches)}):**"]
            for m in diagnostics.schema_mismatches[:20]:
                lines.append(f"  - {m}")
            if len(diagnostics.schema_mismatches) > 20:
                lines.append(f"  - … and {len(diagnostics.schema_mismatches) - 20} more")
        return "\n".join(lines)

    def _diagnostics_errors(self, diagnostics: "AdapterDiagnostics") -> str:
        if not diagnostics.parse_errors:
            return "## Parse Failures\n\n_None — all files parsed cleanly._"
        lines = [f"## Parse Failures ({len(diagnostics.parse_errors)})", ""]
        for e in diagnostics.parse_errors[:20]:
            lines.append(f"- {e}")
        if len(diagnostics.parse_errors) > 20:
            lines.append(f"- … and {len(diagnostics.parse_errors) - 20} more")
        return "\n".join(lines)

    def _diagnostics_lifecycle(self, supplementary: "Optional[dict]") -> str:
        if not supplementary:
            return ""
        lc = supplementary.get("lifecycle_summary", {})
        if not lc:
            return ""
        total = lc.get("total_signals", "?")
        by_status = lc.get("by_status", {})
        lines = ["## Signal Lifecycle Summary", "", f"- **Total signals:** {total}"]
        for status, cnt in sorted(by_status.items()):
            lines.append(f"- **{status}:** {cnt}")
        return "\n".join(lines)

    def _adapter_diagnostics(self, diagnostics: "Optional[AdapterDiagnostics]") -> str:
        if diagnostics is None:
            return ""
        lines = [
            "## Adapter Diagnostics",
            "",
            f"- **Source directory:** `{diagnostics.source_dir}`",
            f"- **Events parsed:** {diagnostics.events_parsed}",
            f"- **Records skipped:** {diagnostics.records_skipped}",
        ]
        if diagnostics.files_found:
            lines += ["", "**Files found:**"]
            for f in diagnostics.files_found:
                lines.append(f"  - `{f}` ✓")
        if diagnostics.files_missing:
            lines += ["", "**Files missing:**"]
            for f in diagnostics.files_missing:
                lines.append(f"  - `{f}` ✗")
        if diagnostics.source_breakdown:
            lines += ["", "**Events by source:**"]
            for src, cnt in sorted(diagnostics.source_breakdown.items()):
                lines.append(f"  - {src}: {cnt}")
        if diagnostics.schema_mismatches:
            lines += ["", f"**Schema mismatches ({len(diagnostics.schema_mismatches)}):**"]
            for m in diagnostics.schema_mismatches[:10]:
                lines.append(f"  - {m}")
            if len(diagnostics.schema_mismatches) > 10:
                lines.append(f"  - … and {len(diagnostics.schema_mismatches) - 10} more")
        if diagnostics.parse_errors:
            lines += ["", f"**Parse errors ({len(diagnostics.parse_errors)}):**"]
            for e in diagnostics.parse_errors[:5]:
                lines.append(f"  - {e}")
        return "\n".join(lines)

    def _supplementary_strategy_performance(self, supplementary: "Optional[dict]") -> str:
        if not supplementary:
            return ""
        strat = supplementary.get("strategy_performance", {}).get("strategies", {})
        if not strat:
            return ""
        lines = [
            "## NovaBotV2Options Strategy Performance (Pre-Computed)",
            "",
            "_Source: `data/reports/strategy_performance.json` — advisory only_",
            "",
            "| Strategy | Trades | Wins | Losses | Win Rate | Avg PnL | Total PnL |",
            "|---|---|---|---|---|---|---|",
        ]
        for sid, s in strat.items():
            wr = f"{s.get('win_rate', 0):.1%}"
            avg_pnl = f"${s.get('avg_pnl', 0):+.2f}"
            total_pnl = f"${s.get('total_pnl', 0):+.2f}"
            lines.append(
                f"| {sid} | {s.get('trade_count', 0)} | {s.get('win_count', 0)} "
                f"| {s.get('loss_count', 0)} | {wr} | {avg_pnl} | {total_pnl} |"
            )
        return "\n".join(lines)

    def _supplementary_regime_performance(self, supplementary: "Optional[dict]") -> str:
        if not supplementary:
            return ""
        buckets = supplementary.get("regime_performance", {}).get("buckets", {})
        if not buckets:
            return ""
        lines = [
            "## NovaBotV2Options Regime Performance (Pre-Computed)",
            "",
            "_Source: `data/reports/regime_performance.json` — advisory only_",
            "",
            "| Regime | Vol Env | Signals | Trades | Win Rate | Avg PnL | Reject Rate |",
            "|---|---|---|---|---|---|---|",
        ]
        for bucket_key, b in sorted(buckets.items()):
            wr = f"{b.get('win_rate', 0):.1%}"
            avg_pnl = f"${b.get('avg_pnl', 0):+.2f}"
            reject_rate = f"{b.get('rejection_rate', 0):.0%}"
            lines.append(
                f"| {b.get('regime', '?')} | {b.get('vol_env', '?')} "
                f"| {b.get('signals_created', 0)} | {b.get('trade_count', 0)} "
                f"| {wr} | {avg_pnl} | {reject_rate} |"
            )
        return "\n".join(lines)

    def _supplementary_statistical_floor(self, supplementary: "Optional[dict]") -> str:
        if not supplementary or "statistical_floor" not in supplementary:
            return ""
        floor = supplementary.get("statistical_floor")
        if isinstance(floor, dict):
            entries = floor.get("signals", [])
        else:
            entries = floor
        if not isinstance(entries, list) or not entries:
            return "\n".join([
                "## Statistical Floor (QA-016)",
                "",
                "**DIAGNOSTIC_ONLY** - no statistical floor evidence supplied; "
                "no signal may be labelled STRONG.",
            ])

        lines = [
            "## Statistical Floor (QA-016)",
            "",
            "_Advisory labels only. This section cannot approve execution, size, or allocation changes._",
            "",
            "| Signal | Strategy | Samples | Strength | Refusals |",
            "|---|---|---|---|---|",
        ]
        for entry in entries:
            if not isinstance(entry, dict):
                lines.append("| unknown | unknown | N/A | DIAGNOSTIC_ONLY | malformed_floor_entry |")
                continue
            metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
            refusals = entry.get("refusal_reasons") or []
            if not isinstance(refusals, list):
                refusals = [str(refusals)]
            requested_strength = str(entry.get("strength") or "DIAGNOSTIC_ONLY")
            strength = "DIAGNOSTIC_ONLY"
            if (
                requested_strength == "STRONG"
                and entry.get("approved") is True
                and entry.get("diagnostic_only") is False
                and not refusals
            ):
                strength = "STRONG"
            lines.append(
                f"| {entry.get('signal_id') or 'unknown'} "
                f"| {entry.get('strategy_id') or 'unknown'} "
                f"| {metrics.get('sample_size', 'N/A')} "
                f"| {strength} "
                f"| {', '.join(str(item) for item in refusals) or 'none'} |"
            )
        return "\n".join(lines)

    def _supplementary_strategy_correlation(self, supplementary: "Optional[dict]") -> str:
        if not supplementary or "strategy_correlation" not in supplementary:
            return ""
        correlation = supplementary.get("strategy_correlation")
        if not isinstance(correlation, dict):
            return "\n".join([
                "## Strategy Outcome Correlation (QA-019)",
                "",
                "**INSUFFICIENT SAMPLE - no correlation value is reported.** "
                "Reasons: malformed_correlation_payload",
            ])

        source_a = correlation.get("source_a", "NovaBotV2")
        source_b = correlation.get("source_b", "NovaBotV2Options")
        overlap_days = correlation.get("overlap_days", 0)
        refusal_reasons = correlation.get("refusal_reasons") or []
        warnings = correlation.get("warnings") or []
        caveats = correlation.get("caveats") or []
        if not isinstance(refusal_reasons, list):
            refusal_reasons = [str(refusal_reasons)]
        if not isinstance(warnings, list):
            warnings = [str(warnings)]
        if not isinstance(caveats, list):
            caveats = [str(caveats)]

        lines = [
            "## Strategy Outcome Correlation (QA-019)",
            "",
            f"Streams: `{source_a}` vs `{source_b}` ({overlap_days} overlapping outcome days)",
            "",
        ]
        value = correlation.get("correlation")
        if correlation.get("insufficient_sample", True) or value is None:
            lines.append(
                "**INSUFFICIENT SAMPLE - no correlation value is reported.** "
                "Reasons: " + (", ".join(str(item) for item in refusal_reasons) or "none recorded")
            )
        else:
            interval = ""
            if correlation.get("ci_low") is not None and correlation.get("ci_high") is not None:
                interval = f" (95% CI [{correlation['ci_low']:+.2f}, {correlation['ci_high']:+.2f}])"
            lines.append(f"Daily realized-PnL correlation: **{float(value):+.2f}**{interval}")
        if warnings:
            lines += ["", "Warnings: " + ", ".join(str(item) for item in warnings)]
        if caveats:
            lines += ["", "Caveats:"]
            for caveat in caveats:
                lines.append(f"- {caveat}")
        return "\n".join(lines)

    def _footer(self) -> str:
        return (
            "---\n\n"
            "_This report is generated by NovaTacticBot. "
            "All findings are advisory only. "
            "No trades, allocations, or parameters were modified. "
            "Human review required before any action is taken._"
        )
