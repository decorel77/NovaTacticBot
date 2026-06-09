# NovaTacticBot — Vision Document

## Why TacticBot Exists

Every trading system generates data. Most systems consume that data only to make the next
decision. They rarely step back and ask:

- Which strategies actually worked, and under what conditions?
- Were our recommendations high quality before the market confirmed them?
- Do we reject too many good ideas? Or too few bad ones?
- Does our performance depend on regime in ways we haven't measured?

NovaTacticBot exists to answer these questions.

It is the reflective layer of the NOVA ecosystem — the part that watches everything else,
measures everything else, and reports back with honest, unfiltered intelligence.

---

## The NOVA Ecosystem

```
┌─────────────────────────────────────────────────────────────────┐
│                        NOVA Ecosystem                           │
│                                                                 │
│  NovaBotV2          → stock decisions                           │
│  NovaBotV2Options   → options decisions                         │
│  MarketRegimeBot    → classifies market environments            │
│  NovaAllocationBot  → recommends capital allocation             │
│  NovaBridge         → coordinates ecosystem workflow            │
│  NovaMemoryBot      → stores ecosystem knowledge                │
│                                                                 │
│  NovaTacticBot      → studies all of the above                  │
│                       reports on all of the above               │
│                       changes none of the above                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## How TacticBot Differs From Every Other NOVA Bot

### NovaBotV2

NovaBotV2 **creates** stock decisions. It acts on signals in real time.

TacticBot **studies** those decisions after the fact. It never creates decisions.

### NovaBotV2Options

NovaBotV2Options **creates** options decisions. It manages positions.

TacticBot **analyses** those decisions for patterns, biases, and regime-specific performance.
It never touches positions.

### MarketRegimeBot

MarketRegimeBot **classifies** the current market environment and feeds that classification
to other bots.

TacticBot **measures** how well regime classifications correlated with actual outcomes.
It never reclassifies markets.

### NovaAllocationBot

NovaAllocationBot **recommends** how capital should be distributed across strategies.

TacticBot **evaluates** whether those recommendations led to better risk-adjusted outcomes.
It never changes allocations.

### NovaMemoryBot

NovaMemoryBot **stores** ecosystem knowledge — decisions, context, history.

TacticBot **consumes** that history to produce analytical intelligence.
It contributes reports back to the ecosystem's understanding, but never modifies bot behavior.

---

## TacticBot's Role

### TacticBot Learns

TacticBot builds a longitudinal record of tactical outcomes. Over time it develops a
statistical picture of what works, what does not, and why.

### TacticBot Observes

TacticBot is passive. It reads outputs. It never interferes with the systems producing them.

### TacticBot Reports

TacticBot produces structured intelligence reports — markdown documents that a human analyst
can read, verify, and act upon if they choose.

### TacticBot Never Acts

No trade. No recommendation that triggers an action. No parameter change.
Every finding is advisory. Every decision belongs to a human.

---

## The Long-Term Vision

In its mature form, NovaTacticBot becomes the **tactical brain** of NOVA:

- It identifies which strategies should be scaled up or down in the current regime
- It detects when a bot's edge is eroding before the drawdown becomes severe
- It surfaces hidden correlations between bot decisions and market microstructure
- It produces weekly intelligence briefings that inform human operators

All of this is **advisory**. A human reads the briefing. A human decides what to change.
TacticBot never touches the controls.

---

## Phase 1 Scope

Phase 1 focuses on NovaBotV2Options as the first data source. The architecture is designed
from day one to support all NOVA bots. The adapter layer is generic. The data contract is
universal. The analytics engine operates on the contract, not on any bot-specific format.

Adding NovaBotV2, MarketRegimeBot, NovaAllocationBot, or NovaBridge in future phases requires
only adding a new adapter — no changes to the core engine or reporting layer.

---

## Design Principles

1. **Read-only first**: If an operation is not read-only, it does not belong here.
2. **Contract-driven**: All bots speak the same language through the tactic data contract.
3. **Adapter isolation**: Source bot details are contained in adapters, not in the engine.
4. **Human-in-the-loop**: Every output is for human consumption. Nothing is automated.
5. **Honest analytics**: TacticBot reports what the data says, not what we want it to say.
