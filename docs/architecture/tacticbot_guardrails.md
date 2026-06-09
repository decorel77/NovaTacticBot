# NovaTacticBot Guardrails

## Purpose

These guardrails define the hard boundaries of NovaTacticBot behavior.
They are permanent. They are not configurable. They are not overridable by any runtime flag.

---

## ADVISORY_ONLY = True

NovaTacticBot is a read-only observer and analyst.

It **studies** outcomes.
It **compares** tactics.
It **identifies** patterns.
It **discovers** weaknesses.
It **produces** intelligence reports.

It does **nothing else**.

---

## Hard Rules

### No Broker Access

- No imports of `ib_insync`, `ibapi`, or any IBKR library
- No TWS connections
- No paper trading connections
- No broker API calls of any kind

### No Order Execution

- No order creation
- No order submission
- No order cancellation
- No order modification

### No Portfolio Modification

- No position changes
- No allocation changes
- No cash movement

### No Scheduler Modification

- No writes to any scheduler configuration
- No task queue modifications in other bots
- No cron modification

### No Repository Modification

- NovaTacticBot may only write within its own repository directory
- No writes to NovaBotV2, NovaBotV2Options, MarketRegimeBot, NovaAllocationBot, NovaBridge, or NovaMemoryBot
- No `.env` modifications anywhere in the ecosystem

### No Automatic Parameter Optimization

- NovaTacticBot may identify that a parameter appears suboptimal
- NovaTacticBot may **report** this in its intelligence output
- NovaTacticBot may **never** apply the change itself

### No Self-Modifying Behavior

- NovaTacticBot may not rewrite its own source code
- NovaTacticBot may not modify its own configuration at runtime
- NovaTacticBot may not update its own task queue autonomously

### No Autonomous Decision Making

- All analytical findings are advisory only
- Humans review every report before any action is considered
- No finding automatically triggers any downstream system

### No Telegram Execution

- NovaTacticBot may not send Telegram commands
- NovaTacticBot may not invoke Telegram bots on behalf of any system
- NovaTacticBot may not use Telegram as an execution channel

---

## Permitted Operations

| Operation | Permitted |
|---|---|
| Read NovaBotV2Options report files | Yes |
| Read NovaBotV2Options log files | Yes |
| Read NovaBotV2Options CSV exports | Yes |
| Write reports to `data/reports/` | Yes |
| Write system state to `data/system/` | Yes |
| Log to console | Yes |
| Log to file within NovaTacticBot | Yes |
| Call any broker API | **No** |
| Write to any other bot's directory | **No** |
| Modify `.env` files | **No** |
| Send Telegram messages | **No** |
| Execute trades | **No** |

---

## Enforcement

Guardrail compliance is enforced by:

1. **Import-level**: Banned imports are listed in `utils/guardrails.py`. The module raises `ImportError` on startup if banned packages are present.
2. **Code review**: All contributions must pass a guardrail review verifying no execution paths exist.
3. **Test suite**: `tests/test_readonly_behavior.py` verifies no execution-related modules are importable from TacticBot code paths.

---

## Guardrail Violations

If a contribution attempts to add any execution capability:

1. The PR is rejected
2. The violation is documented
3. The feature is escalated to human review before any modified version is accepted

---

## Philosophy

> NovaTacticBot knows everything. It controls nothing.
> Intelligence without action is wisdom. Action without intelligence is risk.
> TacticBot provides the wisdom. Humans accept the risk.
