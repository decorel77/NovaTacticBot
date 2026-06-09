"""
TacticBot HTML dashboard generator.

Renders an AnalyticsResult to a self-contained HTML file at
data/reports/tactic_dashboard.html.

Sections:
  1. Strategy performance table (win rate, PnL, streak status)
  2. Regime breakdown table
  3. Edge erosion warnings
  4. Recommendation quality summary

No broker imports. ADVISORY_ONLY. Writes to data/reports/ only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.tactic_analytics_engine import AnalyticsResult

_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
_DASHBOARD_FILE = _DEFAULT_REPORTS_DIR / "tactic_dashboard.html"


def _pct(value: Optional[float]) -> str:
    return f"{value:.1%}" if value is not None else "—"


def _fmt(value: Optional[float], decimals: int = 2) -> str:
    return f"{value:.{decimals}f}" if value is not None else "—"


def _strategy_table(result: AnalyticsResult) -> str:
    rows = []
    streak_flags = result.streak_analysis.flagged_strategies
    erosion_ids = {w.strategy_id for w in result.edge_erosion.warnings}

    for sid, s in sorted(result.strategy_stats.items()):
        flags = []
        if sid in streak_flags:
            flags.append('<span class="badge loss">LOSS STREAK</span>')
        if sid in erosion_ids:
            flags.append('<span class="badge erosion">EDGE EROSION</span>')
        flag_str = " ".join(flags) if flags else ""
        rows.append(
            f"<tr><td>{sid}</td><td>{s.total_events}</td><td>{s.trade_outcomes}</td>"
            f"<td>{_pct(s.win_rate)}</td><td>{_fmt(s.avg_realized_pnl)}</td>"
            f"<td>{_pct(s.avg_score)}</td><td>{flag_str}</td></tr>"
        )

    header = (
        "<tr><th>Strategy</th><th>Events</th><th>Outcomes</th>"
        "<th>Win Rate</th><th>Avg PnL</th><th>Avg Score</th><th>Flags</th></tr>"
    )
    return f"<table>{header}{''.join(rows)}</table>" if rows else "<p>No strategy data.</p>"


def _regime_table(result: AnalyticsResult) -> str:
    rows = []
    for rid, r in sorted(result.regime_stats.items()):
        rows.append(
            f"<tr><td>{rid}</td><td>{r.total_events}</td><td>{r.trade_outcomes}</td>"
            f"<td>{_pct(r.win_rate)}</td><td>{_fmt(r.avg_pnl)}</td></tr>"
        )
    header = "<tr><th>Regime</th><th>Events</th><th>Outcomes</th><th>Win Rate</th><th>Avg PnL</th></tr>"
    return f"<table>{header}{''.join(rows)}</table>" if rows else "<p>No regime data.</p>"


def _erosion_section(result: AnalyticsResult) -> str:
    if not result.edge_erosion.warnings:
        return "<p class='ok'>No edge erosion warnings.</p>"
    items = []
    for w in result.edge_erosion.warnings:
        items.append(
            f"<li><strong>{w.strategy_id}</strong>: rolling {_pct(w.rolling_win_rate)} "
            f"vs baseline {_pct(w.baseline_win_rate)} "
            f"(drop: {_pct(w.drop_pp)})</li>"
        )
    return f"<ul class='warn'>{''.join(items)}</ul>"


def _quality_section(result: AnalyticsResult) -> str:
    rq = result.recommendation_quality
    lines = [
        f"<li>Total recommendations: {rq.total_recommendations}</li>",
        f"<li>Avg score: {_pct(rq.avg_score)}</li>",
        f"<li>High-score win rate (≥0.7): {_pct(rq.high_score_win_rate)}</li>",
        f"<li>Low-score win rate (&lt;0.5): {_pct(rq.low_score_win_rate)}</li>",
    ]
    return f"<ul>{''.join(lines)}</ul>"


CSS = """
body { font-family: sans-serif; max-width: 960px; margin: 2em auto; color: #222; }
h1 { color: #1a1a6e; }
h2 { border-bottom: 1px solid #ccc; padding-bottom: 4px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 1em; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
th { background: #f0f0f0; }
tr:nth-child(even) { background: #fafafa; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
.badge.loss { background: #ffd0d0; color: #900; }
.badge.erosion { background: #fff0c0; color: #660; }
.warn li { color: #c00; }
.ok { color: #060; }
"""


def render(result: AnalyticsResult, title: str = "NovaTacticBot Analytics Dashboard") -> str:
    """Return a self-contained HTML string for the given AnalyticsResult."""
    total = result.data_quality.total_events
    obs_items = "".join(f"<li>{o}</li>" for o in result.observations) or "<li>None</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<h1>{title}</h1>
<p><strong>Total events analysed:</strong> {total}</p>

<h2>1. Strategy Performance</h2>
{_strategy_table(result)}

<h2>2. Regime Breakdown</h2>
{_regime_table(result)}

<h2>3. Edge Erosion Warnings</h2>
{_erosion_section(result)}

<h2>4. Recommendation Quality</h2>
{_quality_section(result)}

<h2>5. Observations</h2>
<ul>{obs_items}</ul>
</body>
</html>"""
    return html


class TacticHtmlDashboard:
    """Writes the TacticBot HTML dashboard to data/reports/tactic_dashboard.html."""

    def __init__(self, output_file: Optional[Path] = None) -> None:
        self._file = output_file or _DASHBOARD_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def write(self, result: AnalyticsResult) -> Path:
        html = render(result)
        self._file.write_text(html, encoding="utf-8")
        return self._file
