# Continuity 2.0 — specification

What we are building for Scenario B. Read [SCENARIO-B.md](SCENARIO-B.md) for why, and
[FLOW.md](FLOW.md) for the narrative version. This is the contract.

## What it does, in one sentence

When a component goes end-of-life, Continuity works out which of your products are affected,
computes whether each candidate replacement actually works **on each affected board**, and
produces an engineering change request per board with the evidence attached and the open
decisions routed to whoever owns them.

## What is wrong with how it is done today

A parametric cross-reference proposes candidates on matching attributes, an engineer judges
whether they work, and **the same replacement is applied to every affected design in one
step** — because checking each board by hand is too slow. Whether a substitute works depends
on the board it sits in. The right answer differs per board, and the industry's own tooling
assumes it does not.

---

## The flow

```mermaid
flowchart TD
    PL[5 product lines<br/>BOM + operating profile each]
    LISTS[AML: qualified manufacturer parts<br/>AVL: approved sources]

    MAIL[Mailbox connector] --> PARSE
    DROP[PDF dropped in] --> PARSE
    PARSE[1 - Parse the notice<br/>model fills declared fields only]

    PARSE --> FIELDS[MPN, notice type, effective date,<br/>last-time-buy, recommended replacement]
    FIELDS -->|unparseable| HUMAN([Escalate - a person reads it])

    FIELDS --> EXPOSE[2 - Exposure<br/>match MPN across every line<br/>deterministic, no model]
    PL --> EXPOSE
    EXPOSE --> AFFECTED[3 of 5 lines affected]

    AFFECTED --> CAND[3 - Candidates<br/>manufacturer recommendation first,<br/>then model-proposed alternates]

    CAND --> FANOUT[4 - Fan-out<br/>every candidate x every affected line]
    FANOUT --> EVAL[evaluate board<br/>all rules, whole board,<br/>using that line's operating profile]
    EVAL --> LABEL[5 - Label every check<br/>satisfied / failed / not applicable /<br/>not assessed / evidence missing]

    LABEL --> MATRIX[6 - The matrix<br/>candidates down, lines across<br/>each cell owned by a department]

    MATRIX --> Q{Does any candidate<br/>satisfy every line?}

    Q -->|no candidate clears all| PERLINE[Per-line decision<br/>a different part per board]
    Q -->|clears all, but a list blocks it| GATE
    Q -->|clears all, already qualified| ECR

    PERLINE --> GATE

    GATE{7 - What is blocked?}
    GATE -->|MPN not on AML| ENGQ([Engineering + Quality<br/>qualify the part])
    GATE -->|MPN fine, source not on AVL| PROC([Procurement<br/>approve the source])
    LISTS --> GATE
    ENGQ --> RESUME
    PROC --> RESUME
    RESUME[decision recorded<br/>against the change]

    RESUME --> ECR
    ECR[8 - One change request per line<br/>baseline, trigger, proposal, evidence,<br/>what was not assessed, cost, approvals]

    ECR --> BOARD[9 - Board consequence<br/>footprint identical = drop-in<br/>footprint differs = layout work]
    BOARD --> RECORD[10 - Record<br/>precedent + audit trail]
```

### Reading the diagram

**Nothing is applied.** The run ends at a change request awaiting approval. A released design
cannot be altered without sign-off, and a tool that silently rewrites production BOMs is
describing an audit finding rather than a product.

**The operating profile enters at `evaluate`, not at ingestion.** It is what makes the answer
board-specific, and it is the reason a KiCad file alone is not enough — connectivity and
geometry are in the file, load current and ambient are not.

**Two gates, not one.** An unqualified manufacturer part is engineering and quality's
decision. A qualified part from an unapproved source is procurement's. Conflating them was
the error the second research pass caught.

**The matrix can end without a winner.** If no candidate clears every line, the answer is a
different part per board — which is the whole thesis, not a failure of the run.

---

## Data model

### Product line
Replaces "project". The brief's own word, and it names a thing the company ships rather than
an engineer's workspace.

