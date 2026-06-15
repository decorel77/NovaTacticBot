# NovaTacticBot — Current State

**Date:** 2026-06-09  
**Phase:** Phases 3–6 COMPLETE + Phase 10 result_snapshot + Phase 11 HTML Dashboard + MarketRegimeBot adapter  
**Mode:** ADVISORY_ONLY = True  

---

## Latest Status — 2026-06-15

- TACTIC-HA-005 cross-run trend analysis is **built and verified**:
  `utils/cross_run_trend_analyser.py` with `tests/test_cross_run_trend_analyser.py`.
  An earlier status drift listed it under "What Is NOT Yet Built"; that is corrected
  below. It is research/diagnostic-only and read-only, and is **not wired** into
  `tools/run_tacticbot.py` or any scheduler.
- Verification run (broker-free venv, synthetic fixtures only): the analyser's
  targeted tests pass at **26/26** after adding fail-closed, small-sample-visibility,
  and determinism cases. The full NovaTacticBot suite passes at **472 tests + 145
  subtests**.
- The analyser fails closed on insufficient (`<2` baselines), empty, or partial
  records: absent metrics are skipped, never coerced into a fabricated trend.
- Safety boundary unchanged: no scheduler, `.env`, live-arm, broker/order code,
  risk/capital settings, deploy, NovaBotV2 producer output, or live cycle was
  touched. No real runtime/outcome data was read; all fixtures are synthetic.

### 2026-06-15 — safe research batch (TC-001/002/004/005)

- **TACTIC-RP-002 (JSON analytics export):** a research-only serializer
  `research/analytics_json_export.py` now renders an `AnalyticsResult` to a
  deterministic, ASCII-safe JSON dict/string (sibling of the Markdown report). It
  is diagnostic-only, propagates `data_is_real` (never invents it), writes nothing
  by default, and is **not wired** into `tools/run_tacticbot.py`. A future
  runtime/report-wired export remains a separate, human-reviewed step.
- **TACTIC-RA-003 (regime-strategy fit matrix):** a research-only
  `research/regime_strategy_fit.py` builds a regime x strategy fit matrix from
  `TacticalEvent`s. Per-cell win rates are **withheld below the `min_sample=30`
  floor** (NEXT-016), unknown/None regimes fail closed to `UNKNOWN`, and the matrix
  is diagnostic-only — never a trusted edge. Not wired into the runner.
- **TACTIC-PR / NEXT-016 test hardening:** added synthetic-only fail-closed cases
  to `tests/test_pattern_recognition.py` (non-positive prices, open/close outside
  `[low, high]`) and provenance/returns invariants to
  `tests/test_pattern_outcome_bridge.py` (synthetic or mixed-provenance data never
  becomes a trusted/real edge even at sample size; averages withheld without returns).
- Full NovaTacticBot suite now passes at **502 tests + 197 subtests** (broker-free
  venv, synthetic fixtures only). No app runner/scheduler wiring, no real
  runtime/outcome reads, no broker/order/secrets/risk/capital/deploy were touched.

---

## Latest Status — 2026-06-12

- NEXT-008/009 read-only NovaBotV2 stock outcome wiring is active behind
  `--nova-botv2-dir`.
- NEXT-016 realness/blocking preflight is cleared after Joeri manually refreshed
  the normal NovaTacticBot runtime artifact with:
  `.\.venv\Scripts\python.exe tools\run_tacticbot.py --nova-botv2-dir C:\NovaGPT\Apps\NovaBotV2 --report-name NEXT_016_real_outcome_runtime_refresh.md`
- NovaBridge default ecosystem freshness panel now reports NovaTacticBot
  `VALID` / `FRESH` / `data_is_real=true` / non-blocking.
- Statistical confidence is still `DIAGNOSTIC_ONLY`: current unique real stock
  outcomes = 1, required soak threshold = at least 30 deduplicated real outcomes
  before TacticBot conclusions can be used for decisions.
- Safety boundary unchanged: no scheduler, `.env`, live-arm, broker/order code,
  risk/capital settings, NEXT-003 promotion, NovaBotV2 producer output, or
  NovaBotV2 live cycle was touched. NovaBotV2 was only read from
  `data/results/trade_events.jsonl`.

---

## What Exists

### Documentation
- `docs/architecture/tactic_data_contract.md` — universal event schema v1.0
- `docs/architecture/tacticbot_guardrails.md` — hard operational boundaries
- `docs/architecture/vision.md` — why TacticBot exists
- `docs/novatacticbot_roadmap.md` — canonical full roadmap (14 phases + future ecosystem)

