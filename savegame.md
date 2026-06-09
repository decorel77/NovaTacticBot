# NovaTacticBot — Savegame

**Session:** 2026-06-09  
**Milestone:** Phase 2 — Real Data Connection — COMPLETE  

---

## Session Summary

Connected NovaTacticBot to the real NovaBotV2Options repository in a strictly
read-only manner. Generated first real intelligence report.

### Key Decisions

1. **Two-adapter strategy**: `NovaBotV2OptionsAdapter` for real directory structure; existing `OptionsAdapter` retained for generic JSON/CSV/log files.
2. **Primary source: decision_audit_trail.jsonl** — richest data with regime, score, risk_reward, and decision context.
3. **PnL cross-reference**: recommendation_accuracy.json cross-referenced to attach realized_pnl/outcome to accepted signals.
4. **TRADE_OUTCOME vs RECOMMENDATION**: ACCEPTED + realized_pnl present → TRADE_OUTCOME; ACCEPTED + no PnL yet → RECOMMENDATION (PENDING).
5. **Chain rejection deduplication**: options_events.jsonl has 356 repeat log lines for the same contract; deduplicated to 1 unique contract.
6. **SIDEWAYS → NORMAL**: NovaBotV2Options uses SIDEWAYS; mapped to NORMAL in universal contract.
7. **`--warn-broker-env` flag**: Development override for machines with ib_insync installed. Logs a prominent WARNING but does not block the run.
8. **AdapterDiagnostics**: Each load records files found/missing, records skipped, schema mismatches, parse errors.

### Real Data Findings

- 17 audit trail records loaded (16 sig-xxx + 1 s99 test record)
- 356 chain rejection log lines → deduplicated to 1 unique AAPL contract
- 5 paper trades have realized PnL in recommendation_accuracy.json
- LONG_CALL: 100% win rate (2/2), avg PnL $123.80
- CASH_SECURED_PUT: 33% win rate (1/3), avg PnL -$23.05
- Rejection rate: 100% of actionable signals (all recommendations either rejected or awaiting outcome)
- Open question: many PENDING outcomes (61% missing) — recommend cross-referencing with paper_positions data in future phases

---

## Files Created/Modified This Session

```
CREATED:
  adapters/nova_options_adapter.py
  tests/test_nova_options_adapter.py
  tests/fixtures/nova_options/data/logs/decision_audit_trail.jsonl
  tests/fixtures/nova_options/data/logs/options_events.jsonl
  tests/fixtures/nova_options/data/reports/recommendation_accuracy.json
  tests/fixtures/nova_options/data/reports/strategy_performance.json
  tests/fixtures/nova_options/data/reports/regime_performance.json
  data/reports/tacticbot_report.md   (first real report)

MODIFIED:
  utils/tactic_report_generator.py   (diagnostics + supplementary sections)
  tools/run_tacticbot.py             (--nova-options-dir, --warn-broker-env)
  CURRENT_STATE.md
  savegame.md
  task_queue.json
```

---

## Resume Instructions

Next session should:

1. Run tests: `python -m pytest tests/ -v`
2. Decide next phase: Multi-Bot Support (adapters for NovaBotV2, MarketRegimeBot, etc.) or Bias Detection
3. For bias detection, add `options_paper_positions.py` data as a source for open positions
4. Check if `data/reports/signal_lifecycle_summary.json` can enrich the event timeline

---

## Open Items

- [ ] Cross-reference paper positions for open paper trades (get realized PnL when they close)
- [ ] The "s99" test record in audit trail has no cycle_id — decide if test records should be filtered
- [ ] Consider reading `data/reports/paper_trade_outcomes.md` for additional context
- [ ] Plan virtualenv separation so ib_insync guardrail doesn't fire in normal development