| Field | Note |
|---|---|
| `bom` | Component instances: refdes, manufacturer, exact MPN, footprint, populated? |
| `operating_profile` | See below. Required before any thermal claim. |
| `board` | Optional KiCad artifact, for the footprint consequence |
| `revision` | Which revision these values describe |

### Operating profile
The input that makes us different, and an honest adoption cost.

| Field | Why |
|---|---|
| `v_in` and tolerance | Dissipation depends on the drop |
| `i_load_max` | Continuous. Peaks recorded separately, with duration. |
| `ambient_max_c` | **The local ambient, not the component grade.** These were conflated. |
| `mounting` | Copper area and board construction — the basis for any θJA we apply |
| `source` | Where each number came from. A guess is labelled a guess. |

### AML and AVL are separate lists

- **AML** — manufacturer parts qualified for an internal part number.
- **AVL** — sources permitted to supply them.

A part can be qualified with no approved source, and a source can be approved for a part that
is not qualified. Different lists, different owners, different gates.

---

## Rules

Ten today. Three are added, and one existing rule is weaker than its name suggests.

**`footprint` is inert on our boards.** Its docstring says it *"never fails a board — it only
ever raises a flag"*, and it returns nothing at all unless the brief stated a size limit. So
"ten rules ran" was overcounting before coverage labels existed.

| New rule | Question it answers | Why it is not covered today |
|---|---|---|
| **`power_dissipation_max`** | Does computed dissipation exceed the part's own stated absolute maximum? | `PartSpec` has no field for it. A part can sit inside its junction limit and over its power rating — this is a different question from `thermal_dissipation`, and missing it is how a 340 mW load passed against a 300 mW ceiling. |
| **`footprint_compatibility`** | Does the candidate fit the land pattern the outgoing part leaves, and do its pin functions map? | Needs a **baseline** — the part being replaced — which no rule currently has. Distinct from `footprint`, which asks whether a part is under a size target. Both keep their job. |
| **`capacitor_requirements`** | Does the candidate's stated output-capacitor requirement conflict with what is on this board? | Named by research as the first thing a hardware engineer attacks on an LDO substitution. Explicit violations are checkable without simulation: AMS1117 wants 22 µF tantalum, TI's TLV1117LV says *"do not use an electrolytic output capacitor"*, NCP1117 specifies an ESR window. |

`capacitor_requirements` reports **failed** on an explicit conflict and **evidence missing**
where the requirement is unpublished. It does not claim stability — that needs simulation —
but it turns the first-attack question from *"not assessed"* into an answer.

**AML and AVL are not rules.** They run in the policy layer beside `RULES`. Physics is
derivable from a datasheet; an approval list is derivable from nothing but the company.

### Consequences

**The demo boards gain a capacitor.** Two slots become at least three — regulator, load,
output capacitor — which is more sourcing and also makes them look like boards rather than
fixtures.

**`PartSpec` gains fields**: `p_dis_max`, the θJA mounting condition it was measured under,
and the capacitor requirement (minimum effective capacitance, ESR window, permitted
dielectric).

**`CONSTRAINT_FIELDS` gains entries** so a repair can demand what the new rules check —
`theta_ja_max` so a thermal repair can ask for a better-cooling package class rather than
naming one exact package, `p_dis_min`, and `approved_only` for the policy layer.

---

## Authorisation

The approval gate does not work on the current code, and this is not a detail.

**`/resume` authorises the thread owner.** It calls `store.thread_for_user(thread_id,
user.id)`, so a procurement account cannot resume an engineer's run. Naming a role in the
interrupt payload does not grant anyone the right to answer it.

**Waivers are keyed by `(rule, slot)`** — `graph/state.py:58` — with no candidate or revision.
So an exception approved for one candidate is inherited by the next candidate in that slot.

Both must change for an approval to mean anything:

- A run carries the roles permitted to answer each open decision, and `/resume` checks the
  answering user against that, not against ownership.
- An approval is scoped to **candidate and revision**, and does not survive either changing.
- The record holds identity, timestamp, the rule that fired, and a rationale.