### Core
- `core/tactic_event.py` — `TacticalEvent` dataclass + enumerations (contract v1.0)
- `core/tactic_analytics_engine.py` — analytics engine v3, returns `AnalyticsResult`
  - Strategy analysis, regime analysis, rejection analysis, recommendation quality
  - Symbol concentration, confidence distribution, candidate ranking
  - Rolling win-rate windows (last-10, last-30, last-100) — TACTIC-HA-003
  - Strategy streak detection (flag loss streak ≥ 3) — TACTIC-SA-003
  - Edge erosion detector (flag rolling ≥ 10pp below baseline) — TACTIC-SA-005
  - Regime bias detector (flag 2× expected frequency) — TACTIC-RA-002
  - Score calibration analysis (10 decile buckets) — TACTIC-SA-004
  - `RegimeBiasAnalysis`, `EdgeErosionAnalysis`, `StreakAnalysis`, `ScoreCalibration` in AnalyticsResult

### Adapters
- `adapters/base_adapter.py` — abstract `BaseAdapter`
- `adapters/options_adapter.py` — generic JSON/CSV/log adapter
- `adapters/nova_options_adapter.py` — real NovaBotV2Options directory adapter
- `adapters/nova_botv2_adapter.py` — NovaBotV2 result_snapshot adapter → SYSTEM_EVENT per run (TACTIC-DC-004)
- `adapters/market_regime_adapter.py` — MarketRegimeBot regime_export.json adapter → REGIME_CHANGE per run (TACTIC-DC-005 / MASTER-020)
  - Reads regime_export.json (v1) or falls back to result_snapshot.json
  - Maps market_regime → TacticalEvent.regime, confidence/100 → score
  - Allowlist enforced, size guard, fail closed
  - Parses: `decision_audit_trail.jsonl`, `options_events.jsonl`, `recommendation_accuracy.json`
  - Supplementary: `strategy_performance.json`, `regime_performance.json`, `signal_lifecycle_summary.json`
  - Full `AdapterDiagnostics`

### Utils
- `utils/guardrails.py` — startup checks, `ADVISORY_ONLY = True`
- `utils/tactic_report_generator.py` — renders AnalyticsResult → markdown + diagnostics
- `utils/tactic_event_logger.py` — internal event log schema + JSONL writer (TACTIC-EL-001)
- `utils/tactic_run_log_writer.py` — run log writer (TACTIC-EL-002) — appends to `data/logs/tactic_run_log.jsonl`
- `utils/analytics_baseline_writer.py` — persists baseline snapshots to `data/system/analytics_baseline.json` (TACTIC-HA-004)
- `utils/adapter_error_logger.py` — ADAPTER_ERROR JSONL logger (TACTIC-EL-003) — appends to `data/logs/tactic_adapter_errors.jsonl`
- `utils/run_history_tracker.py` — run summary tracker (TACTIC-EL-005) — appends to `data/system/run_history.json`
- `utils/tactic_snapshot_writer.py` — writes `data/system/result_snapshot.json` for NovaBridge (TACTIC-RP-005)
- `utils/cross_run_trend_analyser.py` — cross-run trend analysis: win-rate shift, volume shift, strategy mix change (TACTIC-HA-005)
- `utils/multi_source_merger.py` — merges TacticalEvents from all adapters; deduplicates on event_id/signal_id; MergeStats (TACTIC-DC-009)

### Research (offline, unwired, diagnostic-only)
These modules are research-only: not imported by `tools/run_tacticbot.py` or any scheduler, broker-free, fail-closed, and synthetic-fixture tested.
- `research/pattern_recognition.py` — explainable price-pattern detectors over synthetic OHLC(V)
- `research/pattern_report.py` — Markdown render layer for `PatternScanReport`
- `research/pattern_outcome_bridge.py` — trade-outcome diagnostic summary; NEXT-016 `min_sample=30` sample floor
- `research/stock_tactics_backtest.py` — offline backtest harness (NEXT-015)
- `research/analytics_json_export.py` — JSON serializer for `AnalyticsResult` (TACTIC-RP-002); deterministic, ASCII-safe, `data_is_real` propagated
- `research/analytics_json_export_cli.py` — offline synthetic-only CLI for the JSON export (stdout only, `data_is_real=false`, no real-dir reads, fail-closed)
- `research/regime_strategy_fit.py` — regime x strategy fit matrix (TACTIC-RA-003); diagnostic-only, sample-gated, fail-closed
- `research/regime_strategy_fit_report.py` — Markdown render layer for the fit matrix (withheld cells shown `INSUFFICIENT_SAMPLE`)
- `research/regime_strategy_fit_json.py` — JSON serializer for the fit matrix (withheld cells `null`)

### Workflow
- `workflow/tactic_html_dashboard.py` — self-contained HTML dashboard (TACTIC-DB-003) — writes `data/reports/tactic_dashboard.html`

### Tools
- `tools/run_tacticbot.py` — CLI runner

### Task Queue
- `data/system/task_queue.json` — 100 tasks across 15 phases (NOVA standard format)

