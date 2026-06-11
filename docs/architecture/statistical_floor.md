# NovaTacticBot Statistical Floor

## Status

The statistical floor is a QA-016 design-safe advisory layer. It lives in
`core/statistical_floor.py` and is not enabled by default. It is not wired into
the runner, report generator, snapshot writer, AllocationBot, Bridge, or any
execution path.

NovaTacticBot remains advisory/reporting only.

## Purpose

Tactical signals can look strong because of a high score, a small recent win
streak, or an incomplete data set. The statistical floor prevents that label
from being used unless there is enough evidence behind it.

The floor answers one narrow question:

> Does this signal have enough verified evidence to be labelled `STRONG` for
> advisory reporting?

If the answer is no, the result is diagnostic-only.

## Fields Checked

The floor checks:

- `sample_size`: must meet the configured minimum sample count.
- `confidence`: must be a numeric 0.0-1.0 value and meet the configured floor.
- `win_rate`: when present, must be a numeric 0.0-1.0 value and meet the floor.
- `edge`: when present, must be numeric and meet the expected-edge floor.
- `produced_at`: must be parseable and not stale or future-dated.
- `fresh_until`: when present, must be parseable and not expired.
- `data_is_real`: must be exactly `true` by default.
- `regime`: exposure-increasing signals require a known, verified regime.

At least one of `win_rate` or `edge` must be present. When both are present,
both must pass. Invalid numeric values fail closed rather than being coerced.

## Fail-Closed Behavior

The floor refuses strong classification when evidence is:

- missing
- stale
- fake or unverified
- below configured sample, confidence, win-rate, or edge thresholds
- numerically invalid
- tied to an unknown or unverified regime for an exposure-increasing signal

Refusal does not mean the signal is hidden. It means the signal remains
diagnostic-only and must not be treated as strong by downstream advisory
surfaces.

## AllocationBot and Bridge Interaction

Future integration should keep this ordering:

1. TacticBot evaluates tactical evidence and emits advisory diagnostics.
2. NovaBridge may display the floor result as context only.
3. NovaAllocationBot may consume the diagnostic result only after an explicit
   contract is promoted.
4. Allocation changes must still be governed by AllocationBot's own fail-closed
   rules.

The statistical floor must not directly increase allocation, trade size,
position count, or execution eligibility.

## Calibration Requirement

The current thresholds are conservative defaults for testable safety behavior.
They are not a trading model. Before the floor can affect default reports or
snapshots, it needs calibration against historical outcomes, documented
threshold review, and explicit promotion in code and contract docs.

Until then, the floor remains advisory, design-only, and disabled by default.
