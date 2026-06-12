# NovaTacticBot Strategy Outcome Correlation

## Status

The strategy correlation diagnostic is a QA-019 design-safe research layer. It
lives in `core/strategy_correlation.py` and is not enabled by default. The
report generator has an optional section for precomputed correlation results,
but the default runner does not compute or pass those results. It is not wired
into the runner, snapshot writer, AllocationBot, Bridge, or any execution path.

NovaTacticBot remains advisory/reporting only.

## Purpose

The ecosystem's allocation reasoning treats NovaBotV2 (equity) and
NovaBotV2Options as diversifying books, but that diversification has never
been measured. This module answers one narrow question:

> How correlated are the daily realized-PnL outcome streams of two bots,
> and is there enough overlapping evidence to say so honestly?

If there is not enough evidence, no correlation number is reported at all.

## Method

1. Each input stream is a list of `TacticalEvent` objects. Only
   `TRADE_OUTCOME` events with a finite numeric `realized_pnl`, a valid
   timestamp, a non-`PENDING` outcome, and (by default) metadata
   `data_is_real: true` are used. Everything else is excluded fail-closed and
   counted per reason in `excluded_events`.
2. Outcomes are aggregated to daily realized PnL per stream (UTC days).
3. Correlation is Pearson's r over the days present in **both** streams,
   computed in pure python (no numpy/scipy).
4. A 95% interval via the Fisher z-transform accompanies every reported
   correlation (the QA-019 analogue of QA-016's Wilson intervals), so a value
   from 35 days cannot masquerade as a value from 500 days.
5. A trailing rolling-window series (default 30 overlapping days per window)
   shows how the correlation drifts over time.

## Sample-Size Gates (QA-016 pattern)

- Below `min_overlap_days` (default 30) overlapping outcome days, the result
  is `insufficient_sample: true`, `correlation: null`, with refusal reason
  `insufficient_overlap:<n><<floor>`.
- Rolling windows configured below the floor withhold their values entirely.
- Between 30 and `small_sample_warning_below` (default 60) days, the value is
  reported with an explicit `small_sample` warning.
- Constant series (zero variance) refuse with
  `correlation_undefined:constant_series` instead of emitting a fake 0.

## Fail-Closed Behavior

The diagnostic refuses or excludes when evidence is:

- not a trade outcome, or still `PENDING`
- missing or numerically invalid realized PnL
- missing a parseable timestamp
- not flagged `data_is_real: true` (default; configurable for research replay)
- below the minimum-overlap floor

Refusal does not hide anything: exclusion counts and refusal reasons are part
of the result, so a future report says *why* there is no number.

## Standing Caveats

Every result carries these caveats verbatim, and any future report surface
must render them:

- Diagnostic only: correlation describes the past sample, not future
  co-movement.
- Correlation below 1.0 is not proof of diversification; both books share
  market beta.
- Daily-aggregated realized PnL hides intraday co-movement and overlapping
  holding periods.

## Wiring Preconditions

Per the QA-019 task definition, this diagnostic may only appear in the
default TacticBot report **after** both event streams are actually wired:

1. QA-009 regime realness gating — DONE (commit `e93e3e7`).
2. NovaBotV2 adapter (task MB-001) — NOT YET BUILT. Today only the
   NovaBotV2Options stream exists, so there is nothing real to correlate.
3. Adapters must stamp `data_is_real` on outcome events, otherwise the
   default realness gate excludes everything (by design).

Until then `render_markdown_section()` and the optional report section remain
display-only helpers. Nothing computes correlation by default; default runner
output and snapshots are unchanged. If a caller supplies a precomputed
insufficient-overlap result, the report shows `INSUFFICIENT SAMPLE` and
withholds the correlation value.

## AllocationBot and Bridge Interaction

The correlation result must never directly change allocation, trade size,
position count, or execution eligibility. If AllocationBot ever consumes it,
that requires an explicit promoted contract, and allocation changes remain
governed by AllocationBot's own fail-closed rules (see
`allocation_v2_design` correlation note in QA-015).
