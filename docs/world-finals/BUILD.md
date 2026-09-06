# Continuity 2.0 — build

Ordered work. Each item names the files it touches, what *done* means, and its own acceptance
test, so a test cannot drift away from the item it proves.

[SPEC.md](SPEC.md) is the contract. This is the sequence.

## The rule that governs all of it

**Nothing ships behind a label we could have built.** *Not assessed* is for work genuinely
outside scope. It is never cover for something skipped. A judge who finds a label hiding an
unbuilt feature asks about it first, and "we ran out of time" costs the room.

## Order, and why

Three dependencies drive it. The **operating profile** determines what every θJA claim and
every matrix cell means. **Coverage semantics** determine what green means, so nothing may
aggregate cells before they exist. **Authorisation** has to be real before an approval gate is
anything but a label. Getting any of them wrong later is rework of everything above.

## How to work through it

**Items 1 to 9 are surgical** — small changes in code that has been read closely. They need no
planning ceremony and no documentation research. Do them directly, and keep the suite green
after each.

**Items 11 to 13 rewrite how the graph carries state and who may answer a question.** Check
LangGraph's documentation for the pinned version before planning them — `interrupt`, `resume`
and state semantics move between releases, and the repo pins `langgraph 1.2.11`. This is also
the natural point to hand a bounded spec to a subagent, since by then items 1 to 9 have green
acceptance tests to build against rather than a description.

**Item 18 is unexplored** and should be researched before it is planned at all.

---

# Phase 1 · Foundations

## 1 · Real fixture, real parts, and the fields it needs — **DONE**

Suite 721 → **735 passed, 5 skipped**. Fourteen new tests, none existing moved. Five model
fields shipped rather than four: `Rail.i_load_basis` had to be separate from `Rail.basis`, or R1
would cite a power budget as the source of a rail's *voltage*. `rail_draw` had five call sites,
not three — `energy_budget` and `situation.py` were missed by the original survey.

**No cell in the demo rests on the package table.** All four manufacturers publish a θJA, so
every number on screen cites a datasheet. LD1117S33 briefly looked unpublished because Rev 26 of
ST's datasheet omits the SOT-223 column that Rev 38 carries — a correction worth remembering,
because it is a trap for item 5's extractor in the opposite direction from the usual one.

Everything downstream quotes these numbers. Verifying them is what showed that four of the
figures SPEC originally carried had no source — see [PARTS.md](PARTS.md), which is now the
record. This item makes the code match it.

**Files** `engine/models.py`, `engine/draw.py`, `engine/rules.py`,
`backend/tools/eol_differential.py`. The implementation brief is
[tasks/ITEM-1.md](tasks/ITEM-1.md) — hand that over whole.

**The model additions come first**, because the fixture cannot state an honest θJA or an
honest dissipation without them. All are additive: design mode leaves them unset and behaves
exactly as it does today. A fifth, `Rail.i_load_basis`, is described in the summary above.

- **`PartSpec.theta_ja_mounting`** — the condition the value was measured under. Without it,
  160 °C/W at a minimum-size pad and 60 °C/W at 1000 mm² of copper look like the same kind of
  number, and comparing them is the first thing a hardware engineer would catch.
- **`PartSpec.t_j_max`** — the junction limit, separately from the ambient grade. `temp_max`
  does both jobs today, and for NCP1117 they differ: the distributor states `0~125 ℃ @(Ta)`
  while onsemi's datasheet states a 150 °C maximum die junction temperature. Failing that part
  against 125 would be failing it against a number that is not a junction limit.
- **`Requirements.mounting`** — the board's copper area, so AMS1117's own Table 1 can be
  applied to the board it is actually sitting on, and so the thermal verdict can cite it.
- **`Rail.i_load`** — the product line's declared rail load. `draw.rail_draw()` returns it when
  set and falls back to summing parts when it is not. That one function is the single change
  point: `thermal_dissipation` (`rules.py:785`) and `current_budget` (`rules.py:600`) both
  reach the draw through it, so they stay consistent for free.

