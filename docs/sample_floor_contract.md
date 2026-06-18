# NovaTacticBot — Diagnostic Dashboard Sample-Floor Contract

Status: contract/design document (docs-only); diagnostic-only
Scope: define what a diagnostic surface must show about sample sufficiency — sample count, threshold, provenance, withheld state — so a single real outcome can never read as an edge claim
Implementation status: this document reads no real outcomes, wires no dashboard, changes no code, and touches no runtime data. It is a contract; nothing here executes or promotes any conclusion.

Card: TACTIC-002 (§4 EPIC-07) from the NovaGPT Vault roadmap. Companion to `research_diagnostic_outputs.md`, `NEXT_016_real_outcome_stream_preflight.md`, and the research-promotion checklist (TACTIC-004).

## Principle

Tactic expectancy/outcome conclusions are **DIAGNOSTIC_ONLY** until a documented sample floor of trusted, deduplicated **real** outcomes is reached. Below the floor, metrics are **withheld**, not shown with a caveat. Visibility of insufficiency is the feature.

## Sample floor

- **Floor = 30 trusted, deduplicated, real outcomes** (per NEXT-016). Synthetic/mixed-provenance outcomes do **not** count toward the floor.
- Until the floor is met, the surface shows `INSUFFICIENT_SAMPLE` and withholds expectancy/edge metrics.

## Required fields on any diagnostic surface (contract)

| Field | Meaning | Rule |
|---|---|---|
| `sample_count` | trusted deduplicated real outcomes counted | integer ≥ 0; never inflated by synthetic rows |
| `sample_floor` | the threshold (30) | constant; shown alongside count |
| `provenance` | `REAL` / `SYNTHETIC` / `MIXED` | only `REAL` counts toward the floor |
| `status` | `DIAGNOSTIC_ONLY` / `INSUFFICIENT_SAMPLE` / `WITHHELD` | never `EDGE`/`SIGNAL` below the floor |
| `withheld` | which metrics are hidden and why | explicit list, not an empty silence |

## Case behaviour (fail-closed)

| Case | Behaviour |
|---|---|
| `sample_count < 30` (REAL) | `status = INSUFFICIENT_SAMPLE`; expectancy/edge metrics `WITHHELD`; show count vs floor |
| `sample_count = 30` (REAL, trusted, deduplicated) | metrics may be shown as `DIAGNOSTIC_ONLY` (still not trading authority) |
| `provenance = MIXED` or `SYNTHETIC` | does not count toward the floor; metrics `WITHHELD` regardless of count |
| provenance/count unknown | fail closed ⇒ `WITHHELD` / `INSUFFICIENT_SAMPLE` |

## Hard boundaries

- **Diagnostic-only, never trading authority.** Reaching the floor enables *display*, not influence on orders/risk/capital (that path is TACTIC-007, HUMAN_GATED).
- **No synthetic promotion.** Synthetic/mixed outcomes never count toward the floor or get presented as an edge.
- **No real-outcome read here.** Building toward the floor with an approved read-only path is TACTIC-006 (BLOCKED); this card defines the contract only.

## Validation (docs-only / synthetic)

- `<30`, `=30`, and `mixed/synthetic` provenance cases each produce the fail-closed status above (synthetic fixtures only).
- Withheld metrics are explicitly listed; nothing reads as an edge below the floor.
- No real outcome stream is read; no dashboard is wired.

## Safety confirmation

This contract was written from existing NovaTacticBot research/diagnostic docs only. It read no real outcomes, wired no dashboard, changed no code, and touched no runtime/private/generated data or `.env`/secret. Conclusions stay DIAGNOSTIC_ONLY and sample-gated; real-outcome accumulation (TACTIC-006) and any influence on trading (TACTIC-007) remain gated. This document grants no authority and lifts no gate.
