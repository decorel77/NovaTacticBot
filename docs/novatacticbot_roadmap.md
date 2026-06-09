# NovaTacticBot — Full Roadmap

**Date:** 2026-06-09  
**Authority:** This document is the canonical phase roadmap for NovaTacticBot.  
**Task queue:** `data/system/task_queue.json` (100 tasks)  

---

## Guiding Principle

> TacticBot learns. TacticBot observes. TacticBot reports. TacticBot never acts.

---

## Permanent Constraints (all phases, forever)

- `ADVISORY_ONLY = True`
- No broker access
- No trade execution
- No portfolio modification
- No scheduler modification
- No Telegram command execution
- All writes limited to `data/` directory within NovaTacticBot
- Human review required for all advisory suggestions

---

## Phase Status Overview

| Phase | Name | Status | Tasks | Done |
|---|---|---|---|---|
| PHASE_1 | Foundation | COMPLETE | 8 | 8 |
| PHASE_2 | Data Collection | IN PROGRESS | 11 | 3 |
| PHASE_3 | Event Logging | PLANNED | 7 | 0 |
| PHASE_4 | Historical Analytics | IN PROGRESS | 7 | 2 |
| PHASE_5 | Strategy Analytics | IN PROGRESS | 9 | 2 |
| PHASE_6 | Regime Analytics | IN PROGRESS | 7 | 1 |
| PHASE_7 | Recommendation Analytics | IN PROGRESS | 5 | 1 |
| PHASE_8 | Cross-Bot Analytics | PLANNED | 6 | 0 |
| PHASE_9 | Dashboard | IN PROGRESS | 6 | 2 |
| PHASE_10 | Reporting | IN PROGRESS | 7 | 1 |
| PHASE_11 | Memory Integration | PLANNED | 5 | 0 |
| PHASE_12 | Allocation Integration | PLANNED | 5 | 0 |
| PHASE_13 | Advanced Analytics | FUTURE | 6 | 0 |
| PHASE_14 | Readiness Review | FUTURE | 6 | 0 |
| FUTURE_ECOSYSTEM | Future Ecosystem Expansion | PLANNING | 5 | 0 |

---

## PHASE_1 — Foundation (COMPLETE)

**Goal:** Establish the read-only advisory architecture, data contract, and guardrails.

**Status:** COMPLETE — 8/8 tasks done, 99 tests passing.

Tasks:
- TACTIC-F-001 — Repository structure and safety contracts ✓
- TACTIC-F-002 — tactic_data_contract.md ✓
- TACTIC-F-003 — tacticbot_guardrails.md ✓
- TACTIC-F-004 — vision.md ✓
- TACTIC-F-005 — TacticalEvent dataclass and enumerations ✓
- TACTIC-F-006 — Guardrails enforcement module ✓
- TACTIC-F-007 — BaseAdapter abstract class ✓
- TACTIC-F-008 — Phase 1 test suite (53 tests) ✓

---

## PHASE_2 — Data Collection (IN PROGRESS)

**Goal:** Build adapters for every NOVA bot so TacticBot can ingest all ecosystem data.

**Status:** NovaBotV2Options adapter complete. Multi-bot adapters pending.

Tasks:
- TACTIC-DC-001 — Discover and inventory NovaBotV2Options real data sources ✓
- TACTIC-DC-002 — Create NovaBotV2Options real-data adapter ✓
- TACTIC-DC-003 — Implement AdapterDiagnostics ✓
- TACTIC-DC-004 — Create NovaBotV2 adapter (TODO)
- TACTIC-DC-005 — Create MarketRegimeBot adapter (TODO)
- TACTIC-DC-006 — Create NovaAllocationBot adapter (TODO)
- TACTIC-DC-007 — Create NovaMemoryBot report adapter (TODO)
- TACTIC-DC-008 — Create NovaBridge adapter (TODO)
- TACTIC-DC-009 — Multi-source data merge and deduplication (TODO)
- TACTIC-DC-010 — Source inventory v2 — multi-bot schema documentation (TODO)
- TACTIC-DC-011 — Adapter schema compatibility validator (TODO)

**Dependencies:** Requires agreement on export format from each bot's maintainer. MarketRegimeBot must complete REGIME-PHASE-005 (result_snapshot) before TACTIC-DC-005 is actionable.

---

## PHASE_3 — Event Logging (PLANNED)

**Goal:** Give TacticBot its own structured event log for observability and data quality tracking.

Tasks:
- TACTIC-EL-001 — Define TacticBot internal event log schema
- TACTIC-EL-002 — Implement run log writer
- TACTIC-EL-003 — Implement adapter error event logging
- TACTIC-EL-004 — Implement source staleness detection
- TACTIC-EL-005 — Create run history tracker
- TACTIC-EL-006 — Write tests for event logging
- TACTIC-EL-007 — Recommendation produced event logging

