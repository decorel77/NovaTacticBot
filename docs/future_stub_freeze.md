# Future-Ecosystem Bot Stub Freeze (REPAIR-012)

**Date:** 2026-06-10
**Mode:** ADVISORY_ONLY = True
**Status:** FROZEN — human promotion required
**Authority:** NOVA repair queue REPAIR-012; rationale in
`Vault/Handover/NOVA_FUTURE_BOTS_ASSESSMENT.md` (default stance: **DO NOT BUILD YET**).

---

## Why

The `FUTURE_ECOSYSTEM` phase holds planning-only stubs for future data-source bots.
Left as ordinary `FUTURE` tasks they could be picked up or counted as actionable
before a deliberate human decision. This freeze makes accidental promotion impossible
without an explicit, reviewed code+test change. TacticBot stays advisory-only; no
future stub adds a broker import, an execution path, or a dispatch surface.

## What is frozen

Each task below carries a machine-readable `"frozen": true` + `"freeze"` block in
`data/system/task_queue.json` declaring it **future, non-dispatchable, non-executable,
no broker access, no live trading, human-promotion-required**.

| Task ID | Future bot |
|---|---|
| `TACTIC-FUTURE-001` | LoggingBot data source |
| `TACTIC-FUTURE-002` | ResearchBot fundamental data |
| `TACTIC-FUTURE-003` | NewsBot sentiment |
| `TACTIC-FUTURE-004` | MacroBot macro regime |
| `TACTIC-FUTURE-005` | TaxBot realized-gains |

## Enforcement

`tests/test_future_stub_freeze.py` pins the **exact** frozen set and asserts:
- every `FUTURE_ECOSYSTEM` task is frozen (a new stub cannot slip in unfrozen);
- frozen tasks are never `TODO`/`DONE` (cannot enter actionable/done counts);
- no adapter/module exists for any frozen future bot (non-executable).

## Promotion (the only way out of the freeze)

A future bot is promoted **only** by deliberate human decision once its matching
trigger condition in `NOVA_FUTURE_BOTS_ASSESSMENT.md` is met. Promotion must, in the
same change: remove the task's `freeze` block and update
`tests/test_future_stub_freeze.py`.
