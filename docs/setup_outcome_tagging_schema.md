# NovaTacticBot — Setup / Outcome Tagging Schema

Status: schema/design document (docs-only); research-only, no execution meaning
Scope: define the tag schema for a trade setup and its outcome (setup, regime, score, RR, ATR, volume, age, exit reason, protection state) so expectancy research has reliable, versioned provenance
Implementation status: this document reads no real trades/outcomes, wires no producer, changes no code, and touches no runtime data. It is a versioned schema; it carries no execution semantics.

Card: TACTIC-003 (§4 EPIC-07) from the NovaGPT Vault roadmap. Companion to `sample_floor_contract.md` and `pattern_recognition_research.md`. Producer field ownership is BRIDGE-006 (recommended).

## Purpose

A reliable setup/outcome tag schema is the prerequisite for trustworthy expectancy research. This schema is **descriptive only** — a tag never authorises or influences a trade.

## Schema version

`setup_outcome_tag.v1` — additive, versioned. New fields are added as optional; existing fields are never silently repurposed.

## Fields

### Required (a record without all required fields is fail-closed / excluded)

| Field | Type | Meaning |
|---|---|---|
| `setup` | enum/string | the setup label (shared vocabulary; e.g. breakout, pullback) |
| `regime` | string | regime at entry, mapped to the canonical regime vocabulary (UNKNOWN if absent) |
| `entry_score` | float | the setup's score at entry |
| `rr_planned` | float | planned reward:risk |
| `atr` | float | ATR (volatility context) at entry |
| `volume_context` | string/enum | relative volume context (e.g. above/below average) |
| `age` | int/duration | bars/time held |
| `exit_reason` | enum | target / stop / time / manual / protection / UNKNOWN |
| `protection_state` | enum | PROTECTED / PARTIAL / MISSING / UNKNOWN at exit |
| `provenance` | enum | `REAL` / `SYNTHETIC` / `MIXED` (only `REAL` counts toward sample floor) |

### Optional

| Field | Type | Meaning |
|---|---|---|
| `rr_realized` | float | realised reward:risk |
| `mfe` / `mae` | float | max favourable / adverse excursion |
| `regime_confidence` | float | regime classifier confidence at entry |
| `notes` | string | free-text research note (never an instruction) |

## Rules (fail closed)

1. **Missing provenance ⇒ excluded.** A record without `provenance` (or with unverifiable provenance) is dropped from any expectancy aggregation, never assumed `REAL`.
2. **Missing required field ⇒ excluded** from aggregation and flagged, never defaulted to a favourable value.
3. **No execution meaning.** No field (including `exit_reason`/`protection_state`) authorises or modifies a trade; tags describe history.
4. **Versioned/additive.** Schema changes bump the version; consumers ignore unknown fields rather than failing.
5. **Sample-floor aware.** Only `provenance = REAL` records count toward the TACTIC-002 sample floor.

## Validation (docs-only / synthetic)

- A complete synthetic record validates; a record missing a required field or `provenance` is excluded (fail-closed) and flagged.
- Unknown `exit_reason`/`protection_state`/`regime` map to `UNKNOWN`, never a favourable default.
- No real trade/outcome data is read.

## Stop conditions

- If the schema needs the NovaBotV2 producer changed or real trade logs read, stop — producer change/real reads are out of this card (producer ownership = BRIDGE-006; real outcomes = TACTIC-006, BLOCKED).

## Safety confirmation

This schema was written from existing NovaTacticBot research docs only. It read no real trades/outcomes/runtime data (`data/system/*`, logs), changed no code, wired no producer, and touched no `.env`/secret or cross-repo path. Tags are descriptive/research-only with no execution semantics; this document grants no authority and lifts no gate.
