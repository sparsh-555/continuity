# Continuity 2.0 — the flow, and what is settled

Design record for Scenario B. Written 6 Sep 2026. Read [SCENARIO-B.md](SCENARIO-B.md) for
why we took the topic and [EOL-RESEARCH.md](EOL-RESEARCH.md) for the sourced industry
figures every claim below leans on.

Two lists. **Finalised** is decided — build it without reopening. **Unproven** is where the
demo can still change shape, and each item names the test that settles it.

---

## Finalised

1. **Scenario B.** An EOL part, three product lines, 48 hours, three departments.
2. **The entry is an event, not a brief.** A PCN is parsed into declared fields and matched
   to BOMs on MPN. `parse_requirements`, `clarify`, `plan` and `replan` leave the graph —
   and the 36–105 s GLM planner call leaves with them.
3. **The engine is untouched.** Ten rules, whole-board re-check after every change, the
   `/bom/validate` path that never enters the planner.
4. **Fan-out across candidate × board.** This is the new machinery and the thesis: the same
   substitute passes on one board and fails on another, because compatibility is a property
   of the board, not the part.
5. **A policy layer runs parallel to `RULES`, not inside it.** Same Verdict/Evidence shape,
   tagged with the department that owns it. `RULES` keeps only physical law, which is
   derivable from datasheets; an AVL is organisational law, derivable from nothing but the
   company. Evaluated **alongside**, never as an upstream filter — filtering unapproved
   candidates before evaluation destroys the moment where design says yes and procurement
   says no.
6. **Escalation gains an owner.** Mechanism unchanged: `escalate` → `interrupt()` →
   `/resume`. What changes is that the question is addressed to procurement or production
   rather than to "the user".
7. **One screen with attribution.** No role-specific views and no fourth rail item. Three
   separate dashboards would rebuild the silo we claim to dissolve, and the value is only
   visible when the departments' verdicts sit side by side on the same candidate.
8. **`/datasheet` stays and gets featured.** It extracts one θJA fact for a given MPN and
   package. Evaluating a candidate substitute needs exactly that, which is how the thermal
   failure on line C becomes evidence rather than assertion.
9. **Email: the POST endpoint is the real path.** IMAP polling a throwaway mailbox is the
   stage flourish on top of it. Everything downstream of the parser is transport-agnostic,
   so a venue network failure costs the flourish, not the demo.
10. **Decisions classify into the industry's own buckets** — exact / qualified alternate /
    redesign candidate — which map onto the DoD cost metrics.
11. **No WorkBuddy integration** unless the organiser confirms criterion 4.2 means WorkBuddy
    specifically. See [WORKBUDDY.md](WORKBUDDY.md).

---

## The flow

Output changed on 6 Sep. The run used to end with three repaired boards; it now ends with
**three change requests awaiting approval**, because a released design cannot be altered
without sign-off. See [SCENARIO-B.md](SCENARIO-B.md) on ECR/ECO. The mechanics up to that
point are unchanged.

**0 · Standing state.** The dashboard lists **product lines** — the brief's own word, and
better than "projects", which sounds like an engineer's workspace rather than a thing the
company ships. Each was added by **uploading its KiCad project**, which yields the BOM the
rules need and the board the footprint view draws, from a file the engineer already has.
Each department's constraints are registered as inputs *they* own: procurement's
approved-vendor list, manufacturing's placeable footprints, design's per-board requirements.

**1 · The notice arrives.** A PCN, as an unstructured PDF or a forwarded email — either the
mailbox connector finds it or an engineer drops it in. Parsed into `{MPN, notice type,
effective date, LTB date, recommended replacement}`. The model fills declared fields and never
adds one; an unparseable notice escalates rather than gets guessed at. *This replaces the
planner.*

**2 · Exposure.** Match the MPN across every line. Deterministic, no model. *"AMS1117-3.3
appears in 3 of your 5 product lines."*

**This step is not our differentiator and we must stop saying it is.** SiliconExpert has a BOM
Manager, Z2Data's PCN Manager deduplicates notices and routes ownership, PCNshark does PDF
intake and BOM matching. Matching a notice to a bill of materials is established, commodity
functionality. What none of them does is the next step.

**3 · The manufacturer's own suggestion, first.** Because that is what a person does. Then
model-proposed alternates through the distributor MCP, with precedents consulted.

**4 · The core loop.** For every candidate on every affected line, drop it in and run
`evaluate(board)` — all ten rules on the whole board. Unchanged code.

**5 · The matrix, and the reveal.** Candidates down, lines across, every cell carrying the
role that owns any failure. The manufacturer's recommended replacement passes two lines and
fails the third. Industry names that failure mode itself: assuming a recommended replacement
is drop-in is a documented standard mistake.

**6 · The approval gate.** When the engine cannot decide, or the only survivor violates a
role-owned constraint, it stops and addresses the decision to its owner. *"TLV1117LV33DCYR
passes all three lines but is not on the approved-vendor list. This is procurement's
decision."* Not a question to whoever is at the keyboard. The answer resumes the run and is
recorded against the change.

