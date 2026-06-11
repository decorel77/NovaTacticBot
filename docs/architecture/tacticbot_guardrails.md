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

Guardrail compliance is enforced at two levels:

1. **Runtime package guardrail**: broker-capable packages listed in
   `utils/guardrails.py` are checked at startup by `run_all_checks()`. If any
   banned broker package is importable in the active interpreter, startup raises
   `GuardrailViolation`.
2. **Source-scan test guardrail**: standard-library execution/network modules
   listed in `utils/guardrails.py` under `_BANNED_MODULES` are enforced by
   `tests/test_readonly_behavior.py`. The test parses production source with
   Python AST and fails if production code imports banned modules such as
   `socket`, `subprocess`, `ftplib`, `smtplib`, or `imaplib`, or calls
   `os.system(...)`.
3. **Code review**: all contributions must pass guardrail review verifying no
   execution paths exist.

The banned module list is not a runtime import hook. It is a test-enforced
source policy. Tests may import utilities such as `subprocess` to verify
behavior; production source may not.

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
