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

**0 · Standing state.** Three product lines with BOMs already in the system. Each
department's constraints registered as inputs *they* own — procurement's approved-vendor
list, manufacturing's placeable footprints, design's per-board requirements. Plus precedents.

**1 · The notice arrives.** An unstructured PCN or PDN, PDF or forwarded email. The
orchestrator parses it into `{MPN, notice type, effective date, LTB date, recommended
replacement}`. The model fills declared fields and never adds one; an unparseable notice
escalates rather than gets guessed at. *This replaces the planner.*

**2 · Exposure.** Match the MPN across every BOM. Deterministic, no model. This is also the
join SiliconExpert and Z2Data structurally cannot do, because they do not know your BOMs.

**3 · Candidates.** In order: the manufacturer's recommended replacement straight from the
notice, because that is what a human tries first; then model-proposed alternates sourced
through the distributor MCP, with precedents consulted. The model proposes only MPNs that
exist in distributor data.

**4 · The core loop.** For every candidate on every affected board, drop it into the slot and
run `evaluate(board)` — all ten rules on the whole board, not just the changed part. Three
candidates across three boards is nine whole-board evaluations. Unchanged code.

**5 · The matrix.** Candidates down, boards across, every cell carrying the role that owns
any failure. The reveal lives here: **the manufacturer's own recommended replacement passes
two boards and fails the third.** Industry names that failure mode itself — "assuming the
recommended replacement is drop-in" is a documented standard mistake.

**6 · Repair and escalation.** If nothing passes everywhere, `review` proposes beyond a
straight swap, `policy` validates each proposal, the engine re-checks the whole board after
every one, capped at three. When the engine cannot resolve it, or the only survivor violates
a role-owned constraint, escalate to the owner.

**7 · Three decisions, not one.** Per board: drop-in, or drop-in with a layout change, or no
candidate. Then the cost bucket for each.

**8 · Record.** Write the precedent — resolutions *and rejections* — and emit the change
record the mandatory checklist demands.

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

**What this does not settle:** the parts are synthetic. The physics and the rule behaviour
are real, and the setup values (θJA, rail voltages, draws) were chosen. Replacing them with
real MPNs whose datasheets a judge could look up is still open, and is now the highest
remaining risk in the demo.

---

## Still open

- Whether the PCB state is worth building at all, decided after the `pcbnew` spike.
- Where department constraints are *authored*. They are experienced in the matrix, which is
  all the demo needs; a management surface is a product need, not a demo need.
- Whether `replan` has any role left.
