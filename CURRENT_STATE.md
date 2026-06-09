# NovaTacticBot — Current State

**Date:** 2026-06-09  
**Phase:** Phases 3–6 COMPLETE + Phase 10 result_snapshot + Phase 11 HTML Dashboard  
**Mode:** ADVISORY_ONLY = True  

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

### Workflow
- `workflow/tactic_html_dashboard.py` — self-contained HTML dashboard (TACTIC-DB-003) — writes `data/reports/tactic_dashboard.html`

### Tools
- `tools/run_tacticbot.py` — CLI runner

### Task Queue
- `data/system/task_queue.json` — 100 tasks across 15 phases (NOVA standard format)

### Tests (243 passing)
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
- `tests/test_cross_run_trend_analyser.py` — NEW (21 tests)
- `tests/test_nova_botv2_adapter.py` — NEW (21 tests)
- `tests/test_multi_source_merger.py` — NEW (17 tests)

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

## Known Environment Issue

`ib_insync` is installed in the shared Python environment. Use `--warn-broker-env` on this machine.

---

## How to Run

```bash
cd C:\NovaGPT\Apps\NovaTacticBot
python tools/run_tacticbot.py --nova-options-dir "C:\NovaGPT\Apps\NovaBotV2Options" --warn-broker-env
```

---

## What Is NOT Yet Built

- NovaBotV2 adapter (TACTIC-DC-004) — requires schema coordination (human approval)
- MarketRegimeBot adapter (TACTIC-DC-005) — blocked on MASTER-017
- NovaAllocationBot adapter (TACTIC-DC-006)
- NovaMemoryBot adapter (TACTIC-DC-007)
- NovaBridge adapter (TACTIC-DC-008)
- Historical baseline trend analysis (TACTIC-HA-005) — blocked on MASTER-005 ✓ + MASTER-007 ✓ → now unblocked
- Regime-strategy fit matrix (TACTIC-RA-003)
- JSON analytics export (TACTIC-RP-002)
- Multi-source data merge (TACTIC-DC-009) — blocked on MASTER-032 (human approval)

---

## Recommended Next Steps

1. **TACTIC-HA-005** — Cross-run trend analysis (unblocked now by run_history ✓ + baseline ✓)
2. **MASTER-022** — NovaBridge TacticBot adapter (unblocked by result_snapshot ✓)
3. **TACTIC-RP-002** — JSON analytics export
4. **TACTIC-RA-003** — Regime-strategy fit matrix
