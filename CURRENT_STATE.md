# NovaTacticBot — Current State

**Date:** 2026-06-09  
**Phase:** Phase 2 — Real Data Connection — COMPLETE  
**Mode:** ADVISORY_ONLY = True  

---

## What Exists

### Documentation
- `docs/architecture/tactic_data_contract.md` — universal event schema
- `docs/architecture/tacticbot_guardrails.md` — hard operational boundaries
- `docs/architecture/vision.md` — why TacticBot exists

### Core
- `core/tactic_event.py` — `TacticalEvent` dataclass + enumerations (contract v1.0)
- `core/tactic_analytics_engine.py` — all analytics passes, returns `AnalyticsResult`

### Adapters
- `adapters/base_adapter.py` — abstract `BaseAdapter`
- `adapters/options_adapter.py` — generic JSON/CSV/log adapter
- `adapters/nova_options_adapter.py` — real NovaBotV2Options directory adapter

### Utils
- `utils/guardrails.py` — startup checks, `ADVISORY_ONLY = True`
- `utils/tactic_report_generator.py` — renders AnalyticsResult → markdown with diagnostics sections

### Tools
- `tools/run_tacticbot.py` — CLI runner with `--nova-options-dir` and `--warn-broker-env`

### Tests (78 passing)
- `tests/test_tactic_event.py`
- `tests/test_options_adapter.py`
- `tests/test_analytics_engine.py`
- `tests/test_report_generator.py`
- `tests/test_readonly_behavior.py`
- `tests/test_nova_options_adapter.py` — real-data integration tests

### Fixtures
- `tests/fixtures/nova_options/` — sanitized NovaBotV2Options data for tests

### Reports Generated
- `data/reports/tacticbot_report.md` — first real intelligence report

---

## Real Data Summary (from NovaBotV2Options)

| Metric | Value |
|---|---|
| Events loaded | 18 |
| Source files | decision_audit_trail.jsonl, options_events.jsonl, recommendation_accuracy.json |
| Strategies observed | 4 (LONG_CALL, CASH_SECURED_PUT, COVERED_CALL, chain_filter_AAPL) |
| Regimes observed | 4 (BULL, BEAR, NORMAL, UNKNOWN) |
| Completed trades (paper) | 5 (from recommendation_accuracy.json) |
| Chain rejections (deduplicated) | 1 |
| Signal rejections | 10 |
| Adapter errors | 0 |
| Records skipped | 299 (duplicate chain rejection log lines) |

---

## NovaBotV2Options Write-Safety Verification

`git status` in NovaBotV2Options after TacticBot run shows only the pre-existing
untracked file `docs/handover/advisory_pipeline_audit_2026-06-08.md` — TacticBot
wrote no files to the source repository. Confirmed clean.

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

# Clean production environment (no --warn-broker-env needed):
python tools/run_tacticbot.py --nova-options-dir "C:\NovaGPT\Apps\NovaBotV2Options"
```

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
- Bias detection analytics
- Advisory suggestion generation
- Edge erosion detection
- Scheduled reporting

---

## Readiness for Phase 3

| Criterion | Status |
|---|---|
| Real NovaBotV2Options data ingested | READY |
| First real report generated | READY |
| Adapter diagnostics in report | READY |
| Pre-computed supplementary stats in report | READY |
| Write-safety confirmed | READY |
| 78 tests passing | READY |
| Multi-bot adapter architecture stable | READY |
| Next: Bias detection or multi-bot support | PENDING |
