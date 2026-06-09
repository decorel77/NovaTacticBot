# NovaTacticBot — Current State

**Date:** 2026-06-09  
**Phase:** Foundation (Phase 1) — COMPLETE  
**Mode:** ADVISORY_ONLY = True  

---

## What Exists

### Documentation
- `docs/architecture/tactic_data_contract.md` — universal event schema
- `docs/architecture/tacticbot_guardrails.md` — hard operational boundaries
- `docs/architecture/vision.md` — why TacticBot exists and how it differs from all other NOVA bots

### Core
- `core/tactic_event.py` — `TacticalEvent` dataclass + enumerations (contract v1.0)
- `core/tactic_analytics_engine.py` — all analytics passes, returns `AnalyticsResult`

### Adapters
- `adapters/base_adapter.py` — abstract `BaseAdapter`
- `adapters/options_adapter.py` — reads NovaBotV2Options JSON / CSV / log files

### Utils
- `utils/guardrails.py` — startup checks, `ADVISORY_ONLY = True`
- `utils/tactic_report_generator.py` — renders `AnalyticsResult` → markdown report

### Tools
- `tools/run_tacticbot.py` — end-to-end runner

### Tests
- `tests/test_tactic_event.py` — contract validation, serialization
- `tests/test_options_adapter.py` — JSON, CSV, log, edge cases
- `tests/test_analytics_engine.py` — all analytics passes
- `tests/test_report_generator.py` — report rendering
- `tests/test_readonly_behavior.py` — guardrail and write-safety verification

### Project Files
- `task_queue.json` — phased task backlog
- `roadmap.md` — long-term vision
- `savegame.md` — session checkpoint

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

## How to Run

```bash
cd C:\NovaGPT\Apps\NovaTacticBot
python tools/run_tacticbot.py --source-dir PATH_TO_OPTIONS_OUTPUT
```

---

## How to Run Tests

```bash
cd C:\NovaGPT\Apps\NovaTacticBot
python -m pytest tests/ -v
```

---

## Readiness for Phase 2

| Criterion | Status |
|---|---|
| Universal data contract defined | READY |
| Adapter interface stable | READY |
| Analytics engine operational | READY |
| Report generation working | READY |
| Guardrails enforced at startup | READY |
| Test suite passing | READY |
| Multi-bot expansion architecture in place | READY |
| Real NovaBotV2Options data ingested | PENDING — connect source_dir |
