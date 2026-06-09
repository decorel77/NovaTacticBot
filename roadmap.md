# NovaTacticBot Roadmap

## Guiding Principle

> TacticBot learns. TacticBot observes. TacticBot reports. TacticBot never acts.

---

## Current Phase: Phase 2 Complete — Ready for Bias Detection or Multi-Bot Support

Phase 2 is delivered. Real data flows from NovaBotV2Options. Analytics v2 is live.

---

## Phase 1 — Foundation (COMPLETE)

- Universal tactic data contract
- NovaBotV2Options adapter (JSON, CSV, log)
- Tactical analytics engine (strategy, regime, rejection, recommendation quality)
- Markdown report generator
- Guardrail enforcement
- Full test suite (78 tests)

**Status:** COMPLETE

---

## Phase 2 — Real Data Integration (COMPLETE)

- NovaBotV2OptionsAdapter reading real directory structure
- decision_audit_trail.jsonl + options_events.jsonl + recommendation_accuracy.json
- decision_audit_summary.json fallback source
- signal_lifecycle_summary.json supplementary data
- Analytics Engine v2: symbol concentration, confidence distribution, candidate ranking
- Separate adapter_diagnostics.md report
- Source inventory with schema documentation
- 99 tests passing

**Status:** COMPLETE

---

## Phase 2 — Multi-Bot Support

**Goal:** Add adapters for every NOVA bot

- NovaBotV2 adapter
- MarketRegimeBot adapter
- NovaAllocationBot adapter
- NovaBridge adapter
- Cross-bot correlation analysis

**Requires:** Coordination with each bot's maintainer to agree on export format

---

## Phase 3 — Bias Detection

**Goal:** Surface systematic biases invisible to the bots themselves

- Regime bias (does the bot over-trade in specific regimes?)
- Score calibration (do high-score signals actually win more often?)
- Temporal patterns (time-of-day, day-of-week effects)
- Streak analysis (are losses clustered?)

---

## Phase 4 — Tactical Suggestions (Advisory)

**Goal:** Add an advisory suggestions section to reports

- Strategy scaling recommendations (human must approve)
- Regime-strategy fit analysis
- All suggestions require human review before any action

---

## Phase 5 — Edge Erosion Detection

**Goal:** Detect when a strategy's edge is diminishing before the drawdown compounds

- Rolling window win-rate tracking
- Edge erosion alerts in reports
- Historical baseline storage

---

## Phase 6 — Weekly Intelligence Briefings

**Goal:** Automated weekly reports covering all active NOVA bots

- Scheduled runner
- Multi-bot executive briefing template
- NovaMemoryBot integration for historical context

---

## Permanent Constraints

These constraints apply to every phase, forever:

- ADVISORY_ONLY = True
- No broker access
- No trade execution
- No portfolio modification
- No scheduler modification
- Human review required for all suggestions