**7 · A change request per line.** Affected part, reason, evidence, cost delta, approvals
required. Continuity assembled the packet; the board decides.

**8 · The boards, after approval.** And this is where the real parts pay off:

- **Sensor Node and Gateway** take ME6211 at $0.0597 — but that is **SOT-23-5 against the
  outgoing SOT-223**. The pads move, connections break, both boards need layout work.
- **Display Unit** takes TLV1117 at $0.1115 — **same SOT-223 footprint, a true drop-in.**

So the footprint view shows two boards with broken connections lit and one untouched, and it
**inverts the obvious answer**: the cheap part is not cheap once you count respinning two
boards, and the expensive one is free to adopt. That is a decision no parametric search
reaches, and it is why the KiCad view earns its place rather than decorating.

**9 · Record.** Precedents — resolutions *and* rejections — plus the audit trail the ECO
process requires.

### What survives from the current graph

| Current node | 2.0 |
|---|---|
| `parse_requirements`, `clarify`, `plan`, `replan` | Replaced by PCN parse + exposure match |
| `select` | Candidate enumeration for one slot |
| `validate` | **Unchanged**, fanned out across boards |
| `review`, `apply` | **Unchanged** |
| `escalate` | Unchanged mechanism, gains an owner |
| `finalize` | Per-board decisions |

Six of ten nodes survive untouched, and the four replaced are where the latency lived.

---

## The screen

The centre panel gains **three states, as a drill-down rather than new destinations**:

| State | Shows | Reached by |
|---|---|---|
| **Matrix** | Candidates × boards, cells owned by department | Default during and after evaluation |
| **Graph** | One board's reasoning, failure highlighted | Clicking a cell |
| **PCB** | One board's physical consequence | After a decision |

`ComponentGraph` is **not** replaced by a PCB view. The graph shows what the engine actually
reasons about — roles, rails, what feeds what — and the ten rules operate on exactly that
structure. A layout shows physical placement, which the engine touches only through
`footprint`. Swapping one for the other hides the thing that thinks and shows the thing that
does not, and it makes us look like a layout tool.

`ConflictPanel` is not replaced either — it is **scoped to one cell**. The moment the
recommended replacement fails on line C is a conflict, and it still needs its evidence shown.

---

## Memory

Keep the part graph. What changes is what a node means.

Today a precedent is *this conflict signature was repaired this way*. In 2.0 it is *this MPN
was replaced by that one, on this board, for this reason* — **and** *this candidate was
rejected on that board for thermal*. Rejections matter as much as resolutions: they are what
stops the orchestrator re-proposing a part already ruled out.

Memory also acquires a price. Per the DoD metrics, resolving an EOL with an **already
approved** part costs ~$1,281; a simple substitute qualified from scratch costs ~$15,656.
Memory is the difference between those two buckets on the next event. It is simultaneously
the audit history the industry checklist mandates.

---

## Build order

Written 6 Sep after an adversarial research pass. Ordered by *claim earned per day*, not by
dependency. The principle is **build the thing that makes the claim true rather than shrink
the claim** — several findings that looked like corrections are features the brief asks for.

| # | Build | Claim it earns |
|---|---|---|
| 1 | **θJA read from the datasheet**, with the quoted line and the copper-area condition. `/datasheet` already does this; it is not in the demo path. | Kills our weakest number. No competitor opens the PDF. |
| 2 | **Two bug fixes.** The reviewer prompt tells the model a larger linear regulator has the same junction temperature (wrong — different θJA). `policy` permits a slot at `repair_count == 3` against a three-repair cap. | Correctness, and we are currently misinforming the model. |
| 3 | **Multi-board fan-out and the matrix.** | The whole thesis: one substitute, opposite verdicts. |
| 4 | **Coverage semantics** — *checked and satisfied* / *not assessed* / *evidence missing*, instead of a bare pass. | Turns incomplete coverage from a weakness into the reason to trust us. Nobody else does it. |
| 5 | **Two approval gates.** Unqualified MPN routes to engineering and quality; qualified part with an unapproved source routes to procurement. AML and AVL are different lists. | Answers *"coordinate the cross-team response"* correctly rather than plausibly. |
| 6 | **A real footprint-compatibility rule** — land pattern and pin function, not a size ceiling. | *"Production confirms assembly compatibility"*, from the prompt. |
| 7 | **Operating profile as a first-class input** — load, ambient, duty cycle, per line. | The moat. It is *why* our answer differs per board and theirs cannot. |
| 8 | **Full PCN schema** — many parts, distinct nullable dates, per-part replacement mapping. | Real notices, not our five-field guess. |
| 9 | **KiCad ingestion** via `kicad-cli` BOM and netlist export. | Onboarding from a file engineers already have. |
| 10 | **KiCad before/after view** with DRC deltas. | The physical consequence of the decision. |

Items 1 to 5 are the demo. 6 to 10 are stretch, in that order. If 7 slips, the operating
profile is entered by hand and we say so.

