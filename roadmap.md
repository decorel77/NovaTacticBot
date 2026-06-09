# NovaTacticBot Roadmap

## Guiding Principle

> TacticBot learns. TacticBot observes. TacticBot reports. TacticBot never acts.

---

## Current Phase: Foundation Complete

Phase 1 is delivered. The foundation is read-only, tested, and ready for real data.

---

## Phase 1 — Foundation (COMPLETE)

- Universal tactic data contract
- NovaBotV2Options adapter (JSON, CSV, log)
- Tactical analytics engine (strategy, regime, rejection, recommendation quality)
- Markdown report generator
- Guardrail enforcement
- Full test suite

**Status:** Ready for NovaBotV2Options data ingestion

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