**Can begin:** Immediately. No external dependencies.

---

## PHASE_4 — Historical Analytics (IN PROGRESS)

**Goal:** Deep time-series analysis of performance trends across all ingested history.

**Status:** Analytics Engine v1 and v2 complete. Rolling windows and baselines pending.

Tasks:
- TACTIC-HA-001 — Analytics Engine v1 (strategy, regime, rejection, rec quality) ✓
- TACTIC-HA-002 — Analytics Engine v2 (symbol concentration, confidence, ranking) ✓
- TACTIC-HA-003 — Rolling-window win-rate tracker (TODO)
- TACTIC-HA-004 — Historical baseline snapshot storage (TODO)
- TACTIC-HA-005 — Cross-run trend analysis (TODO)
- TACTIC-HA-006 — PnL distribution analysis (TODO)
- TACTIC-HA-007 — Holding period analytics (TODO)

---

## PHASE_5 — Strategy Analytics (IN PROGRESS)

**Goal:** Comprehensive per-strategy performance analysis including bias and edge erosion.

**Status:** Strategy performance and ranking complete. Streak/calibration/erosion pending.

Tasks:
- TACTIC-SA-001 — Strategy performance analytics engine ✓
- TACTIC-SA-002 — Strategy ranking by composite score ✓
- TACTIC-SA-003 — Strategy streak detection (TODO)
- TACTIC-SA-004 — Strategy score calibration analysis (TODO)
- TACTIC-SA-005 — Strategy edge erosion detector (TODO)
- TACTIC-SA-006 — Best/worst symbol analysis per strategy (TODO)
- TACTIC-SA-007 — Strategy temporal pattern analysis (TODO)
- TACTIC-SA-008 — Strategy test suite v3 (TODO)
- TACTIC-SA-009 — Strategy regime-conditional win rate matrix (TODO)

---

## PHASE_6 — Regime Analytics (IN PROGRESS)

**Goal:** Understand how market regime affects every aspect of strategy performance.

**Status:** Regime performance engine complete. Bias detection and fit matrix pending.

Tasks:
- TACTIC-RA-001 — Regime performance analytics engine ✓
- TACTIC-RA-002 — Regime bias detector (TODO)
- TACTIC-RA-003 — Regime-strategy fit matrix (TODO)
- TACTIC-RA-004 — IV environment impact analysis (TODO)
- TACTIC-RA-005 — Regime transition impact analysis (TODO)
- TACTIC-RA-006 — Regime analytics test suite (TODO)
- TACTIC-RA-007 — Volatility spike impact analysis (TODO)

**Dependencies:** TACTIC-DC-005 (MarketRegimeBot adapter) desirable but not blocking — can use NovaBotV2Options regime labels.

---

## PHASE_7 — Recommendation Analytics (IN PROGRESS)

**Goal:** Measure the quality of advisory recommendations against actual outcomes.

**Status:** Accuracy tracker complete. Rank calibration and counterfactual pending.

Tasks:
- TACTIC-RCA-001 — Recommendation accuracy tracker ✓
- TACTIC-RCA-002 — Recommendation rank calibration analysis (TODO)
- TACTIC-RCA-003 — Rejected signal counterfactual analysis (TODO)
- TACTIC-RCA-004 — R/R estimate accuracy scoring (TODO)
- TACTIC-RCA-005 — Recommendation quality trend tracking (TODO)

---

## PHASE_8 — Cross-Bot Analytics (PLANNED)

**Goal:** Correlate events and outcomes across all NOVA bots to find ecosystem-level patterns.

**Dependencies:** Requires PHASE_2 multi-bot adapters (TACTIC-DC-004 through DC-008).

Tasks:
- TACTIC-CBA-001 — NovaBotV2 vs NovaBotV2Options correlation
- TACTIC-CBA-002 — Regime-allocation-performance triangle analysis
- TACTIC-CBA-003 — Ecosystem health impact on signal quality
- TACTIC-CBA-004 — Cross-bot event timeline reconstruction
- TACTIC-CBA-005 — Memory-informed signal context analysis
- TACTIC-CBA-006 — Allocation-adjusted performance comparison

---

## PHASE_9 — Dashboard (IN PROGRESS)

**Goal:** Visual and structured reporting interfaces for all analytics outputs.

**Status:** Markdown report and adapter diagnostics complete. HTML dashboard pending.

Tasks:
- TACTIC-DB-001 — Markdown intelligence report (tacticbot_report.md) ✓
- TACTIC-DB-002 — Adapter diagnostics report (adapter_diagnostics.md) ✓
- TACTIC-DB-003 — HTML dashboard (TODO)
- TACTIC-DB-004 — Cross-bot analytics section in HTML dashboard (TODO)
- TACTIC-DB-005 — Edge erosion warning panel (TODO)
- TACTIC-DB-006 — Write-safety and read-only behavior test suite extension (TODO)