**Done when** the four regulators and the output capacitor carry the listings recorded in
PARTS.md — TI's `C15578` for TLV1117LV33DCYR, never JSMSEMI's `C48937499` — every θJA carries
its quoted line and its mounting condition, `mpn="LOAD"` is replaced by the real module each
line carries, and each line states its own ambient, copper area and rail load with a basis.

**Test** the script reproduces the SPEC matrix: the incumbent passes all three lines at both
ends of its 46-to->90 spread; TLV1117LV33 fails C on voltage against a 5.5 V ceiling;
NCP1117ST33 fails B on thermal at 159 °C against onsemi's 150 °C limit and clears C with 11 °C
of margin; LD1117S33 clears all three and lands on B with 1.5 °C to spare.

## 2 · Operating profile

**Files** `engine/models.py`, `engine/rules.py`, `api/store.py`

Item 1 adds the fields the engine needs. This item makes them a persisted property of a product
line rather than something a fixture sets.

**Done when** `ambient_max_c` belongs to the profile and `temp_range` means component grade
only — one object conflates them today — and ambient, copper and load reach a run from the
stored profile. Every thermal verdict cites the ambient it used and where that number came from.

**Test** the same board at 25 °C and 70 °C returns different verdicts, each naming its ambient.
A board with no profile returns *evidence missing* for thermal rather than assuming 25 °C.

## 3 · Coverage semantics

**Files** `engine/models.py` (`Verdict` status), `engine/rules.py`, `api/events.py`, frontend

**Done when** every rule returns one of **satisfied / failed / not applicable / not assessed /
evidence missing**, and a cell is green only when every applicable check is satisfied.

**Test** a board reports `interface_role_match` as *not applicable* rather than passing; a green
cell shows its count of unassessed checks; and a part with no stated θJA whose package the table
*does* know reports *evidence missing* rather than falling back silently. The demo's four
regulators no longer supply that case — all four publish a figure — so build the case from a
part that genuinely publishes none.

## 4 · Three bug fixes

**Files** `reviewer.py`, `engine/policy.py`, `graph/nodes.py`, `graph/sourcing.py`

- The reviewer's system prompt claims a larger linear regulator has the same junction
  temperature. Same power, different θJA, different temperature — we are misinforming the model.
- `policy` permits a slot at `repair_count == 3` against a three-repair cap.
- **Repair constraints do not accumulate.** `nodes.py` stores only the latest repair's
  constraint, so repair two forgets what repair one demanded and the search oscillates between
  two parts failing opposite ends of a range. Scenario B is temperature ranges across three
  boards, so this will bite. Accumulate on `swap` only, where the kind of part is unchanged.

**Test** the cap refuses a fourth repair; the misleading sentence is gone; a two-sided
constraint (`rated_from` then `rated_to`) reaches a search carrying both.

---

# Phase 2 · Rules

## 5 · θJA from the datasheet

**Files** `parts/datasheet.py`, `parts/normalize.py`, `engine/rules.py`

**Done when** θJA comes from the PDF with its quoted line **and its mounting condition**, the
extraction binds the value to the correct table column rather than only checking a quote
appears somewhere, and the cache is keyed by document identity rather than by MPN — today a
cached result can shadow a newly uploaded datasheet, which is a live demo hazard.

**And when the package-table fallback stops answering substitution questions.**
`packages.theta_ja("SOT-223")` returns **62.0**, against a published 62.9 from TI on a JEDEC
board and **160** from onsemi at a minimum pad — for the same package. A single figure spanning
a 2.6× spread is not an approximation, it is the optimistic end presented as a default, and it
is what would let LD1117S33 report a temperature ST never published. The table can stay for
design mode, where an approximate number beats refusing to answer a brief; it must not stand in
for a datasheet when the question is *"is this substitute safe on this board"*. That is the
difference `evidence missing` exists to express.

**Test** all four datasheets yield the right θJA with the right quote, bound to the right
column — the ST LD1117 document is the hard case in **both** directions: Rev 38's Table 2 prints
110 / 55 / 100 / 50 across SOT-223 / SO-8 / DPAK / TO-220, so taking 50 for a SOT-223 part fails
this test, and so does concluding nothing was published when handed Rev 26, which omits the
column entirely. The extraction must record the document revision alongside the value. Uploading
a different datasheet for the same MPN returns the new value, not the cached one.

