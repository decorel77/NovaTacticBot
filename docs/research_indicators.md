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

## Now enforced repo-wide and cross-repo (PATTERN-009 + TA-008 + TA-009)

The old "unwired" claim was a per-module check plus a manual grep. It is now a
standing, broker-free tripwire on **both** sides of the boundary:

- **NovaTacticBot (PATTERN-009).** `tests/test_pattern_unwired_guard.py` AST-scans
  every `*.py` under `tools/`, `workflow/`, `core/`, `adapters/` and fails if any
  imports the `research` package or `research_indicators` specifically — so a
  future runner/scheduler/adapter that wired this prototype in is caught in CI.
- **NovaBotV2 (TA-009).** `tests/test_live_signal_research_indicator_guard.py`
  AST-scans the live TA/signal chain (`workflow/nova_signal_generator.py`,
  `workflow/nova_market_scanner.py`, `utils/signal_setup_utils.py`,
  `utils/market_data_utils.py`, `utils/indicators.py`) and fails if any of them
  imports a research/experimental/prototype indicator (incl. `compute_macd` /
  `compute_bollinger` / `compute_volume_trend`). The live set stays EMA20/EMA50 +
  RSI + ATR. See NovaBotV2 `docs/ta_indicator_production_path.md` §TA-009.
- **TA-008** broadened the edge-case coverage (length boundaries, every
  invalid-config branch, zero-mean Bollinger window, degenerate volume baseline,
  wrong-type inputs, `report_to_dict` round-trip).

Net effect: importing this module into either repo's live signal path now **fails
CI broker-free**. Promotion remains a deliberate HUMAN_GATED decision that must
update these guards on purpose.

## Out of scope

No wiring into any runner/scheduler or the live indicator path, no edge claim, no
real-data run. Promotion would be a separate, explicitly human-gated decision.
