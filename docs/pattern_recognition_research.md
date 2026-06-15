# Pattern Recognition (Research-Only Prototype)

**Module:** `research/pattern_recognition.py` (+ `research/__init__.py`)
**Status:** research-only, **not wired** into the advisory runner or any scheduler.
**Tests:** `tests/test_pattern_recognition.py`, fixtures in `tests/fixtures/patterns/`.
**Companion:** shares the OHLC validation and setup-label vocabulary of
`research/stock_tactics_backtest.py` (see `docs/NEXT_015_stock_tactics_backtest_harness.md`).

## What this is

A deterministic, fixture-driven scanner that looks at a single symbol's daily
OHLC(V) series (and, optionally, a list of labeled trade outcomes) and reports
which simple, **explainable** setups are present in the most recent window. It
is a *research microscope*, not a trading system: it produces descriptive
evidence, never a trade instruction.

Each detector returns a `PatternSignal` carrying the safety contract Nova asked
for:

| Field | Meaning |
|---|---|
| `pattern_name` | which detector produced the verdict |
| `detected` | whether the rule fired |
| `confidence_score` | `0.0`–`1.0`; `0.0` when not detected or failed closed |
| `evidence` | the explainable numbers behind the verdict |
| `required_data_quality` | what the detector assumed (min bars, needs_volume, window) |
| `missing_data` | which required inputs were absent/insufficient |
| `fail_closed_reason` | set (with `detected=False`) when the rule could not run |
| `research_only` | always `True` |
| `data_is_real` | propagated from the caller; forced `False` on any fail-closed signal |

`scan_patterns(...)` runs every price detector and aggregates them into a
`PatternScanReport` with run-level `research_only`, `broker_execution="disabled"`,
`data_is_real`, and dataset-level `errors` (fail closed).

## Patterns detected

Over a price series:

1. **breakout_after_consolidation** — a tight prior range followed by a close
   above the range high. Evidence: consolidation high/low, range %, breakout %.
2. **volume_spike** — last bar's volume ≥ a multiple of its trailing average.
   *Fails closed* (not "no spike") when volume is missing on any window bar.
3. **trend_continuation** — a directional window whose last bar moves with the
   net direction and whose bar-to-bar moves are internally consistent.
4. **mean_reversion_candidate** — last close is a z-score extreme versus its
   lookback window (oversold → reversion-up; overbought → reversion-down).
5. **gap_continuation_risk** — an opening gap up/down, flagging whether it closed
   in the gap direction and whether it was (intrabar) filled. Advisory *risk*
   flag, not a buy/sell call.
6. **failed_breakout** — a recent bar poked above the prior range but the last
   bar closed back below it (fakeout).
7. **higher_high_higher_low** — swing structure from two halves of the window:
   HH+HL (uptrend), LH+LL (downtrend), or "mixed" (not detected).
8. **drawdown_recovery** — a meaningful peak-to-trough drawdown that has since
   recovered a configured fraction of its depth.

Over a sequence of labeled outcomes:

9. **win_loss_clusters** — longest win/loss streaks per **normalized** setup
   label, flagging streaks ≥ `cluster_min_len`. Labels normalize through the
   same fail-closed table as the backtest harness; unrecognized labels collapse
   to `UNKNOWN` and are recorded in `evidence["unrecognized_labels"]` — never
   attributed to a setup family that does not exist.

All detectors are pure arithmetic over their inputs: the same fixture always
yields the same numbers. No wall-clock, no randomness, no I/O during compute.

## What is **not** detected (out of scope)

- **No multi-symbol / cross-asset patterns**, no correlation or sector logic.
- **No intraday / multi-timeframe** structure — daily bars only, one symbol per
  series.
- **No indicator zoo** (MACD, Bollinger, Ichimoku, Elliott waves, harmonic
  patterns, candlestick taxonomies). The detectors are deliberately simple and
  explainable; "confidence" is a transparent bounded formula, **not** a trained
  probability.
- **No regime/macro/news context**, no fundamentals, no options greeks.
- **No predictive claim.** A detected pattern describes the present window; it
  does not forecast the next bar or imply an edge.
- **No re-derivation of outcome labels.** `win_loss_clusters` trusts the input
  labels; a *wrong but known* label is undetectable here (garbage labels fail
  closed to UNKNOWN).
- **No fills, sizing, capital, or risk model** of any kind.

## Why it is research-only

