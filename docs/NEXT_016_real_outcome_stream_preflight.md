# NEXT-016 Real Outcome Stream Preflight

Date: 2026-06-12

## Scope

Read-only verification of the NEXT-008/009 NovaBotV2 stock outcome stream wiring.
No NovaBotV2 live cycle, broker/order path, scheduler, `.env`, live-arm, risk,
capital, or producer output was touched.

## Commands / checks run

1. Attempted the normal advisory runner:
   `.\.venv\Scripts\python.exe tools\run_tacticbot.py --nova-botv2-dir C:\NovaGPT\Apps\NovaBotV2 --report-name NEXT_016_real_outcome_preflight_runtime.md`
   - Guardrails passed.
   - `NovaBotV2TradeAdapter` loaded 1 event from `C:\NovaGPT\Apps\NovaBotV2\data\results`.
   - The run stopped before snapshot/report persistence because this sandbox cannot write to `data\reports`.

2. Re-ran the same NovaTacticBot adapter, analytics, provenance, report, and
   artifact writer code with runtime outputs redirected to sandbox temp:
   `C:\Users\CodexSandboxOffline\.codex\.sandbox\tmp\novatacticbot-next016-real-run`

3. Ran NovaBridge read-only validation against the redirected diagnostic snapshot:
   - `validate_snapshot_file(..., require_fresh=True)` => `VALID`
   - `run_contract_check({"NovaTacticBot": diagnostic_snapshot}, migrated_producers={"NovaTacticBot"}, require_fresh=True)` => `PASS`

4. Ran the default NovaBridge freshness panel:
   `.\.venv\Scripts\python.exe tools\ecosystem_freshness_panel.py --format text`

5. Ran targeted NovaTacticBot tests:
   `.\.venv\Scripts\python.exe -m pytest --basetemp C:\Users\CodexSandboxOffline\.codex\.sandbox\tmp\novatacticbot-next016-pytest tests\test_nova_botv2_trade_adapter.py tests\test_source_provenance.py tests\test_run_tacticbot_nova_botv2_wiring.py tests\test_statistical_floor.py tests\test_report_generator.py tests\test_readonly_behavior.py`
   - Result: 65 passed.

## Diagnostic result

- Source path: `C:\NovaGPT\Apps\NovaBotV2\data\results\trade_events.jsonl`
- Raw `SELL_EXECUTED` lines observed: 65
- Real `SELL_EXECUTED` lines observed: 65
- Deduplicated NovaTacticBot outcomes loaded: 1
- Unique `(trade_id, exec_ids)` pairs: 1, currently `(TRD-1, E1)`
- Run-level `data_is_real`: `true`
- `input_source`: `NovaBotV2`
- `broker_execution`: `false`
- `advisory_only`: `true`
- `live_trading_active`: `false`

The diagnostic artifact proves the stock outcome stream can produce a
schema-correct, fresh, real NovaTacticBot snapshot when runtime persistence is
allowed.

## Bridge status

The redirected diagnostic snapshot is Bridge-valid:

- Schema verdict: `VALID`
- Freshness verdict: `VALID`
- Contract check: `PASS`

The default Bridge freshness panel still reports the checked-in/runtime
`C:\novagpt\Apps\NovaTacticBot\data\system\result_snapshot.json` as blocking
because this sandbox could not update the normal NovaTacticBot runtime artifact:

- Default panel NovaTacticBot `data_is_real`: `false`
- Default panel NovaTacticBot `event_count`: `0`
- Default panel NovaTacticBot reason: `data_is_real is False - snapshot is fixture/unverified`

Therefore the wiring is verified, but the ecosystem default panel will clear only
after a normal NovaTacticBot runtime can write its own `data/system` artifacts.

### Manual normal runtime refresh

Joeri manually ran the normal NovaTacticBot runtime locally with write access:

`.\.venv\Scripts\python.exe tools\run_tacticbot.py --nova-botv2-dir C:\NovaGPT\Apps\NovaBotV2 --report-name NEXT_016_real_outcome_runtime_refresh.md`

Observed result:

- Guardrails passed.
- Broker packages were not detected.
- `NovaBotV2TradeAdapter` loaded 1 deduplicated event from `C:\NovaGPT\Apps\NovaBotV2\data\results`.
- `data_is_real` provenance: trusted NovaBotV2 stock outcomes verified: 1 real deduplicated outcome event loaded.
- Report written to `data\reports\NEXT_016_real_outcome_runtime_refresh.md`.
- `data\system\result_snapshot.json` written.
- Canonical schema conformance passed.
- `ADVISORY_ONLY` remained true; no trades or modifications were made.

After that refresh, NovaBridge's default ecosystem freshness panel returned `PASS`.
NovaTacticBot is now observed by the default panel as:

- Schema verdict: `VALID`
- Freshness verdict: `FRESH`
- `data_is_real`: `true`
- Blocking: `no`
- Reason: `ok`

This clears the realness/blocking preflight gap for NovaTacticBot's normal
runtime artifact. It does not clear the statistical-confidence soak requirement.

## Statistical confidence gap

`data_is_real=true` is provenance-justified for the stock outcome stream, but it
does not imply strategy confidence. The current deduplicated sample is only 1
unique real trade, so the report must remain `DIAGNOSTIC_ONLY`.

The report generator now emits:

`Statistical confidence: DIAGNOSTIC_ONLY (completed trades 1 < 30)`

Required soak threshold before using TacticBot conclusions for decisions:

- At least 30 deduplicated real stock `TRADE_OUTCOME` events for the relevant
  strategy/regime bucket.
- Fresh real provenance must remain `true`.
- Generic/untrusted sources must not be mixed into the decision sample.
- Statistical floor and correlation diagnostics must pass their own gates before
  any label stronger than diagnostic/advisory is used.

## NEXT-016 status

Realness/blocking preflight is cleared: NovaTacticBot can write a normal
schema-valid, fresh, real runtime snapshot from the NovaBotV2 stock outcome
stream and NovaBridge's default panel now passes it.

NEXT-016 is still not fully complete. Statistical confidence remains
`DIAGNOSTIC_ONLY` until the real stream soaks to at least 30 deduplicated real
stock outcomes for the relevant decision bucket. Current unique real outcomes:
1.
