# NovaTacticBot — Current State

**Date:** 2026-06-09  
**Phase:** Phase 2 — Real Data Integration — COMPLETE  
**Mode:** ADVISORY_ONLY = True  

---

## What Exists

### Documentation
- `docs/architecture/tactic_data_contract.md` — universal event schema
- `docs/architecture/tacticbot_guardrails.md` — hard operational boundaries
- `docs/architecture/vision.md` — why TacticBot exists

### Core
- `core/tactic_event.py` — `TacticalEvent` dataclass + enumerations (contract v1.0)
- `core/tactic_analytics_engine.py` — all analytics passes v2, returns `AnalyticsResult`
  - Strategy analysis, regime analysis, rejection analysis, recommendation quality
  - **NEW (Phase 2):** Symbol concentration, confidence distribution, candidate ranking

### Adapters
- `adapters/base_adapter.py` — abstract `BaseAdapter`
- `adapters/options_adapter.py` — generic JSON/CSV/log adapter
- `adapters/nova_options_adapter.py` — real NovaBotV2Options directory adapter
  - Parses: `decision_audit_trail.jsonl`, `options_events.jsonl`, `recommendation_accuracy.json`
  - Supplementary: `strategy_performance.json`, `regime_performance.json`, `signal_lifecycle_summary.json`
  - Fallback: `decision_audit_summary.json` (used when JSONL is absent)
  - Full `AdapterDiagnostics` with files found/missing/skipped, parse errors, schema mismatches

### Utils
- `utils/guardrails.py` — startup checks, `ADVISORY_ONLY = True`
- `utils/tactic_report_generator.py` — renders AnalyticsResult → markdown
  - `tacticbot_report.md` — main intelligence report
  - `adapter_diagnostics.md` — **NEW** separate diagnostics file

### Tools
- `tools/run_tacticbot.py` — CLI runner with `--nova-options-dir` and `--warn-broker-env`

### Tests (99 passing)
- `tests/test_tactic_event.py`
- `tests/test_options_adapter.py`
- `tests/test_analytics_engine.py`
- `tests/test_analytics_engine_v2.py` — **NEW** symbol concentration, confidence, ranking, diagnostics
- `tests/test_report_generator.py`
- `tests/test_readonly_behavior.py`
- `tests/test_nova_options_adapter.py` — real-data integration tests

### Fixtures
- `tests/fixtures/nova_options/` — sanitized NovaBotV2Options data for tests

### Reports Generated
- `data/reports/tacticbot_report.md` — intelligence report with v2 analytics sections
- `data/reports/adapter_diagnostics.md` — **NEW** standalone diagnostics file
- `data/reports/source_inventory.md` — **NEW** source discovery and schema documentation

---

## Real Data Summary (from NovaBotV2Options)

| Metric | Value |
|---|---|
| Events loaded | 18 |
| Source files parsed | decision_audit_trail.jsonl, options_events.jsonl, recommendation_accuracy.json, strategy_performance.json, regime_performance.json, signal_lifecycle_summary.json |
| Strategies observed | 4 (LONG_CALL, CASH_SECURED_PUT, COVERED_CALL, chain_filter_AAPL) |
| Regimes observed | 4 (BULL, BEAR, NORMAL, UNKNOWN) |
| Symbols tracked | 5 (AAPL, SPY, MSFT, TSLA, QQQ) |
| Completed trades (paper) | 5 |
| Chain rejections (deduplicated) | 1 |
| Signal rejections | 10 |
| Adapter errors | 0 |
| Records skipped | 299 (duplicate chain rejection log lines) |

---

## NovaBotV2Options Write-Safety Verification

TacticBot writes no files to the source repository. Verified: `test_no_writes_to_fixture_dir` passes.

---

## Known Environment Issue

`ib_insync` is installed in the shared Python environment (same env used by NovaBotV2Options).
The guardrail correctly detects and flags this. Use `--warn-broker-env` for development runs.
For production, run TacticBot in a clean virtualenv.

---

## How to Run

```bash
# Real NovaBotV2Options directory (developer machine):
cd C:\NovaGPT\Apps\NovaTacticBot
python tools/run_tacticbot.py --nova-options-dir "C:\NovaGPT\Apps\NovaBotV2Options" --warn-broker-env
```

Generates:
- `data/reports/tacticbot_report.md`
- `data/reports/adapter_diagnostics.md`

---

## How to Run Tests

```bash
cd C:\NovaGPT\Apps\NovaTacticBot
python -m pytest tests/ -v
```

---

## What Is NOT Yet Built

- NovaBotV2 adapter
- MarketRegimeBot adapter
- NovaAllocationBot adapter
- NovaBridge adapter
- Bias detection analytics (regime bias, score calibration, temporal patterns, streak analysis)
- Advisory suggestion generation
- Edge erosion detection
- Scheduled reporting

---

## Readiness for Phase 3 (Bias Detection)

| Criterion | Status |
|---|---|
| Real NovaBotV2Options data ingested | READY |
| Intelligence report with v2 analytics | READY |
| Symbol concentration analysis | READY |
| Confidence distribution analysis | READY |
| Candidate ranking | READY |
| Separate diagnostics report | READY |
| Source inventory documented | READY |
| Write-safety confirmed | READY |
| 99 tests passing | READY |
| Multi-bot adapter architecture stable | READY |
| Next: Bias detection or multi-bot adapters | PENDING |