### Tests (537 passing + 284 subtests — verified 2026-06-15, broker-free venv)
The list below is representative, not exhaustive. Research-layer suites include
`test_analytics_json_export.py`, `test_regime_strategy_fit.py`,
`test_regime_strategy_fit_report.py`, `test_regime_strategy_fit_json.py`,
`test_pattern_recognition.py`, `test_pattern_outcome_bridge.py`, and
`test_cross_run_trend_analyser.py`.
- `tests/test_tactic_event.py`
- `tests/test_options_adapter.py`
- `tests/test_analytics_engine.py`
- `tests/test_analytics_engine_v2.py`
- `tests/test_report_generator.py`
- `tests/test_readonly_behavior.py`
- `tests/test_nova_options_adapter.py`
- `tests/test_rolling_win_rates.py`
- `tests/test_tactic_event_logger.py`
- `tests/test_tactic_run_log_writer.py` — NEW (9 tests)
- `tests/test_analytics_baseline_writer.py` — NEW (10 tests)
- `tests/test_streak_analysis.py` — NEW (8 tests)
- `tests/test_edge_erosion.py` — NEW (7 tests)
- `tests/test_regime_bias.py` — NEW (7 tests)
- `tests/test_score_calibration.py` — NEW (8 tests)
- `tests/test_tactic_snapshot_writer.py` — NEW (5 tests)
- `tests/test_run_history_tracker.py` — NEW (5 tests)
- `tests/test_adapter_error_logger.py` — NEW (5 tests)
- `tests/test_tactic_html_dashboard.py` — NEW (5 tests)
- `tests/test_cross_run_trend_analyser.py` — NEW (26 tests; verified 2026-06-15)
- `tests/test_nova_botv2_adapter.py` — NEW (21 tests)
- `tests/test_multi_source_merger.py` — NEW (17 tests)
- `tests/test_market_regime_adapter.py` — NEW (27 tests)

### Reports Generated
- `data/reports/tacticbot_report.md`
- `data/reports/adapter_diagnostics.md`
- `data/reports/source_inventory.md`

---

## Real Data Summary (from NovaBotV2Options)

| Metric | Value |
|---|---|
| Events loaded | 18 |
| Strategies observed | 4 (LONG_CALL, CASH_SECURED_PUT, COVERED_CALL, chain_filter_AAPL) |
| Regimes observed | 4 (BULL, BEAR, NORMAL, UNKNOWN) |
| Symbols tracked | 5 (AAPL, SPY, MSFT, TSLA, QQQ) |
| Completed trades (paper) | 5 |
| Adapter errors | 0 |

---

## Environment Isolation (REPAIR-011)

`ib_insync` is installed in the **shared** global interpreter, which is broker-capable.
NovaTacticBot is advisory-only and must NOT run there. Instead it runs in its own
**broker-free virtualenv**, built once with `setup_venv.ps1` (or `setup_venv.sh`).
That script installs only `requirements.txt` (stdlib + pytest, no broker libs) and
asserts no broker package is importable.

The broker guardrail is now **hard** — the former `--warn-broker-env` escape hatch
was removed. If a broker package is reachable, `run_tacticbot.py` aborts with exit 1.

---

## How to Run

```powershell
cd C:\NovaGPT\Apps\NovaTacticBot
# One-time: build the isolated broker-free venv
./setup_venv.ps1
# Run inside that venv:
.\.venv\Scripts\python.exe tools\run_tacticbot.py --nova-options-dir "C:\NovaGPT\Apps\NovaBotV2Options"
```

---

## What Is NOT Yet Built

- MarketRegimeBot adapter (TACTIC-DC-005) — **DONE** (MASTER-020)
- NovaAllocationBot adapter (TACTIC-DC-006)
- NovaMemoryBot adapter (TACTIC-DC-007)
- NovaBridge adapter (TACTIC-DC-008)
- Cross-run / historical baseline trend analysis (TACTIC-HA-005) — **DONE** (built + 26 tests; research/diagnostic-only, not runtime-wired)
- Regime-strategy fit matrix (TACTIC-RA-003) — **research-only done** (`research/regime_strategy_fit.py`, diagnostic-only, sample-gated, not runtime-wired); runtime/report wiring still open
- JSON analytics export (TACTIC-RP-002) — **research-only done** (`research/analytics_json_export.py`, diagnostic-only, not runtime-wired); runtime/report wiring still open
- Multi-source data merge (TACTIC-DC-009) — blocked on MASTER-032 (human approval)

---

## Recommended Next Steps

1. **MASTER-022** — NovaBridge TacticBot adapter (unblocked by result_snapshot ✓)
2. **TACTIC-RP-002 / TACTIC-RA-003 runtime wiring** — promote the research-only
   JSON exporter and regime-strategy fit matrix into report/runtime output behind a
   reviewed, human-gated promotion (real-data + ≥30 sample gates still apply)
3. **TACTIC-HA-006** — PnL distribution analysis (synthetic-fixture research candidate)

> TACTIC-HA-005 (cross-run trend analysis) is complete — see "Latest Status — 2026-06-15".
> TACTIC-RP-002 and TACTIC-RA-003 have research-only implementations — see the
> "2026-06-15 — safe research batch" status block above.
