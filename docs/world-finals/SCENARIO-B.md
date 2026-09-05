# Scenario B — end-of-life part, three product lines, 48 hours

**Locked 4 Sep 2026.** WorkBuddy issued two tailored topics under the heading
*Continuity · Electronics Manufacturing*. We are taking B.

## The two topics, verbatim

> **A.** A hardware company is producing 5 different PCB designs simultaneously. Every role
> along the supply chain—procurement specialists, design engineers, production managers, and
> quality inspectors—can use this solution. Show how each role relies on the tool to keep
> their own work on track when a single component runs short, so the shortage does not
> cascade across all 5 projects.

> **B.** A critical component just went end-of-life, affecting 3 product lines. The
> engineering team needs approved substitutes within 48 hours. How does your tool coordinate
> the cross-team response—design validates alternatives, procurement checks availability, and
> production confirms assembly compatibility?

## Why B

B partitions cleanly onto rules that already exist. A does not.

The three roles B names map onto `RULES` (`engine/rules.py:1315`) with nothing missing and
nothing spare:

| B's role | Rules it owns |
|---|---|
| Design validates alternatives | `voltage_overlap` · `interface_role_match` · `pin_budget` · `current_budget` · `thermal_dissipation` · `temperature_rating` · `energy_budget` · `rail_coverage` |
| Procurement checks availability | `availability` |
| Production confirms assembly compatibility | `footprint` |

The central action for a part going end-of-life is `swap`, the first entry in the repair
vocabulary (`reviewer.py:44`) and the one the engine handles best. `/bom/validate`
(`api/app.py:204`) already accepts an existing BOM and runs all ten rules without touching
the planner, which is the exact shape of *"here are three product lines that already exist,
one part just died."*

B is also a literal instance of **Chained Collaboration**, one of the three sanctioned
upgrade paths, whose own example in the deck is a linear chain. Design → procurement →
production is that chain.

## Why not A

A names **four** roles, and the fourth is quality inspectors, which maps to nothing in the
ten rules. Satisfying it would mean inventing a QA concept for the pitch.

Worse, *"keep their own work on track"* across five concurrent projects and *"the shortage
does not cascade"* imply deciding which board gets the remaining stock. That is inventory
allocation across a portfolio — a shared project-management system, not a board analyser.
It is not built, it is not close, and it is not what the engine is for.

The rubric agrees. Efficiency Gains wants a quantified before/after, and B hands us the
clock in the prompt: **48 hours**. A's benefit is a counterfactual — the cascade that didn't
happen — which cannot be shown on stage. And a five-minute slot cannot carry five projects
and four dashboards legibly.

## The argument the pitch is built on

The cross-team response *is* the bottleneck, and it is a sequence of round trips.

Today: design proposes a candidate, procurement replies no stock, design tries again,
production says wrong footprint, repeat. Each leg is a day or two of email. That is where
the 48 hours goes.

Continuity does not coordinate those people by passing their messages faster. It removes
most of the round trips, because every candidate is checked against all three departments'
constraints **simultaneously**, before anyone sees it. The engine already re-checks the
whole board after every change; this is that same property applied across departments
instead of across rules.

## What role specificity has to mean

The prompt's verb is *coordinate*, not *serve*. It asks for a chain with handoffs, not three
products. Three things have to be true, and building three separate dashboards is the wrong
answer to all of them:

1. **Each role owns a constraint the others cannot silently override.** Today all ten rules
   are hardcoded and answer to nobody. An engineer who finds an electrically perfect
   substitute that is not on the approved-vendor list should be stopped by procurement's
   rule, not by procurement's email three days later.
2. **Each role sees the same verdict in its own terms.** One finding, three renderings — a
   view layer over one shared result, never three engines.
3. **The handoff is visible, and it is `escalate`.** Today escalation asks the one user
   through `interrupt()`. Here it routes to the role that owns the answer.

## Gap analysis

Already built:

- All ten rules and the whole-board re-check after every repair
- `swap` as a repair action, with `policy.py` validating every proposal
- `/bom/validate` for boards that already exist
- `escalate` + LangGraph `interrupt()` for suspending on a decision
- `precedents` — how a conflict signature was resolved last time

Needs building:

| | Item |
|---|---|
| 🔴 | **Multi-board.** One EOL part evaluated across three BOMs at once. Today Continuity validates one board at a time. This is the genuinely new machinery, and the most demoable moment in the scenario — the substitute that works on line 1 may fail the thermal budget on line 3. |
| 🔴 | **Rule ownership.** Tag each rule with an owning role so findings can be attributed and escalations routed. |
| 🟡 | **Approved-vendor list.** B says *"approved"* substitutes. An AVL is the natural procurement-owned constraint and slots in beside `availability`, plausibly as an eleventh rule. |
| 🟡 | **Role-specific rendering** of a shared finding. |
| 🟡 | **Escalation addressed to a role** rather than to "the user". |

## Open — not yet researched

- The real-world EOL response flow. What actually happens when a PCN lands: who is notified,
  what the current tooling is, how long each leg really takes. The round-trip argument above
  is reasoning from the interviews and from how the rules partition, **not** from sourced
  industry data. It needs grounding before it goes in a pitch deck.
- How this is demoed on stage in the time available.
- How far to go with WorkBuddy. **The deck does not require it.** In the Agent track
  brief WorkBuddy appears only as the question-setter (由 workbuddy 定向出题); the sole
  scoring mention is a permissive bonus box (可以充分结合WorkBuddy功能), and criterion 4.2
  names no product. Three roles chained in sequence is close to WorkBuddy's Expert Group
  concept, and its Open Platform opened Skill / Expert / Connector to developers on 2 Sep,
  so there is a real affinity — but rebuilding onto it would spend most of the seven days
  chasing at most 10 points while risking the 20 that depend on the demo working.
  Current position: install and learn the vocabulary, do not port the product.
