# NovaTacticBot Real Outcome Stream — Discovery & Design (NEXT-008/009 + NEXT-016)

**Status:** DISCOVERY / DESIGN ONLY. Nothing is wired into runtime by this document.
No producer output was changed. All inspection below was read-only.
**Goal:** identify how NovaTacticBot can obtain a real, read-only outcome stream so
it stops being the sole blocking ecosystem producer (`data_is_real: false` / EMPTY),
and specify the minimal wiring for a later, separately-reviewed task.

---

## 1. Why NovaTacticBot is currently EMPTY / data_is_real=false

It is **not** because real outcome data is missing — it is because the existing
real-outcome adapter is **not wired into the runner**:

- `tools/run_tacticbot.py` only loads `NovaBotV2OptionsAdapter` (`--nova-options-dir`)
  and the generic `OptionsAdapter` (`--source-dir`). It **never instantiates**
  `adapters/nova_botv2_trade_adapter.py::NovaBotV2TradeAdapter`.
- Run-level realness comes solely from
  `utils/source_provenance.derive_run_provenance(nova_options_dir, source_dir)`,
  which assesses only the Options paper source. The Options source is PAPER, so the
  run is `data_is_real: false`, the snapshot fails canonical conformance
  (`data_is_real must be true`), and Bridge marks it REJECTED / blocking.

So the gap is **(a) wiring** (NEXT-008/009) and **(b) sample volume** (NEXT-016).

---

## 2. Sources inspected (read-only)

- `NovaBotV2/data/results/trade_events.jsonl` (+ `.csv`)
- `NovaBotV2/data/logs/json/market_events.jsonl`
- `NovaBotV2/data/system/result_snapshot.json`
- `NovaBotV2Options/data/logs/decision_audit_trail.jsonl`
- `NovaBotV2Options/data/logs/options_events.jsonl`
- `NovaBotV2Options/data/system/result_snapshot.json`
- NovaTacticBot: `adapters/nova_botv2_trade_adapter.py`, `adapters/nova_botv2_adapter.py`,
  `utils/source_provenance.py`, `core/tactic_event.py`, `tools/run_tacticbot.py`

---

## 3. Candidate outcome sources

| Source | Producer | Real / paper / mock | data_is_real safe? | Notes |
|---|---|---|---|---|
| `NovaBotV2/data/results/trade_events.jsonl` → `SELL_EXECUTED` | NovaBotV2 (stock) | **REAL** (broker-reconciled) | **YES (per-event)** | 65 SELL_EXECUTED, all `execution_mode: LIVE_RECONCILED`, `broker_source: IBKR`, real `exec_ids`, realised `netto_pnl`. **Best candidate.** |
| `NovaBotV2Options/data/logs/decision_audit_trail.jsonl` | NovaBotV2Options | **PAPER** (+ test markers) | NO | 27 records, `exposure_decision: PAPER`, `outcome: PAPER`, `strategy_reasoning: "test reason"`. Decisions, not realised PnL. |
| `NovaBotV2Options/data/logs/options_events.jsonl` | NovaBotV2Options | paper / processing | NO | 375 lines; chain-row REJECT / loader events, not closed-trade outcomes. |
| `NovaBotV2/data/logs/json/market_events.jsonl` | NovaBotV2 | market data | N/A | Price/market events, not trade outcomes. |
| `NovaBotV2/data/system/result_snapshot.json` | NovaBotV2 | worker state | N/A | Armed-state/positions snapshot (preserved evidence), not a per-trade outcome stream. |
| `NovaBotV2Options/data/system/result_snapshot.json` | NovaBotV2Options | paper summary | NO | Dry-run dashboard summary, no per-trade realised outcomes. |

### 3.1 Best candidate — NovaBotV2 `trade_events.jsonl` (`SELL_EXECUTED`)