## 6 · `power_dissipation_max`

**Files** `engine/models.py`, `engine/rules.py`, `parts/normalize.py`

**Done when** `PartSpec` carries a stated maximum dissipation and the rule fails when computed
power exceeds it. Separate from `thermal_dissipation` — a part can be inside its junction limit
and over its power rating.

**Test** a part rated 300 mW dissipating 340 mW fails; a part with no stated maximum reports
*evidence missing*.

## 7 · `footprint_compatibility`

**Files** `engine/models.py` (a baseline concept), `engine/rules.py`, footprint data

**Done when** the rule compares land pattern and pin function against **the part being
replaced**, which no rule can express today. `footprint` keeps its own advisory size job.

**Test** SOT-223 to SOT-223 reports compatible; SOT-223 to SOT-23-5 reports incompatible; a
candidate with an extra pin function reports the unmapped pin rather than passing.

## 8 · `capacitor_requirements`

**Files** `engine/models.py`, `engine/rules.py`, `parts/normalize.py`

**Done when** the rule compares the candidate's stated output-capacitor requirement — minimum
effective capacitance, ESR window, permitted dielectric — against the capacitor actually on the
board. It reports **failed** on an explicit conflict, **evidence missing** where the
requirement is unpublished, and never claims stability.

**Test** a board carrying 0.1 µF on the output fails TLV1117LV33, which states *"effective
output capacitance… must be greater than 0.5 µF"*; the demo boards' 22 µF X5R satisfies it,
because TI also names X5R and X7R explicitly. AMS1117's *"22 µF solid tantalum"* against that
same ceramic is a **dielectric the datasheet does not address**, so it reports evidence missing
rather than either a pass or a fail — the datasheet recommends a type, it does not rule one out.

## 9 · Repair vocabulary

**Files** `reviewer.py`

**Done when** `CONSTRAINT_FIELDS` can express what the new rules check: `theta_ja_max` so a
thermal repair can demand a better-cooling package class rather than naming one exact package,
`p_dis_min`, and `approved_only`.

**Test** a repair demanding `theta_ja_max` reaches the search and narrows the shortlist.

---

# Phase 3 · The enterprise flow

## 10 · Product lines

**Files** `api/projects.py`, `api/store.py`, frontend routes

**Done when** a product line holds a BOM, an operating profile and a revision, and exposure
matching returns the affected lines from an MPN.

**Test** an MPN present in three of five lines returns exactly those three.

## 11 · Authorisation and roles

**Before** the gates, because a gate without this is a label.

**Files** `api/store.py`, `api/auth.py`, `api/app.py`, `graph/state.py`

**Done when** a run carries the roles permitted to answer each open decision; `/resume` checks
the answering user against that rather than against thread ownership — it calls
`thread_for_user` today, so a procurement account cannot answer an engineer's run at all. And
waivers are scoped to candidate and revision instead of `(rule, slot)`.

**Test** a procurement user resumes an engineer's run at a procurement gate and is refused at
an engineering gate; an approval granted for one candidate does not carry to the next.

## 12 · Fan-out and the matrix

**Files** new orchestration, `api/app.py`, frontend

**Done when** one candidate is evaluated against N boards, and results keep their board and
candidate identity — a repair changes the candidate, so a result must not silently remain in
the original candidate's row.

**Each cell is one `evaluate(board)` with the candidate substituted.** It does not route
through the graph: no repair loop, no interrupt, no per-cell checkpoint. The graph's repair
loop sits upstream and generates further candidates when the manufacturer's recommendation
fails — repair produces rows, the fan-out fills them. Routing nine cells through the graph
would inherit machinery none of them uses, at a cost research put at several engineer-days.

**Test** the demo case produces the full matrix, every cell attributable to a board, a candidate
and an owning department.

## 13 · AML, AVL and the two gates

**Files** policy layer, `graph/nodes.py`, `api/app.py`, `api/store.py`

