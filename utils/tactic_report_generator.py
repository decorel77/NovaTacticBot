"""
Tactic Report Generator — converts AnalyticsResult into a markdown report.

Writes to data/reports/tacticbot_report.md (or a caller-specified path).
Never writes outside the NovaTacticBot directory.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.tactic_analytics_engine import AnalyticsResult

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = Path("data/reports/tacticbot_report.md")


class TacticReportGenerator:

    def generate(
        self,
        result: AnalyticsResult,
        output_path: Optional[Path] = None,
        source_description: str = "NovaBotV2Options",
    ) -> Path:
        """
        Render the AnalyticsResult to markdown and write to output_path.
        Returns the path where the report was written.
        """
        path = output_path or DEFAULT_REPORT_PATH
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        report = self._render(result, source_description)
        path.write_text(report, encoding="utf-8")
        logger.info("Report written to %s", path)
        return path

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _render(self, result: AnalyticsResult, source: str) -> str:
        sections = [
            self._header(source),
            self._executive_summary(result),
            self._strategy_analysis(result),
            self._regime_analysis(result),
            self._recommendation_quality(result),
            self._rejection_analysis(result),
            self._data_quality(result),
            self._open_questions(result),
            self._observations(result),
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

    def _open_questions(self, result: AnalyticsResult) -> str:
        if not result.open_questions:
            return ""
        lines = ["## Open Questions", ""]
        for q in result.open_questions:
            lines.append(f"- {q}")
        return "\n".join(lines)

    def _observations(self, result: AnalyticsResult) -> str:
        if not result.observations:
            return ""
        lines = ["## Observations", ""]
        for obs in result.observations:
            lines.append(f"- {obs}")
        return "\n".join(lines)

    def _footer(self) -> str:
        return (
            "---\n\n"
            "_This report is generated by NovaTacticBot. "
            "All findings are advisory only. "
            "No trades, allocations, or parameters were modified. "
            "Human review required before any action is taken._"
        )