---

## Coverage semantics

A bare "pass" is what lets a green cell mean nothing. Every check reports one of five:

| Label | Meaning |
|---|---|
| **Satisfied** | Checked against stated inputs, and it holds |
| **Failed** | Checked, and it does not hold |
| **Not applicable** | This check has no subject on this board |
| **Not assessed** | We do not perform this check |
| **Evidence missing** | We would check it, but an input is absent or unsourced |

**A cell is green only when every applicable check is satisfied.** Anything unassessed or
missing evidence shows on the cell rather than being buried in a drawer.

### Margin is an attribute, not a sixth label

The engine emits `warn` today for two unrelated things, and they split differently:

- *"runs hot even though 100 °C clears the 125 °C limit"* → **satisfied**, carrying a margin.
  It does hold. It holds narrowly, and the cell shows how narrowly.
- *"could not check — the distributor states no minimum"* → **evidence missing**.

Keeping margin as an attribute rather than a label matters for our own demo: LD1117S33 on the
gateway sits at 100 °C against a 125 °C limit. Calling that anything other than satisfied
would be wrong, and showing it without the margin would be worse — a thin margin is exactly
what an approver needs to see, and it is what makes the choice between one qualified part and
two approved ones a real decision rather than an obvious one.

This is why "nine of ten rules passed" is a number we stop quoting: several rules have no
subject on a two-part board, so the denominator was never ten.

---

## Where the fan-out runs

The matrix does **not** route every cell through the graph. Each cell is one
`evaluate(board)` with a candidate substituted — deterministic, fast, no repair loop, no
interrupt.

The graph's repair loop sits **upstream**: it is what proposes further candidates once the
manufacturer's recommendation fails. So repair generates rows; the fan-out fills them.

This is a deliberate choice against the alternative — routing all nine cells through the
graph — which would inherit repair, interrupts and per-cell checkpointing for a case that
needs none of it. Research estimated that integration alone at several engineer-days, and it
would buy nothing the matrix uses. What the graph still owns is candidate generation and the
approval gates.

---

## What the engine may and may not conclude

| It may say | It may not say |
|---|---|
| This candidate fails `thermal_dissipation` on line C under the stated profile | This candidate is unsuitable |
| Every applicable check is satisfied | This candidate is approved |
| Output-capacitor stability was **not assessed** | The replacement circuit is stable |
| The footprint differs, so the layout changes | The board will work after the change |

The architecture claim survives a hardware engineer only if it is stated precisely. **No
compatibility verdict is produced by a model** is a statement about *who executes the check*.
It does not claim the inputs are independently verified, or that coverage is complete. The
coverage labels are what make that honest rather than a dodge.

---

## Decisions taken

**θJA is quoted, not looked up.** From the datasheet, with the mounting case named.

For the incumbent it changes no verdict, and saying so is stronger than picking a number:
AMS1117 across its entire published range of **46 to 95 °C/W** puts line C between **52 °C and
81 °C** — passing at every value. The conclusion is robust to the whole spread, which is a
better answer to *"where did that number come from"* than a single confident figure.

**One footprint family for the candidates.** All SOT-223, so thermal resistance is the
variable under test rather than being confounded by physical incompatibility. This is why
ME6211 is out: SOT-23-5 does not fit a SOT-223 land pattern on any line, so it never belonged
in the comparison.

| Part | θJA | Role |
|---|---|---|
| AMS1117-3.3 | 46–95, mounting-dependent | Going end-of-life |
| TLV1117LV33 | 62.9 | Candidate |
| LD1117S33 | 110 | Candidate |
| NCP1117ST33 | 160 | Candidate |

**Ambient and component grade are separate fields.** `ambient_max_c` comes from the operating
profile; `temp_range` stays a component grade. Conflating them was a real defect, and it is
what made the fixture's 25 °C ambient sit unexamined beside a 0–70 °C range.

---

## The demo case

Five product lines. Three carry AMS1117-3.3; the other two exist so that "3 of your 5 lines"
means something.