**Done when** AML and AVL are separate lists; an unqualified MPN routes to engineering and
quality; a qualified part from an unapproved source routes to procurement; and an approval
records identity, timestamp, the rule that fired and a rationale.

**Test** the gate fires on an unqualified part with **no** electrical failure, since approval
cannot depend on failure.

## 14 · Mailbox connector, both directions

**Files** new module, `api/app.py`

**Done when** an unread message with a PDF attachment starts a run, and a gate sends a real
approval request naming the decision, the evidence and the requester. A POST endpoint accepts
the same PDF so the demo never depends on mail delivery.

**Test** a PCN sent to the mailbox starts a run within one poll; a gate produces a delivered
email; the POST path produces an identical run.

## 15 · The change request

**Files** new module, store, frontend

**Done when** each affected line yields a persisted request carrying baseline and revision, the
notice that triggered it, the proposal with alternatives rejected and why, the evidence, **what
was not assessed**, cost split into recurring and one-time, and the approvals required.

**Test** the three demo lines produce three requests, each naming its unassessed checks.

---

# Phase 4 · Demo assets

## 15a · Precedents

Missing from every document until now, and it carries a business argument: per the DoD
metrics, resolving an EOL with an **already approved** part costs about $1,281 against roughly
$15,656 for a substitute qualified from scratch. Memory is the difference between those two
buckets on the next notice.

**Files** `api/memory.py`, `api/store.py`, `reviewer.py`

**Done when** a resolution **and a rejection** are recorded against a conflict signature,
scoped to the board they applied to, and reach the reviewer on a later run. Rejections matter
as much as resolutions — they stop a candidate already ruled out being proposed again.

**Test** a candidate rejected on line C for thermal is not re-proposed for line C on a second
notice; a part approved on line A surfaces as precedent when line B hits the same signature.

---

## 16 · Seeded world

**The demo does not exist without this**, and it is not presentation work.

**Files** a seed script, fixtures

**Done when** five product lines exist with BOMs, operating profiles and revisions; three carry
AMS1117-3.3; AML and AVL records exist with LD1117S33 deliberately absent from the AML; and two
accounts exist — an engineer and an approver with a procurement or quality role.

**Test** the seed runs from an empty database and the demo plays end to end afterwards.

## 17 · The notice

**Done when** a PCN document exists that parses, **labelled as a constructed example** rather
than passed off as a real manufacturer notice. It recommends NCP1117ST33 — plausible, since
onsemi is a genuine AMS1117 second source — and the recommendation fails the gateway.

**Test** the parser extracts every declared field from it, and reports the fields it cannot find
rather than inventing them.

## 18 · KiCad

**Files** new module

**Done when** a project bundle yields a BOM through `kicad-cli` and the board renders with the
footprint consequence of the chosen substitute.

**Note** pin the KiCad version. `pcbnew`'s SWIG bindings run headless but are deprecated from
KiCad 9 with removal planned for 11; the replacement IPC API needs a running GUI until 11.
`kicad-cli` SVG export is the dependable path for before-and-after evidence.

**Test** a known project yields the expected BOM rows and a rendered board.

---

# Phase 5 · Presentation

Not written yet, and not covered anywhere in these documents.

- **The pitch.** The Singapore speech is for the old story and does not survive the reframe.
- **Slides**, same.
- **The fallback recording.** The organiser advised one last time and it was never cut.
- **Q&A preparation** against the questions the research says we still cannot answer: *"show me
  why the green cell is justified on this actual board"*, *"what exactly did this person
  approve, and does it survive a revision"*, *"why can't my component-intelligence tool plus my
  EDA suite do this"*.

---

## Still unfixed, deliberately out of scope

- The `/projects` retry loop has no backoff — one 401 became fifteen requests.
- Nothing configures logging, so application warnings reach production logs only through
  Python's last-resort handler, unformatted.
- Output-capacitor **stability** remains unassessed. Item 8 checks explicit violations of a
  stated requirement; proving stability needs simulation. Say so plainly when asked.

## Open with the organiser

Submission deadline for the finals work, pitch and Q&A length, what criterion 4.2 means by
"product features", venue network reachability, and booth requirements. See
[README.md](README.md).
