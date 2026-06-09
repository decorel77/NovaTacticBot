# Tactic Data Contract v1.0

## Overview

The Tactic Data Contract defines the universal tactical event format consumed by NovaTacticBot.
All source bots must convert their native output into this schema before TacticBot can process it.

---

## Universal Tactical Event Schema

```json
{
  "event_id": "uuid-v4",
  "timestamp": "ISO-8601",
  "source_bot": "NovaBotV2Options",
  "event_type": "TRADE_OUTCOME",
  "strategy_id": "covered_call",
  "regime": "NORMAL",
  "score": 0.82,
  "expected_rr": 1.8,
  "realized_pnl": 55.20,
  "outcome": "WIN",
  "metadata": {}
}
```

---

## Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | string (UUID) | Yes | Unique identifier for the event |
| `timestamp` | string (ISO-8601) | Yes | When the event occurred |
| `source_bot` | string | Yes | Which NOVA bot produced this event |
| `event_type` | string (enum) | Yes | Category of event (see below) |
| `strategy_id` | string | Yes | Identifier of the strategy involved |
| `regime` | string (enum) | No | Market regime at time of event |
| `score` | float [0.0–1.0] | No | Confidence or quality score assigned by source bot |
| `expected_rr` | float | No | Expected risk/reward ratio at decision time |
| `realized_pnl` | float | No | Actual PnL realized (null if not yet known) |
| `outcome` | string (enum) | No | Result of the event (see below) |
| `metadata` | object | No | Source-bot-specific additional fields |

---

## Enumerated Values

### source_bot

| Value | Description |
|---|---|
| `NovaBotV2` | Stock decision bot |
| `NovaBotV2Options` | Options decision bot |
| `MarketRegimeBot` | Market regime classifier |
| `NovaAllocationBot` | Capital allocation recommender |
| `NovaBridge` | Ecosystem coordinator |

### event_type

| Value | Description |
|---|---|
| `TRADE_OUTCOME` | A completed trade result |
| `RECOMMENDATION` | A signal or recommendation issued |
| `REJECTION` | A signal that was filtered or rejected |
| `REGIME_CHANGE` | A market regime transition |
| `ALLOCATION_CHANGE` | An allocation recommendation event |
| `SYSTEM_EVENT` | Operational or lifecycle event |

### regime

| Value | Description |
|---|---|
| `BULL` | Bullish market environment |
| `BEAR` | Bearish market environment |
| `NORMAL` | Neutral / range-bound market |
| `HIGH_VOL` | High volatility regime |
| `LOW_VOL` | Low volatility regime |
| `UNKNOWN` | Regime not classified |

### outcome

| Value | Description |
|---|---|
| `WIN` | Positive outcome |
| `LOSS` | Negative outcome |
| `BREAKEVEN` | Near-zero outcome |
| `PARTIAL` | Partially filled or closed |
| `EXPIRED` | Expired without exercise |
| `PENDING` | Outcome not yet known |

---

## Adapter Responsibilities

Each source bot has a corresponding adapter in `adapters/`. The adapter is responsible for:

1. Reading native bot output (reports, logs, CSV exports)
2. Mapping native fields to the universal schema
3. Validating required fields
4. Returning a list of `TacticalEvent` objects

Adapters are **read-only**. They never write back to source bot systems.

---

## Versioning

The contract version is embedded in every event via the `metadata.contract_version` field.
Current version: `1.0`

When fields are added, the minor version increments.
When fields are removed or renamed, the major version increments.
All adapters must declare which contract version they target.

---

## Multi-Bot Expansion Notes

This contract is intentionally generic. Fields like `regime`, `score`, and `expected_rr` are
optional so that bots which do not produce those values (e.g. MarketRegimeBot producing only
regime classification events) can still conform without nulling every field.

Future bot-specific fields belong in `metadata`, not in the top-level schema.