| Line | Supply | Load | Dissipation | Role in the story |
|---|---|---|---|---|
| **A · Sensor node** | 5 V | 150 mA | 0.255 W | The easy case — everything passes |
| **B · Gateway** | 5 V | 400 mA | 0.680 W | Kills the hot candidate on **thermal** |
| **C · Industrial node** | 12 V | 60 mA | 0.522 W | Kills the cool candidate on **voltage** |
| D, E | — | — | — | Do not contain the part |

Computed against a 125 °C junction limit at the stated ambient:

| | A | B | C |
|---|---|---|---|
| **AMS1117-3.3** — today, at its *worst* published θJA (95) | 49 °C | 90 °C | 75 °C |
| **TLV1117LV33** — 62.9 °C/W | 41 °C | 68 °C | **fails: 12 V exceeds its 5.5 V ceiling** |
| **LD1117S33** — 110 °C/W | 53 °C | warm, 100 °C | 82 °C |
| **NCP1117ST33** — 160 °C/W | 66 °C | **fails: 134 °C** | warm, 109 °C |

Three things this buys:

- **Two different rules fire.** `thermal_dissipation` on B, `voltage_overlap` on C. The engine
  is not a thermal calculator with extra steps.
- **The incumbent passes everywhere even at its worst θJA**, so the boards are fine today and
  the substitution is the entire problem. The conclusion is robust to the 46–95 spread.
- **No candidate is free.** LD1117S33 clears all three but runs at 100 °C on the gateway and
  is not on the AML. So the decision put to a human is real: qualify one new part and use it
  everywhere, or run two already-approved parts across three boards.

The PCN recommends **NCP1117ST33** — plausible, since onsemi is a genuine AMS1117 second
source — and it fails the gateway. The manufacturer's own recommendation cooks one of your
boards, which is a documented industry failure mode rather than a contrivance.

---

## How the handoff is shown

The research on enterprise agent evaluation is blunt: *"Nobody puts governance on the
highlight reel"*, and the gap between a demo and something compliance will sign off on is
*"audit logs, human-in-the-loop approvals, and role-based access."* Also worth citing:
**46% of enterprises name integration with existing systems as their primary challenge**
deploying agents.

So the plumbing is the differentiator, and it is shown by its **record**, never by an inbox.

**Intake — the run starts because an email arrived.** Nothing is typed. The first trace line
is *"PCN from Advanced Monolithic Systems, received 09:14"*, sourced from the mailbox. Five
seconds, and it reframes the demo from *I asked a tool* to *the world happened and the system
responded*.

**Handoff — email out, approval in-app.** The send is one-way SMTP, so no round trip sits in
the critical path. The approval is performed by a **different signed-in identity**, because a
second click in the presenter's own session proves nothing — a demo where one person creates
and approves in two minutes is the exact failure sophisticated buyers call out.

What goes on screen is the audit record:

```
Routed to Engineering + Quality · 09:16 · rule: AML gate · evidence: 3 boards, 27 checks
Approved by priya@… · 09:17 · "Qualified on Rev C, evidence QUAL-014"
```

Named identity, timestamp, the rule that fired, and a rationale bound to the decision. That
is the direct answer to *"who approved the decision your agent made three months ago"* — the
question the research says enterprises cannot answer and never demonstrate.

**Approval by replying to the email** uses the same connector in the other direction and is
the answer to *"what if procurement will not log in?"* — a Q&A answer, not the stage path,
because an IMAP round trip on stage is dead air.

**This works only if every part of it is real.** A different identity, a real send, a real
record. Staging any of it collapses credibility on the one beat that invites scrutiny.

---

## Shipping rule

**Nothing is labelled where we could have built it.** *Not assessed* is for work genuinely
outside scope — output-capacitor stability needs simulation and datasheet parameters we do
not hold. It is never a place to put something we chose to skip. A judge who finds a label
covering an unbuilt feature will ask about it first, and the honest answer costs the room.

This is why the footprint rule ships as a real land-pattern and pin-function comparison
rather than a size ceiling with the difference waved at.
