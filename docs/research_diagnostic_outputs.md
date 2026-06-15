# NovaTacticBot — Research-Only Diagnostic Outputs

**Status:** research-only / diagnostic-only reference for the `research/` output layer
**Audience:** anyone reading or extending TacticBot's offline analytics exports

This note documents the research-only modules that turn analytics into structured
or human-readable diagnostic output. They are deliberately separate from the
runtime: none of them is imported by `tools/run_tacticbot.py`, the analytics
engine, or any scheduler, and a `SafetyTests` case in each module's test file
pins that fact.

> **Permanent contract.** TacticBot is `ADVISORY_ONLY = True`: it observes and
> reports, it never acts. Everything below is descriptive evidence — never a
> forecast, an edge, a trade signal, or any trading/allocation/risk/capital
> authority.

## Shared safety contract

Every module in this layer is:

- **research-only / diagnostic-only** — descriptive tallies and serializations,
  no recommendation, no optimization, no forecast;
- **unwired** — not imported by the runner or any scheduler (enforced by tests);
- **broker-free** — imports no broker / order / live-cycle / scheduler / network /
  subprocess module (only stdlib + core TacticBot types);
- **fail-closed** — empty/missing/malformed/degenerate input yields an error
  result with no fabricated numbers (e.g. `NaN` PnL is skipped; an invalid
  holding span is skipped, never made negative);
- **sample-aware** — below the documented `min_sample = 30` real-outcome floor
  (the NEXT-016 gate) a rate is withheld and/or the status is
  `INSUFFICIENT_SAMPLE`; a number is never upgraded to a trusted edge;
- **provenance-honest** — `data_is_real` is propagated verbatim from the caller
  (default `False`) and never invented; mixed/unknown provenance stays untrusted.

## Modules

### Structured export

- `research/analytics_json_export.py` — `result_to_dict(result, *, data_is_real=False, generated_at=None)`
  and `to_json(...)` serialize an `AnalyticsResult` (from `core/tactic_analytics_engine.py`)
  into a deterministic, ASCII-safe JSON document (`{"meta": ..., "analytics": ...}`).
  The structured-export sibling of `utils/tactic_report_generator.py`'s Markdown.
- `research/analytics_json_export_cli.py` — offline, **synthetic-only** CLI: loads a
  synthetic events fixture, runs the engine, and prints the JSON export to stdout.
  It writes nothing by default, has **no** real-directory option, always reports
  `data_is_real=false`, and fails closed (exit 2) on a missing/malformed fixture.

### Regime × strategy fit (TACTIC-RA-003)

- `research/regime_strategy_fit.py` — `build_regime_strategy_fit(events, *, min_sample=30, data_is_real=False)`
  builds a regime × strategy fit matrix. Per-cell win rate is **withheld below the
  sample floor** (`INSUFFICIENT_SAMPLE`); unknown/None regimes fail closed to a
  known `UNKNOWN` bucket.
- `research/regime_strategy_fit_report.py` — `build_markdown(fit, ...)` renders the
  matrix as ASCII-safe Markdown (per-cell table + win-rate grid). Withheld cells
  render `INSUFFICIENT_SAMPLE`; the report carries a "not trading advice" disclaimer.
- `research/regime_strategy_fit_json.py` — `fit_to_dict(fit, ...)` / `to_json(...)`
  serialize the matrix; a withheld cell serializes `win_rate: null`.

### Descriptive distributions

- `research/pnl_distribution.py` (TACTIC-HA-006) — `build_pnl_distribution(events, ...)`
  returns a descriptive realized-PnL distribution: histogram buckets,
  count/mean/median/min/max/stdev, a win/loss/breakeven split, and a per-strategy
  summary. `NaN` PnL is skipped; empty/no-PnL input fails closed.
- `research/holding_period_analytics.py` (TACTIC-HA-007) — `build_holding_period_analysis(events, ...)`
  summarizes trade holding periods (in days) from `entry_time` / `exit_time` in
  event metadata. Missing/unparseable timestamps and non-positive (or mismatched
  tz-awareness) spans are skipped and counted — never fabricated.

### Broader research family (context)

`research/pattern_recognition.py`, `research/pattern_report.py`,
`research/pattern_outcome_bridge.py`, and `research/stock_tactics_backtest.py`
are the price-pattern and trade-outcome research modules. They share the same
research-only, fail-closed, sample-gated contract and are documented in
`docs/pattern_recognition_research.md`.

## Running the offline export (synthetic only)

```powershell
cd C:\NovaGPT\Apps\NovaTacticBot
# inside the broker-free venv:
.\.venv\Scripts\python.exe -m research.analytics_json_export_cli `
    tests\fixtures\analytics\events_synthetic.json
```

The CLI reads only the synthetic fixture, prints JSON to stdout, and never asserts
realness. There is no option to point it at a real bot directory.

## Promotion path (before any runtime/report wiring)

Surfacing any of these outputs inside the runner, NovaBridge, or a generated report
is a **separate, human-reviewed promotion** — never an implicit import. Before that:

1. **Real, labeled, out-of-sample data** at sufficient sample size — every checked-in
   fixture is synthetic. Per-setup/per-cell conclusions need ≥30 real deduplicated
   outcomes (the NEXT-016 gate), which the live outcome stream does not yet meet.
2. **Statistical validation** and **calibration** before any number is treated as
   more than a transparent descriptive figure.
3. A **deliberate, reviewed change** to wire the output read-only into a report —
   and even then it stays descriptive and never gains broker / order / risk /
   capital / allocation authority.