- It **places no orders** and **connects to no broker** (`ib_insync`/`ibapi`/
  `alpaca`/etc.); it imports no network/subprocess/order/live-cycle/scheduler
  modules. A `SafetyTests` case asserts the module imports none of the
  guardrail's banned broker packages and is not referenced by the runner.
- It is **not wired** into `tools/run_tacticbot.py`, any adapter, workflow, or
  scheduler. The only code that imports it is its own test.
- It touches **no risk, capital, or position-sizing** settings, and reads/writes
  **no** live NovaBotV2 state, snapshot, `.env`, live-arm token, or scheduled
  task. It uses no network.
- Every signal is flagged `research_only=True`. `data_is_real` is **propagated**
  from the caller and **never invented**; it is forced `False` on any
  fail-closed signal and on any dataset that fails validation, even if the
  caller asserted `data_is_real=True`.
- It **fails closed**: invalid OHLC (non-positive prices, `high < low`,
  open/close outside `[low, high]`, negative volume), non-increasing dates, or
  insufficient/degenerate windows produce a `fail_closed_reason` and
  `detected=False` rather than a guess.

## What would be needed before any production use

Nothing here is production-ready, by design. Before any detection could inform
a real decision, all of the following would be required:

1. **Real, labeled, out-of-sample data** at sufficient sample size. Every
   checked-in fixture is synthetic and exists only to pin the arithmetic.
   Per-setup conclusions need ≥30 real deduplicated outcomes per family
   (the NEXT-016 gate), which the live outcome stream does not yet meet.
2. **Statistical validation** that a detected pattern actually precedes a
   different outcome distribution — with multiple-testing correction, because
   nine detectors over many windows will surface spurious "signals".
3. **Calibration** of the transparent confidence formulas against measured hit
   rates (today they are bounded heuristics, not probabilities).
4. **A human-reviewed promotion step** analogous to the future-bot freeze: a
   deliberate, reviewed change — never an implicit import into the runner.
5. **Independent risk/capital controls** owned elsewhere. This module must
   remain incapable of sizing, ordering, or arming anything.

## How this could later feed NovaTacticBot reports (without controlling trades)

The intended (NOT yet wired) consumption path, all read-only:

- The setup-label vocabulary here is the **same** as the backtest harness and
  `NovaBotV2TradeAdapter`'s `strategy_id`, so pattern observations, backtest
  expectancy, and real-outcome expectancy are directly comparable per label.
- A future report step could call `scan_patterns(...)` on a **sanitized,
  offline** price/outcome snapshot and surface `report_to_dict(report)` as a
  **static research artifact** next to the existing analytics — clearly marked
  research-only — to answer questions like "when TacticBot saw a
  `failed_breakout`, what did the real outcome distribution look like?".
- Any such surfacing would consume the JSON report only; the scanner itself
  stays out of every runtime cycle and never gains broker/order/risk authority.

## Usage (offline only)

```bash
# from the NovaTacticBot repo root, using its broker-free venv
.\.venv\Scripts\python.exe -m research.pattern_recognition `
    tests/fixtures/patterns/outcomes_clusters.json `
    --consolidation-window 6 --volume-window 6 --trend-window 6 --lookback 8
```

Programmatic:

```python
from research.pattern_recognition import load_dataset, scan_patterns, PatternConfig

bars, outcomes, symbol, meta = load_dataset("tests/fixtures/patterns/breakout_volume.json")
report = scan_patterns(
    bars,
    PatternConfig(consolidation_window=6, volume_spike_window=6, trend_window=6, lookback=8),
    symbol=symbol,
    outcomes=outcomes or None,
)
# report.research_only is True; report.broker_execution == "disabled"
# report.data_is_real is False (fixtures are synthetic); every signal carries the same flags
for s in report.detected:
    print(s.pattern_name, s.confidence_score, s.evidence)
```

The CLI **never asserts realness** (`data_is_real=False`); the checked-in
fixtures are synthetic and exist only to pin the maths.

## Known limitations

- **Transparent heuristics, not models.** Confidence is a bounded formula per
  detector (documented in the source docstrings), not a learned probability.
- **Window-local.** Every price detector looks at the most recent window ending
  at the last bar; it does not enumerate every historical occurrence.
- **Single symbol, daily bars, long-context.** No multi-symbol, intraday, or
  short-side structure modeling.
- **Synthetic fixtures only.** They pin the arithmetic; they say nothing about
  live edge. Any real-data run must label its fixture as real historical data
  explicitly and state in-sample vs out-of-sample.
- **Label provenance is declarative** for `win_loss_clusters` (same caveat as
  the backtest harness): a wrong-but-known label is undetectable offline.
