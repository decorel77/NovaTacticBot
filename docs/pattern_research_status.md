# NovaTacticBot Pattern-Recognition — Research-Only Status (PATTERN-001)

Task: `PATTERN-001`
Status: documentation-only (broker-free, no code edit, no run)
Repo: `Apps/NovaTacticBot`
Evidence date: 2026-06-26 (Europe/Brussels) — **line numbers dated; re-verify at HEAD.**
HEAD at audit: `1808448`

> This note runs no code, imports no broker module, reads no real outcome data,
> and changes nothing. It is a single consolidated confirmation that the pattern
> stack is **research-only / fail-closed / synthetic-only / unwired**, with the
> evidence cross-checked against HEAD. It complements the deeper
> `docs/pattern_recognition_research.md` (detector math) and the module-level
> status lines in `CURRENT_STATE.md` (§"Research (offline, unwired, …)").

## (a) The 9 detectors

Source: `research/pattern_recognition.py` (`PATTERN_NAMES`, `:57-67`). Eight run
over a price (OHLCV) series; one runs over a sequence of labeled trade outcomes.

| # | Detector | Input | Function |
|---|---|---|---|
| 1 | `breakout_after_consolidation` | price bars | `detect_breakout_after_consolidation` (`:270`) |
| 2 | `volume_spike` | price bars (needs volume) | `detect_volume_spike` (`:319`) |
| 3 | `trend_continuation` | price bars | `detect_trend_continuation` (`:357`) |
| 4 | `mean_reversion_candidate` | price bars | `detect_mean_reversion_candidate` (`:409`) |
| 5 | `gap_continuation_risk` | price bars | `detect_gap_continuation_risk` (`:458`) |
| 6 | `failed_breakout` | price bars | `detect_failed_breakout` (`:510`) |
| 7 | `higher_high_higher_low` | price bars | `detect_higher_high_higher_low` (`:557`) |
| 8 | `drawdown_recovery` | price bars | `detect_drawdown_recovery` (`:607`) |
| 9 | `win_loss_clusters` | trade outcomes | `detect_win_loss_clusters` (`:666`) |

The eight price detectors are wired into `_PRICE_DETECTORS` (`:743-752`); `scan_patterns`
(`:755`) runs them and appends `win_loss_clusters` only when `outcomes` is supplied.

## (b) Fail-closed contract

Every detector returns a `PatternSignal` (`:134-161`) carrying
`research_only=True`, a `confidence_score` that is `0.0` whenever not detected or
failed-closed, and a `fail_closed_reason` (with `detected=False`) when the rule
cannot run. Concretely:

- Module constants `RESEARCH_ONLY=True` (`:54`) and `BROKER_EXECUTION="disabled"` (`:55`).
- Insufficient data → `_insufficient(...)` (`:223`); degenerate/invalid input →
  `_failed(...)` (`:247`). Both force `data_is_real=False` ("a non-result vouches
  for nothing").
- `volume_spike` fails closed (not "no spike") when volume is missing on any
  window bar (`:334-338`).
- Zero-variance / non-positive-base windows fail closed in mean-reversion,
  trend, breakout, etc. (`:292-293`, `:373-374`, `:425-428`).
- Dataset-level invalid bars short-circuit `scan_patterns` into an `errors=...`
  report with no signals (`:772-784`); `validate_pattern_bars` (`:209`) rejects
  bad OHLC/date/volume.
- `data_is_real` is propagated from the caller, never invented; the CLI always
  passes `data_is_real=False` (`:919`).

The outcome bridge `research/pattern_outcome_bridge.py` adds the same posture for
trade outcomes: `_to_float` rejects non-finite values to `None` (`:133-142`),
`normalize_outcome` fails closed to `UNKNOWN` (`:145-148`), and below-threshold
groups are `INSUFFICIENT_SAMPLE` with `win_rate=None` (`:271-276`).

## (c) Synthetic-only

- `load_dataset` (`:813`) reads local JSON fixtures; the docstring states all
  checked-in fixtures are synthetic and declare `data_is_real: false`, and the
  loader "never asserts realness".
- The only path that can touch real data is an **explicit, manual, read-only**
  `--nova-botv2-dir` on the outcome-bridge CLI (`pattern_outcome_bridge.py:549-573`),
  which lazy-imports the read-only `NovaBotV2TradeAdapter`. The default synthetic
  path never imports the adapter. (PATTERN-002 keeps this read-only and gated.)
- Tests: `tests/test_pattern_recognition.py`, `tests/test_pattern_outcome_bridge.py`,
  fixtures under `tests/fixtures/patterns/` — all synthetic.

## (d) Unwired (not imported by any runner/scheduler)

Verified at HEAD `1808448` with ripgrep over all `*.py` excluding `research/`,
`tests/`, `__pycache__/`:

```
grep -rn -E "pattern_recognition|pattern_report|pattern_outcome_bridge" \
  --include=*.py . | grep -v -E "^\./research/|^\./tests/|/__pycache__/"
  -> (no matches)
```

The advisory runner `tools/run_tacticbot.py` imports none of the three pattern
modules (its imports are guardrails, adapters, `core.tactic_analytics_engine`,
report/snapshot writers, and `workflow.tactic_html_dashboard` — `:41-59`). The
three pattern modules are imported only by each other and their tests:
`pattern_report` imports `pattern_recognition` (`:30-36`); `pattern_outcome_bridge`
imports both (`:46-51`). Nothing reaches a broker/order/scheduler.

## (e) The ≥30 real-outcome gate (NEXT-016)

- `pattern_outcome_bridge.DEFAULT_MIN_SAMPLE = 30` (`:58`).
- Per-setup `win_rate` / `average_return_pct` are emitted only when
  `sample_count >= min_sample` and there are decisive outcomes; otherwise `None`
  with `win_rate_status = "INSUFFICIENT_SAMPLE"` (`:271-279`).
- Overall and per-setup `status` is `INSUFFICIENT_SAMPLE` whenever the **real**
  sample is below `min_sample` (`:283`, `:304`); a withholding note is added
  (`:314-318`). Small samples are never upgraded to a trusted edge.
- Per `CURRENT_STATE.md`, the current deduplicated real stock-outcome count is ~1,
  far below 30, so everything stays `DIAGNOSTIC_ONLY`. Promotion to advisory is a
  separate `BLOCKED + HUMAN_GATED` card (`PATTERN-005`), and pattern output never
  driving an order is the guard card `PATTERN-006`.

## Verification performed (no code run)

- `PATTERN_NAMES` lists exactly 9 names; 8 in `_PRICE_DETECTORS` + 1 outcome detector. ✔
- `RESEARCH_ONLY=True` / `BROKER_EXECUTION="disabled"` in all three modules. ✔
- `DEFAULT_MIN_SAMPLE = 30`; sub-threshold win-rates withheld (`None`/`INSUFFICIENT_SAMPLE`). ✔
- No `*.py` outside `research/`/`tests/` imports the three modules; runner imports none. ✔

## Out of scope for this card

No wiring, no runner import, no real-data run, no threshold change, no code edit.
This is description only. PATTERN-002 (outcome-count reporting), PATTERN-004
(lookahead audit) are separate SAFE cards; PATTERN-003/005/006 are HUMAN_GATED/BLOCKED.
