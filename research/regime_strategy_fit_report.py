"""Research-only Markdown renderer for RegimeStrategyFit (TACTIC-RA-003 report layer).

A thin, research-only **formatting** layer over ``research/regime_strategy_fit.py``.
It adds **no** capability: no broker / data-feed / network access, no risk/capital
settings, and no writes (it returns a string). It is **not** wired into
``tools/run_tacticbot.py`` or any scheduler.

It renders the diagnostic-only fit matrix as **ASCII-safe** Markdown. Withheld
(below sample-floor) cells render as ``INSUFFICIENT_SAMPLE``; ``status`` and
``data_is_real`` are taken **verbatim** from the fit and never upgraded. The
output is descriptive evidence only and explicitly **not trading advice**.
"""
from __future__ import annotations

from research.regime_strategy_fit import STATUS_INSUFFICIENT, RegimeStrategyFit

DEFAULT_TITLE: str = "NovaTacticBot - Regime x Strategy Fit (Research-Only)"


def _bool(value: object) -> str:
    return "true" if bool(value) else "false"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _rate_cell(win_rate: float | None) -> str:
    return _pct(win_rate) if win_rate is not None else STATUS_INSUFFICIENT


def build_markdown(
    fit: RegimeStrategyFit,
    *,
    title: str = DEFAULT_TITLE,
    generated_at: str | None = None,
) -> str:
    """Render a ``RegimeStrategyFit`` as a research-only, ASCII-safe Markdown report.

    Fails closed: when ``fit.errors`` is set, only the metadata block and an
    errors section are rendered (no tables). All printed text is ASCII so the
    report renders on any console codepage and in redirected pipelines.
    """
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    if generated_at is not None:
        lines.append(f"- **generated_at:** {generated_at}")
    lines.append("- **research_only:** true")
    lines.append("- **diagnostic_only:** true")
    lines.append(f"- **status:** {fit.status}")
    lines.append(f"- **data_is_real:** {_bool(fit.data_is_real)}")
    lines.append(f"- **broker_execution:** {fit.broker_execution}")
    lines.append(f"- **min_sample_threshold:** {fit.min_sample}")
    lines.append("")
    lines.append(
        "> **Not trading advice.** This is a descriptive regime x strategy tally, "
        "not a strategy edge and not a trade signal. It is research-only, runs "
        "offline, connects to nothing, and never influences a live decision, "
        "risk, or capital."
    )
    lines.append("")

    if fit.errors:
        lines.append("## Errors (failed closed)")
        lines.append("")
        for err in fit.errors:
            lines.append(f"- {err}")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    # Overview.
    lines.append("## Overview")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| total_events | {fit.total_events} |")
    lines.append(f"| total_decisive | {fit.total_decisive} |")
    lines.append(f"| regimes | {', '.join(fit.regimes) or '-'} |")
    lines.append(f"| strategies | {', '.join(fit.strategies) or '-'} |")
    lines.append(f"| status | {fit.status} |")
    lines.append("")

    if fit.status == STATUS_INSUFFICIENT:
        lines.append(
            "> **INSUFFICIENT_SAMPLE.** Decisive outcomes are below the sample "
            "floor; per-cell win rates are withheld and nothing here is a trusted edge."
        )
        lines.append("")

    # Per-cell table.
    lines.append("## Per-cell summary")
    lines.append("")
    if fit.cells:
        lines.append(
            "| Regime | Strategy | Events | Decisive | Wins | Losses | Win rate | Status |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for key in sorted(fit.cells):
            c = fit.cells[key]
            lines.append(
                f"| {c.regime} | {c.strategy_id} | {c.total_events} | {c.sample_count} "
                f"| {c.wins} | {c.losses} | {_rate_cell(c.win_rate)} | {c.status} |"
            )
    else:
        lines.append("_No cells to summarize._")
    lines.append("")

    # Win-rate grid (regime rows x strategy columns).
    if fit.strategies and fit.regimes:
        lines.append("## Win-rate grid (regime x strategy)")
        lines.append("")
        lines.append(
            "Cells show a win rate only at/above the sample floor; a below-floor "
            "cell shows INSUFFICIENT_SAMPLE and a missing pair shows `-`."
        )
        lines.append("")
        lines.append("| Regime \\ Strategy | " + " | ".join(fit.strategies) + " |")
        lines.append("|---" * (len(fit.strategies) + 1) + "|")
        for regime in fit.regimes:
            row = [regime]
            for strat in fit.strategies:
                c = fit.cells.get(RegimeStrategyFit.cell_key(regime, strat))
                if c is None:
                    row.append("-")
                elif c.win_rate is not None:
                    row.append(f"{_pct(c.win_rate)} (n={c.sample_count})")
                else:
                    row.append(f"INSUFFICIENT_SAMPLE (n={c.sample_count})")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    if fit.notes:
        lines.append("## Notes")
        lines.append("")
        for note in fit.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
