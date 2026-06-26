# Research-Only Indicators: MACD / Bollinger / Volume Trend (TA-004)

Task: `TA-004`
Status: research-only prototype (broker-free, stdlib-only, **unwired**)
Repo: `Apps/NovaTacticBot`
Module: `research/research_indicators.py` · Tests: `tests/test_research_indicators.py`
HEAD at authoring: `1808448`

> **This is research, not a live signal.** These indicators are a *microscope* for
> studying whether MACD / Bollinger / volume-trend add anything. They are **not**
> used by the live NovaBotV2 path (whose deliberate set stays EMA20/EMA50 + RSI +
> ATR — see NovaBotV2 `docs/ta_indicator_production_path.md`). No edge is claimed.

## Why it lives here (and not in NovaBotV2)

Consistent with pattern recognition, research-stage technical analysis lives in
`NovaTacticBot/research/`, never in the NovaBotV2 live path. This module must
**not** be added to `build_indicator_frame`, `detect_setup`, or the market
scanner, and must not be imported by any runner/scheduler.

## What it computes (pure, deterministic)

| Indicator | Function | Output |
|---|---|---|
| MACD | `compute_macd(closes, cfg)` | `macd`, `signal`, `histogram` (EMA fast−slow, signal EMA, diff) |
| Bollinger Bands | `compute_bollinger(closes, cfg)` | `mid`, `upper`, `lower`, `percent_b`, `bandwidth` |
| Volume trend | `compute_volume_trend(volumes, cfg)` | `short_avg`, `long_avg`, `ratio`, `direction` (rising/falling/flat) |
| All three | `compute_research_indicators(closes, volumes, cfg)` | a `ResearchIndicatorReport` |

Periods/thresholds are in `ResearchIndicatorConfig` (classic defaults: MACD
12/26/9, Bollinger 20/2, volume 5/20). EMA uses the `adjust=False` convention,
seeded with the first value, so results are fully deterministic.

## Fail-closed contract

- Every result carries `research_only=True`, `broker_execution="disabled"`, and a
  `status` of `OK` or `FAIL_CLOSED` with a `fail_closed_reason`.
- Non-finite (`NaN`/`±Infinity`), non-numeric, `None`, and `bool` inputs fail
  closed (`_is_real_number` / `_finite_floats`) — never coerced to a fabricated 0.
- Insufficient length, invalid periods, zero-variance Bollinger windows, and
  negative/degenerate volume all fail closed with null values.
- Given the same input it always returns the same output (no wall-clock, no RNG).

## Safety / import-isolation (pinned by tests)

`tests/test_research_indicators.py::SafetyTests` asserts the module imports no
broker/network package (via `utils.guardrails._BANNED_PACKAGES`), no
`pandas`/`numpy`, no order/koopbot/scheduler symbol; that its **import lines**
reference no NovaBotV2 live-path module; and that `tools/run_tacticbot.py` does
not import it. Determinism and the NaN/inf fail-closed cases are pinned too.

## Out of scope

No wiring into any runner/scheduler or the live indicator path, no edge claim, no
real-data run. Promotion would be a separate, explicitly human-gated decision.
