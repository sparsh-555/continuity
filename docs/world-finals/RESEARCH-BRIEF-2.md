# Research brief, round two — verify the plan, not the idea

Copy everything below the line into a fresh session. Self-contained.

---

You are the second adversarial pass on a product about to be built for a competition demo
on **13 September 2026**. Round one found real problems and we acted on them. This round
verifies **the plan we are about to execute**, in the six days remaining.

**Do not write code. Do not redesign the architecture. Do not propose scope.** One person,
six days, a demo that must run live on a laptop.

## The product

**Continuity** validates printed-circuit-board bills of materials. Repo
`~/Documents/GitHub/continuity`. Python, LangGraph, React, Postgres.

> A deterministic engine owns *what is electrically broken*. A language model owns *which
> repair to try*. The engine re-checks the whole board after every change. No compatibility
> verdict is produced by a model.

Read: `backend/continuity/engine/rules.py` (the ten rules), `reviewer.py` (`ACTIONS`,
`CONSTRAINT_FIELDS`, and the system prompt), `engine/policy.py` (the guard layer),
`graph/build.py` and `graph/nodes.py` (the state machine), `api/app.py` (`/bom/validate`,
`/design`, `/resume`, `/datasheet`), `parts/normalize.py`, `engine/packages.py` (the θJA
table), `backend/tools/eol_differential.py` (the demo case — run it), and
`docs/world-finals/*.md`.

## What round one established, so you do not repeat it

Accepted and already acted on:

- Our θJA figures (62 for SOT-223, 250 for SOT-23-5) are **not defensible**. The AMS
  datasheet says 95 °C/W with strong copper-area dependence. ME6211's 250 could not be
  substantiated at all, and its 150 °C is **TOPR**, not a junction limit.
  *(Later correction: the AMS datasheet was subsequently opened and parsed. It says
  **90 °C/W**, footnoted "46 °C/W to >90 °C/W", with a copper-area table. See
  [PARTS.md](PARTS.md).)*
- The fixture mixes a **JSMSEMI** listing with **TI** specifications for TLV1117LV. TI's part
  is 6 V absolute maximum, not the 12 V in our fixture.
- The `footprint` rule checks a **package-size ceiling**, not land-pattern compatibility.
- **Competitors already do PCN-to-BOM matching and cross-team routing** — SiliconExpert,
  Z2Data, PCNshark, Accuris. We have stopped claiming otherwise.
- A new manufacturer part is **not** a procurement-only approval. AML and AVL differ.
- The DoD cost figures are defence obsolescence resolutions and the 2025 source contradicts
  itself between slides. Dropped from the pitch.
- `/bom/validate` **bypasses** the repair and interrupt graph.
- Two bugs: the reviewer prompt asserts a larger linear regulator has the same junction
  temperature; `policy` permits a slot at `repair_count == 3` against a three-repair cap.

## The corrected position

> Everyone in this market can tell you a part is affected. Nobody can tell you whether the
> replacement works on **your** board, because their answer is one row per part and the real
> answer differs per board.

The proof is one substitute passing on one line and failing on another — which a parametric
cross-reference cannot produce **by construction**, since its data model has no board in it.

## The build order to critique

| # | Build |
|---|---|
| 1 | θJA read from the datasheet, with quoted line and copper-area condition |
| 2 | The two bug fixes above |
| 3 | Multi-board fan-out and the candidate × board matrix |
| 4 | Coverage semantics: *checked and satisfied* / *not assessed* / *evidence missing* |
| 5 | Two approval gates — engineering+quality for an unqualified MPN, procurement for an unapproved source |
| 6 | A real footprint-compatibility rule: land pattern and pin function |
| 7 | Operating profile as a first-class input (load, ambient, duty cycle, per line) |
| 8 | Full PCN schema |
| 9 | KiCad ingestion via `kicad-cli` |
| 10 | KiCad before/after view with DRC deltas |

1–5 are the demo; 6–10 are stretch. **Tell us what is undercosted, what is out of order, and
what is not worth building at all.**

## What to verify — ranked