- **Path:** `Apps/NovaBotV2/data/results/trade_events.jsonl` (append-only, ~1.96 MB, 2132 lines).
- **Producer:** NovaBotV2 (the live stock pilot).
- **Real/paper:** **REAL** — 65 `SELL_EXECUTED` events, **all `LIVE_RECONCILED`** from IBKR.
- **data_is_real can safely be true:** **YES**, per the existing fail-closed rule
  (`LIVE` / `LIVE_RECONCILED` → true; `DRY_RUN` / `SIMULATED` / `""` / unknown → false).
- **Required fields available:** `event_type`, `execution_mode`, `ticker`, `strategy`,
  `setup_type`, `netto_pnl` / `pnl_abs` / `profit_abs`, `pnl_pct` / `netto_pnl_pct`,
  `quantity`, `price`, `sell_reason`, `trade_id`, `exec_ids`, `broker_source`,
  `cycle_id`, `session_id`, `timestamp`.
- **Missing / weak fields:** `realized_pnl` often null (use `netto_pnl`); commission data
  absent (`commission_report_missing` warning → net PnL may exclude fees); no per-trade
  `regime` or `score`.
- **Risks / limitations (important):**
  - **Effective sample = ~1 unique trade.** All 65 `SELL_EXECUTED` share
    `trade_id="TRD-1"`, `exec_ids="E1"`, `ticker="LUNR"`, `strategy="BREAKOUT"`,
    `netto_pnl=+5.0 (+25%)`. They are the **same broker-managed exit re-logged across
    29 reconciliation cycles**. The adapter's `(trade_id, exec_ids)` dedup correctly
    collapses them to **one** outcome. So the stream is *real* but *statistically
    negligible right now*.
  - `trade_id` counter looks low/reused (`TRD-1`), so dedup must stay strict.
  - Fees excluded from net PnL on at least some fills (slightly optimistic).
  - All-wins (1/1) — no variance to learn from yet.

### 3.2 Options side is not a real source yet

The Options streams are PAPER (and partly test fixtures). They must stay
`data_is_real: false`. They become useful only after NEXT-016 real-chain paper soak
adds provenance-flagged realised paper outcomes — and even then they are *paper*, so
they feed diagnostics, not real-money realness.

---

## 4. Is `data_is_real: true` currently justified?

- **Per-event (stock):** **YES** — a real `LIVE_RECONCILED` IBKR fill is genuinely real.
- **Run/snapshot level (once wired):** **YES but barely** — exactly one unique real
  closed trade exists. Flipping the tactic snapshot to `data_is_real: true` would be
  honest (real data is present), **but** the derived analytics must stay fail-closed:
  the statistical floor (QA-016) and correlation diagnostic (QA-019) will correctly
  report `DIAGNOSTIC_ONLY` until many more unique real trades accrue.
- **Options:** **NO** — paper/test only.

**Conclusion:** real stock outcomes exist and `data_is_real: true` is provenance-justified,
but the ecosystem should treat tactic *conclusions* as `DIAGNOSTIC_ONLY` until soak
(NEXT-016) grows the unique-trade count. Wiring fixes the *blocker*; soak fixes the *signal*.

---

## 5. Minimal read-only adapter design

The adapter **already exists and is tested** — `adapters/nova_botv2_trade_adapter.py::NovaBotV2TradeAdapter`
(11 tests in `tests/test_nova_botv2_trade_adapter.py`). So "design" here is mostly the
**wiring + run-level provenance extension**, not new adapter code.

- **Input files:** `Apps/NovaBotV2/data/results/trade_events.jsonl` (read-only; tail-capped at 16 MB).
- **Output event schema:** `core/tactic_event.TacticalEvent` with
  `event_type = TRADE_OUTCOME`, `source_bot = NovaBotV2`, `strategy_id` from
  `strategy`/`setup_type`, `realized_pnl` from the first present PnL field,
  `outcome` ∈ {WIN, LOSS, BREAKEVEN, PENDING}, and provenance in
  `metadata["data_is_real"]` plus `execution_mode`, `ticker`, `trade_id`, `exec_ids`, etc.