---

## PHASE_10 — Reporting (IN PROGRESS)

**Goal:** Structured report exports, advisory suggestions, and NovaBridge result_snapshot.

**Status:** Source inventory complete. JSON export, result_snapshot, advisory section pending.

Tasks:
- TACTIC-RP-001 — Source inventory report ✓
- TACTIC-RP-002 — Structured JSON analytics export (TODO)
- TACTIC-RP-003 — Weekly intelligence briefing template (TODO)
- TACTIC-RP-004 — Advisory tactical suggestions section (TODO)
- TACTIC-RP-005 — TacticBot result_snapshot.json for NovaBridge (TODO)
- TACTIC-RP-006 — Automated weekly report runner (FUTURE)
- TACTIC-RP-007 — Report generator extension tests (TODO)

---

## PHASE_11 — Memory Integration (PLANNED)

**Goal:** Integrate with NovaMemoryBot for historical context and cross-bot reporting.

**Dependencies:** TACTIC-DC-007 (NovaMemoryBot adapter).

Tasks:
- TACTIC-MI-001 — Design NovaMemoryBot integration contract
- TACTIC-MI-002 — Memory-contextualized analytics pass
- TACTIC-MI-003 — SAVEGAME.md historical context ingestion
- TACTIC-MI-004 — Produce TacticBot-to-MemoryBot summary export
- TACTIC-MI-005 — Memory integration test suite

---

## PHASE_12 — Allocation Integration (PLANNED)

**Goal:** Feed TacticBot strategy rankings as advisory input to NovaAllocationBot.

**Dependencies:** TACTIC-DC-006 (NovaAllocationBot adapter), TACTIC-RA-003 (regime-strategy fit matrix).

Tasks:
- TACTIC-AI-001 — Design AllocationBot integration contract
- TACTIC-AI-002 — Tactic-based allocation recommendation advisory
- TACTIC-AI-003 — Export allocation advisory to result_snapshot.json
- TACTIC-AI-004 — Allocation outcome feedback loop (FUTURE — data accumulation required)
- TACTIC-AI-005 — Allocation integration test suite

---

## PHASE_13 — Advanced Analytics (FUTURE)

**Goal:** Statistical rigor and experimental methods to deepen insight quality.

**Status:** FUTURE — requires substantial trade history (N≥30 per strategy for significance tests).

Tasks:
- TACTIC-AA-001 — Statistical significance testing for strategy rankings
- TACTIC-AA-002 — Sharpe-like strategy risk-adjusted ranking
- TACTIC-AA-003 — Monte Carlo simulation for strategy robustness
- TACTIC-AA-004 — Correlation matrix across strategy-symbol pairs
- TACTIC-AA-005 — Machine learning strategy classifier (experimental)
- TACTIC-AA-006 — Multi-bot executive briefing generation

---

## PHASE_14 — Readiness Review (FUTURE)

**Goal:** Human review gates ensuring every phase is complete before full deployment.

Tasks:
- TACTIC-RR-001 — Phase readiness gate: multi-bot adapters
- TACTIC-RR-002 — Phase readiness gate: analytics engines
- TACTIC-RR-003 — Phase readiness gate: reporting and dashboard
- TACTIC-RR-004 — Guardrails and ADVISORY_ONLY final audit
- TACTIC-RR-005 — Full test suite health check (target 200+ tests)
- TACTIC-RR-006 — Ecosystem integration documentation — final handover

---

## FUTURE_ECOSYSTEM — Future Bot Integration Planning

Planning stubs only. No implementation until bots exist.

- TACTIC-FUTURE-001 — LoggingBot data source preparation
- TACTIC-FUTURE-002 — ResearchBot fundamental data integration
- TACTIC-FUTURE-003 — NewsBot sentiment integration
- TACTIC-FUTURE-004 — MacroBot macro regime integration
- TACTIC-FUTURE-005 — TaxBot realized gains impact analysis

---

## Recommended Next Development Cycle

**Priority order for next session:**

1. **PHASE_3 Event Logging** (TACTIC-EL-001 through EL-003) — can begin immediately, no dependencies
2. **PHASE_2 Data Collection** — TACTIC-DC-004 (NovaBotV2 adapter) — coordinate with NovaBotV2 maintainer
3. **PHASE_5 Strategy Analytics** — TACTIC-SA-003/004 (streak detection + score calibration) — builds on existing engine
4. **PHASE_4 Historical Analytics** — TACTIC-HA-003/004 (rolling windows + baseline storage)
5. **PHASE_10 Reporting** — TACTIC-RP-002/005 (JSON export + result_snapshot for NovaBridge)