### 1 · Settle the thermal facts. This gates everything.
- What θJA does the **AMS1117-3.3** datasheet state, under exactly what conditions? Which
  manufacturer's datasheet is authoritative for the part JLCPCB actually ships?
- Does the **ME6211C33M5G-N** datasheet state a θJA at all? If not, what should we do — a
  JEDEC standard figure for SOT-23-5, a competitor's figure for the same package, or refuse
  to compute and report *evidence missing*?
- Is the **300 mW absolute-maximum power** for SOT23 real, and does it mean our 200 mA line
  (340 mW) fails on a limit we are not checking? If so our demo has two failures, not one.
- How should a θJA that varies from 46 to 90+ °C/W with copper area be presented honestly
  while still supporting a decisive on-stage claim?
- We need a **third part**: a real 3.3 V LDO, in stock at JLCPCB, with a **published θJA**,
  credible as a replacement for AMS1117-3.3. Name candidates with datasheet links.
- Is there a **real, citable EOL or PCN** for any common 3.3 V LDO we could use instead of a
  labelled hypothetical?

### 2 · Coverage semantics — is this real, and is it ours?
We intend to replace a bare "pass" with *checked and satisfied* / *not assessed* / *evidence
missing*.
- Is there prior art? How do safety-critical or aerospace analyses express **coverage** of a
  review, as distinct from its result?
- Is there standard vocabulary we should adopt rather than invent?
- Does any competitor already report analysis coverage this way?
- What is the failure mode of this idea — where does it make us look weaker rather than more
  trustworthy?

### 3 · Footprint compatibility, for real
- What does comparing two land patterns actually require? Is **IPC-7351** naming sufficient to
  decide compatibility, or is geometry comparison unavoidable?
- How is **pin function** compatibility determined programmatically? ME6211 has a chip-enable
  pin that AMS1117 does not. Is there a data source, or is this irreducibly manual?
- What is the smallest honest version of this rule that is still worth having?

### 4 · Output-capacitor stability
Round one called this the first thing a hardware engineer would attack on an LDO
substitution.
- What exactly makes an LDO substitution unstable — minimum capacitance, ESR window, ceramic
  versus tantalum?
- Is this checkable from datasheet parameters, or does it need simulation?
- Could a defensible rule be built in **under a day**? If not, what is the correct thing to
  say when asked?

### 5 · The two approval gates
- Verify the AML/AVL split and the routing. What does a real *"technically qualified, source
  not approved"* case look like?
- Can one finding legitimately have **several owners**? Round one said our one-department-per-
  cell tagging is an oversimplification. How do real change boards handle that?

### 6 · Try hard to falsify our positioning
This is the pitch, so attack it.
- Does **any** PCN, BOM-risk or component-intelligence tool compute an **application-specific**
  thermal or electrical result for a candidate substitute? Check Accuris BOM AI, Z2Data,
  SiliconExpert, Altium/Octopart, Cofactr, Luminovo, and anything else you find.
- Does any EDA tool do this **inside** an obsolescence workflow rather than at design time?
- If our claim is false, say so plainly and tell us what is actually left.

### 7 · Integration cost we may have underestimated
- How much work is routing `/bom/validate` through the graph so the fan-out gets the repair
  loop and interrupts? Read the code and estimate honestly.
- Does the LangGraph `interrupt()` payload extend to carry an owning role, or does that ripple
  into the frontend and the store?

### 8 · The operating profile
- What is the minimum credible field set — load current, ambient, airflow, duty cycle,
  lifetime, supply tolerance?
- Do engineers have these written down anywhere, or is asking for them a genuine adoption
  barrier?
- Is there a standard or common template?

### 9 · One last adversarial pass
Assume the panel includes a hardware engineer and someone who sells component-intelligence
software.
- What are the three questions we still cannot answer?
- Where is the new pitch weakest?
- What is the most embarrassing thing that could happen live on stage?

## How to answer

- Cite sources. Separate verified from inferred.
- Show disagreement between sources; never average it.
- Say plainly when something is not findable.
- Lead with what changes a decision. If nothing in a section does, say so and move on.