- **Provenance fields & rules:**
  - per-event: `data_is_real = execution_mode ∈ {LIVE, LIVE_RECONCILED}` (fail-closed).
  - **new run-level rule (to add):** the run/snapshot `data_is_real` is true iff
    **≥1 ingested `TRADE_OUTCOME` event has `metadata["data_is_real"] == True`** AND no
    untrusted/generic `--source-dir` was mixed in (mirror the existing
    `derive_run_provenance` taint rule). Implement as a stock-stream assessment
    analogous to `assess_nova_options_source`, then combine sources.
- **Fail-closed rules:** missing file → error + no events; unparseable line → skip +
  record error; non-`SELL_EXECUTED` → ignored; missing/unknown `execution_mode` → not
  real; missing PnL → `PENDING`; dedup on `(trade_id, exec_ids)` keeps the most-reconciled copy.
- **Tests needed (for the wiring task, not this doc):**
  1. runner loads `NovaBotV2TradeAdapter` when the new `--nova-botv2-dir` flag is passed;
  2. run-level `data_is_real` flips **true** given a fixture with ≥1 `LIVE_RECONCILED`
     `SELL_EXECUTED`, and stays **false** for paper/DRY_RUN-only or generic-mixed input;
  3. snapshot then passes canonical conformance (`data_is_real` true) → Bridge VALID;
  4. dedup collapses the re-logged single trade to one outcome (guards the TRD-1/E1 case);
  5. broker-free guardrail still passes (no broker imports introduced).

---

## 6. Recommended implementation plan for NEXT-008/009 (runtime — OUT OF SCOPE here)

1. Add a `--nova-botv2-dir` (default `Apps/NovaBotV2`) arg to `tools/run_tacticbot.py`;
   resolve `data/results/trade_events.jsonl` under it.
2. When set, instantiate `NovaBotV2TradeAdapter`, `load()`, extend `events`, collect errors
   (read-only; the adapter already defaults to the correct path).
3. Extend `utils/source_provenance.py` with a stock-stream assessment + combine into
   `derive_run_provenance(...)` so run-level `data_is_real` reflects real ingested outcomes
   (taint stays: generic/untrusted mixing forces false).
4. Add the tests in §5. Run targeted tests in the broker-free venv.
5. Keep it advisory/read-only; **no** writes to NovaBotV2, no broker, no scheduler.
6. Land behind the existing review gate; only enable in the advisory cadence once NEXT-003
   timing is approved (do not auto-promote).

This is a runtime change and must be its own reviewed task — it is intentionally **not**
performed here.

---

## 7. What remains for NEXT-016 (soak / validation)

- **Stock side:** the live pilot must produce **more unique closed trades** (today: 1).
  Until then, QA-016 floor and QA-019 correlation correctly stay `DIAGNOSTIC_ONLY`.
  Validation: confirm dedup yields the true unique-trade count each run and that net PnL
  fee-handling is understood.
- **Options side (NEXT-016 proper):** make the real-chain fetcher the default research
  source so paper outcomes are provenance-flagged; accumulate ≥20 trading days.
- **Correlation (QA-019):** needs ≥30 overlap days of outcomes from **both** books; the
  options book is paper, so stock-vs-options correlation stays blocked until provenance
  and overlap exist.
- **Gate:** run the advisory cadence (NEXT-003, manual for now) so both streams grow;
  re-check the NovaBridge contract-check / freshness panel until NovaTacticBot reads
  VALID/FRESH/real and its report sections move off `DIAGNOSTIC_ONLY` on their own floors.

---

## 8. Safety

This document changed no code, producer output, scheduler, `.env`, live-arm, broker,
order, or live-cycle state. Inspection of NovaBotV2 / NovaBotV2Options was strictly
read-only (no execution). The wiring in §6 is a recommendation for a separate,
reviewed task and is deliberately not implemented here.