## Unproven — each with the test that settles it

| | Item | Test |
|---|---|---|
| ✅ | ~~**The demo case exists.**~~ **Settled 6 Sep — see "The differential is real" below.** | `backend/tools/eol_differential.py` |
| 🔴 | **The deployed app crashes on the walkthrough**; local does not. The booth runs the public URL all day on the 13th. | Drive the walkthrough headless against the deployed app, capture console and network. Rule out the known rebuild window first — any push to `main` restarts both services for 3–6 minutes. |
| 🟡 | **KiCad footprint swap.** Replace a footprint headless and report which connections broke. Routing is explicitly out of scope. | A `pcbnew` spike, half a day, cleanly cancellable. Rendering in the browser is a second unknown. |
| 🟡 | **Does the Z.ai key work from mainland China?** `llm.py` warns keys do not cross regions and the default endpoint is international. | Ask, or test. Has a lead time if a `bigmodel.cn` account is needed — not something to discover on the 12th. |
| ⚪ | Criterion 4.2's referent | Pending with the organiser |

Run order: ~~the differential test~~, the deployment crash, then KiCad.

### The differential is real — and richer than designed

`backend/tools/eol_differential.py` drives `evaluate()` directly on three boards sharing one
linear regulator that is going EOL. No API, no auth, no planner. Result:

| Candidate | Line A · 5 V, 0.30 A | Line B · 5 V, 0.50 A | Line C · 12 V, 0.20 A |
|---|---|---|---|
| EOL part today | pass | pass | pass (warn: runs hot) |
| **Recommended replacement** (LDO, SOIC-8) | **pass** | **pass, warns at 119 °C** | **FAIL — 216 °C against a 125 °C limit** |
| **Second candidate** (buck) | **FAIL — needs 5.5 V min** | **FAIL — needs 5.5 V min** | **pass** |

Three findings, none of them staged:

1. **The per-board differential exists.** The manufacturer's recommended replacement passes
   two boards and fails the third on `thermal_dissipation`, with the engine deriving the
   power, the rise and the junction temperature itself. Verdict text is already
   demo-ready: *"(12 V − 3.3 V) × 200 mA = 1.74 W in SOIC-8 — 191 °C rise, 216 °C junction
   against a 125 °C limit."*
2. **The result is three-state, not binary.** Line B *clears* the limit at 119 °C and the
   engine still warns that it runs hot. Pass / marginal / fail is a better matrix than
   pass / fail, and it is the kind of nuance a hardware judge respects.
3. **No single part solves all three boards, and the reasons are different rules.** The buck
   fails A and B on `voltage_overlap` — it needs 5.5 V minimum and those rails are 5 V —
   while passing C. So the LDO and the buck fail on opposite boards. **The answer is
   necessarily per-board**, which is the argument for the matrix existing at all rather
   than a single verdict.

`availability` also fails the EOL part on all three boards from stock alone, so the
end-of-life condition already has a corresponding engine verdict.

### Settled 6 Sep — the parts are real now

Rebuilt on MPNs pulled from JLCPCB through `graph.sourcing`, the same path the product uses.
A judge can look every one of them up.

| candidate | A · 120 mA | B · 200 mA | C · 350 mA |
|---|---|---|---|
| **AMS1117-3.3** SOT-223, $0.2176 — *going EOL* | pass | pass | pass |
| **ME6211C33M5G-N** SOT-23-5, $0.0597 — *the cheap swap* | pass | **hot, 110 °C** | **FAIL — 174 °C vs 150 °C** |
| **TLV1117LV33DCYR** SOT-223, $0.1115 — *same package* | pass | pass | pass |

The engine's verdict, verbatim: *"(5 V − 3.3 V) × 350 mA = 0.59 W in SOT-23-5 — 149 °C rise,
174 °C junction against a 150 °C limit."*

The mechanism is the package. θJA is absent from every distributor row, so the engine uses
its own table: **SOT-223 at 62 °C/W against SOT-23-5 at 250 °C/W**. Four times the thermal
resistance in the cheaper part, which is invisible on a parametric search and is the entire
reason the swap fails. Uploading the datasheet through `/datasheet` replaces the table figure
with a quoted one, which is the stronger version of the beat.

**One design change fell out of the real specs.** The plan was to differentiate on input
voltage — a 12 V line C. ME6211 is rated to 6 V, so a 12 V board rejects it on
`voltage_overlap` before thermal is ever reached, which is correct but tells the wrong story.
All three lines now run at 5 V and differ in load current, which is also a more believable
product family.

**Blemish to fix or accept:** `voltage_overlap` warns on all nine cells — the distributor
publishes a maximum but no minimum, and these are LDOs whose real minimum is dropout above
3.3 V. Honest, and noisy on every row. A datasheet upload clears it.

---

## Still open

- Whether the PCB state is worth building at all, decided after the `pcbnew` spike.
- Where department constraints are *authored*. They are experienced in the matrix, which is
  all the demo needs; a management surface is a product need, not a demo need.
- Whether `replan` has any role left.
