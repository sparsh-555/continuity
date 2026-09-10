# Continuity 2.0 — build

Ordered work. Each item names the files it touches, what *done* means, and its own acceptance
test, so a test cannot drift away from the item it proves.

[SPEC.md](SPEC.md) is the contract. This is the sequence.

## The rule that governs all of it

**Nothing ships behind a label we could have built.** *Not assessed* is for work genuinely
outside scope. It is never cover for something skipped. A judge who finds a label hiding an
unbuilt feature asks about it first, and "we ran out of time" costs the room.

## The second rule, learned the hard way on 9 Sep

**Continuity's entire pitch is that it checks parts. A surface that says it could not check
one destroys that claim in seconds, and no amount of correctness underneath buys it back.**

What happened: a distributor lookup failed on a product line page, one part rendered grey
beside two green ones, and the fix shipped was a sentence on the page reading *"Not checked,
because no distributor listing was found."* Beside it, another paragraph explained which
rules had no published figure and which were outside what the engine answers. Every word of
it was true. All of it was a product whose one claim is that it checks parts, opening with
the parts it did not check.

Three things follow, and they are not the same thing said three ways.

**A failure to check is a bug to fix, not a state to render.** The distributor is a network
call and a venue's network is not ours, so a shipping product line must be checkable without
one. It is: `dossier.part_from_facts` builds a part from the readings this company recorded,
which are better evidence than a listing rather than a degraded substitute. Reach for the fix
before reaching for the caption.

**Coverage honesty belongs in the change request, not on a browsing surface.** The five labels
are real and they matter, and the place they matter is the ECR packet, where somebody is
deciding whether to sign. That reader is interrogating one decision and wants to know exactly
what was and was not established. A person looking at a product line for five seconds is not
that reader, and telling them what we could not do answers a question nobody asked.

**Limitations answer questions. They do not open pitches.** This is a standing instruction
from Sparsh, given more than once, and it was broken by putting a disclaimer above the fold on
the main demo page. The caption there also read *"Not a netlist — nothing here has read a
schematic"*, which teaches a room to doubt a picture before they have looked at it. Say what
the thing is. The limitation is available the moment anyone asks, and answering well then is
worth more than volunteering it badly first.

## Order, and why

Three dependencies drive it. The **operating profile** determines what every θJA claim and
every matrix cell means. **Coverage semantics** determine what green means, so nothing may
aggregate cells before they exist. **Authorisation** has to be real before an approval gate is
anything but a label. Getting any of them wrong later is rework of everything above.

## How to work through it

**Items 1 to 9 are surgical** — small changes in code that has been read closely. They need no
planning ceremony and no documentation research. Do them directly, and keep the suite green
after each.

## Which Codex profile to hand a task to

Set up 7 Sep after item 3a cost 221k tokens transcribing a mapping table that was already
decided. Profiles live at `~/.codex/<name>.config.toml` and are selected with
`codex exec -p <name>`.

| Profile | Model | Price per 1M in/out | For |
|---|---|---|---|
| `luna` | gpt-5.6-luna | $1 / $6 | A decided spec transcribed into code — renames, migrations against a given table, test-expectation updates, fixture data |
| `terra` | gpt-5.6-terra | $2.50 / $15 | A bounded change needing judgment inside the boundary — a diagnosed bug with no prescribed patch |
| `sol` | gpt-5.6-sol | $5 / $30 | Architecture or a refactor whose shape is not settled. Nothing delegated so far has qualified |

**Our split makes almost everything Luna work.** The design, the datasheet verification, the
classification calls and the review are done before a brief is written, so what goes over is
transcription with a do-not list. Item 4 ran on Luna at 157k tokens and found a merge site the
brief had missed. If the brief already says what to do, Sol is the wrong answer at five times
the price.

`service_tier = "priority"` is still set in the base config and layers under every profile. It
buys faster processing that a task launched into tmux and left alone does not consume.

---

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

## 2 · The ambient is an input, not a default

**Files** `engine/models.py`, `engine/rules.py`, `planner/plan.py`, `api/bom.py`. The
implementation brief is [tasks/ITEM-2.md](tasks/ITEM-2.md) — hand that over whole.

**Split from what this item first said.** It also called for the profile to be *persisted on a
product line*, and product lines do not exist until item 10 — `Requirements` is not stored at
all today, only run summaries are. That half has moved into item 10, where it can actually be
built. What remains here is the engine-side half, which is the part everything else depends on.

**And it is not what the original acceptance test said.** A board with no stated ambient must
**not** refuse the thermal check. Most briefs never state one, so refusing would turn thermal
into *unchecked* on nearly every board Continuity designs — a large regression dressed up as
rigour. Assuming a bench ambient is fine; assuming it *silently* is the defect. `ambient_c`
keeps its default and gains a source, exactly as `ASSUMED_EFFICIENCY` and the θJA package table
already do. What that assumption earns as a coverage label is item 3's decision, not this one's.

**Done when** `ambient_c` carries where it came from, both prompts omit the field rather than
emitting 25 unasked, `temp_range`'s docstring says it is a component grade — not the board's
ambient and not a junction limit, all three having been confused here before — and every
thermal verdict names the ambient it used and cites its source.

**Test** the same board at 25 °C and 70 °C returns different verdicts, each naming its own
ambient; an assumed ambient is sourced to the assumption and a stated one is not; and a board
that passes at 25 °C fails at 70 °C, so the ambient is provably an operand.

## 3 · Coverage semantics

**Split in two.** The engine vocabulary and the screen are separate jobs with separate risk:
`warn` appears at 22 sites in `rules.py` and each has to be classified as *checked and holds
narrowly* or *could not check* — judgment, not a rename — while the wire and the frontend are
mechanical once the labels settle. Doing both at once means a broken UI hiding a
misclassification.

- **3a · the engine** — `engine/models.py`, `engine/rules.py`, `graph/nodes.py`, `api/bom.py`.
  Brief: [tasks/ITEM-3A.md](tasks/ITEM-3A.md), which carries the site-by-site mapping decided
  in advance so it is transcribed rather than re-derived.
- **3b · the wire and the screen** — `api/events.py`, `frontend/src/app/lib/types.ts` and the
  components reading `'pass' | 'warn' | 'fail'`.

**One rule changes what it decides**, and only one: a chip-select shortfall — *"3 SPI
peripherals need a chip select each, but only 1 GPIO remains"* — was a `warn` because the old
vocabulary had nowhere to put a checked constraint that does not hold. It is a `failed`. That
it was hiding there is the clearest argument for the split.

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

## 6 · `power_dissipation_max` — **not built, and why**

Checked before building, and the quantity it tests is not stated by anything we source.

Every distributor field mentioning power is a different measurement: `Output Power(Max)` is RF
transmit power in dBm, `Current Rating-Power` is a connector's ampacity, and `Power - Max` on a
PoE controller is *deliverable output*. Reading that last one as a dissipation ceiling is the
same category error as reading an ambient rating as a junction limit, which item 1 exists to
have fixed.

The datasheets close it. AMS1117 and NCP1117 both say **"Internally Limited"**, TLV1117LV says
**"See Thermal Information"**, and LD1117 gives 12 W against 0.7 W on our hottest board. For a
linear regulator the dissipation limit *is* the thermal one, and `thermal_dissipation` already
computes it.

So the rule would report *evidence missing* on every cell of the demo and nearly every
regulator in design mode — a label covering a check with no subject, which is what the rule
governing this file forbids.

The case that motivated it is real and its subject is **passives**: a 0603 resistor's 100 mW
rating is a genuine stated spec, and a board full of them wants this check. Continuity's boards
are ICs and a capacitor. Revisit when a board has resistors on it.

<details><summary>The original item</summary>

## 6 · `power_dissipation_max`

**Files** `engine/models.py`, `engine/rules.py`, `parts/normalize.py`

**Done when** `PartSpec` carries a stated maximum dissipation and the rule fails when computed
power exceeds it. Separate from `thermal_dissipation` — a part can be inside its junction limit
and over its power rating.

**Test** a part rated 300 mW dissipating 340 mW fails; a part with no stated maximum reports
*evidence missing*.

</details>

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

## 9 · Repair vocabulary — **done, and narrowed**

`theta_ja_max` shipped. `p_dis_min` and `approved_only` did not, because neither has a
consumer: item 6 was not built, and the AML/AVL policy layer arrives at item 13. A constraint
key the model may emit and nothing reads is worse than no key — it is accepted, ignored, and
looks like it worked, which is exactly how `vout` sat in the vocabulary being silently dropped.

**Done when** a thermal repair asks for a ceiling rather than a package. `theta_ja_max` is in
`CONSTRAINT_FIELDS`, accumulates across repairs because the board still has to shed the heat
after a topology change, and is filtered locally in `sourcing._survives` against the package
table — θJA is not a distributor parameter and never will be. A package the table does not
know is kept, because "cannot tell" must not become "no".

The prompt teaches the arithmetic, `(limit − ambient) / watts`, since the evidence already
carries all three, and warns that a replacement must fit the land pattern it inherits now that
item 7 refuses one that does not.

---

# Phase 3 · The enterprise flow

## 10a · A project becomes a product line — **DONE**

**Files** `api/schema.sql`, `api/store.py`, `api/projects.py` → `api/lines.py`, `api/app.py`,
`routes/projects.tsx` → `routes/lines.tsx`, and every user-facing string.

The rename carried all the way through, with no `/projects` alias: a parallel concept kept
alive so the old thing still works is the drift this project keeps paying for. The migration
runs **before** the `CREATE TABLE` statements — afterwards, an old deployment would create an
empty `product_lines` and then fail the rename on every boot — and it was verified against a
clone of the real database three times, and against a fresh one, which is how the primary key
index still being called `projects_pkey` was found. **Written, not deployed.**

## 10b · A line holds a BOM, a profile and a revision — **DONE**

**Files** `api/schema.sql`, `api/store.py`, `api/lines.py`, new `api/exposure.py`, new
`continuity/profile.py`, frontend line detail. Brief: `tasks/ITEM-10B.md`.

**Done when** a product line holds a BOM, an operating profile and a revision, and exposure
matching returns the affected lines from an MPN.

The BOM is a **table** and the profile is a **jsonb column**, and they go opposite ways for one
reason: exposure matching asks "which rows across every line I own name this MPN", which is an
index probe against `line_parts(user_id, mpn)` and a scan of every stored BOM against jsonb.
The profile is read whole and never filtered on, so typed columns would buy nothing and cost a
migration per new condition.

**Also the half split out of item 2**: the operating profile becomes a *persisted* property of
the line — ambient, copper area and rail load stored against a revision and reaching a run from
there rather than from a fixture. `Requirements` is persisted nowhere today; only run summaries
are, so this is new storage rather than a change to existing storage.

**Test** an MPN present in three of five lines returns exactly those three; and a run against a
stored line uses that line's ambient, copper and load without any of the three being passed in.

Both verified against a running server rather than only in the suite. Exposure returns exactly
three of five lines, excluding one whose only row is `populated = false` and one with no BOM. A
live design run on the gateway emitted *"This product line runs at 45 °C — gateway operating
profile Rev C"* and then computed its junction temperature from that ambient. The **rail** half
of a profile is deliberately not applied to a design run — see DEFERRED.

## 11 · Authorisation and roles

**Before** the gates, because a gate without this is a label. Split in two: 11a moves ownership
to the company, 11b decides who may answer a given question.

### 11a · A product line belongs to a company — **DONE**

**Files** `api/schema.sql`, `api/store.py`, `api/auth.py`, `api/app.py`. Brief: `tasks/ITEM-11A.md`.

**Done when** an organisation owns lines, threads, findings and BOM rows; `users.roles` holds a
set from `engineering | procurement | quality`; and every existing account is an organisation of
one, so nothing they own changes hands.

Ownership had fifteen `WHERE user_id = %s` clauses, each saying *you may see what you personally
created*. Scenario B is three departments looking at one run, so the second of them gets a 404 —
and that 404 is `thread_for_user` working exactly as designed, which is why the concept has to
move rather than gain a sharing flag beside it. `user_id` stays on every table and becomes what
it honestly always was: who created this.

**Test** two organisations are invisible to each other across every listing method; two users in
one organisation see the same lines; the back-fill is idempotent.

Verified against a clone of the real database, three applications: 6 accounts each became an
organisation of one, every line, thread, finding and BOM row back-filled, no row in an
organisation other than its owner's, all 497 run_events preserved, and every account reaching
exactly what it reached before. Then in a browser: a procurement account added to an engineer's
organisation opened the engineer's line from its own dashboard. **Written, not deployed.**

**Delegation note.** This was handed to Codex first and the result was reverted. Its sandbox has
no PostgreSQL, so a *database migration* was the one task shape it cannot test at all: it shipped
`save_findings` with 16 columns against 15 expressions and 13 parameters, broke 20 store tests it
never ran, added none of the five tests the brief asked for, and hedged the whole migration behind
`if org_id is not None else` branches calling two different arities. **Do not delegate schema
work.**

### 11b · A decision names who may answer it — **DONE**

**Files** `graph/nodes.py`, `graph/state.py`, `api/app.py`. Brief: `tasks/ITEM-11B.md`.

**Done when** a run carries the roles permitted to answer each open decision; `/resume` checks
the answering user against that; and waivers are scoped to `(rule, subject, mpn, revision)`
instead of `(rule, slot)`.

Organisation membership is necessary and not sufficient — on its own it lets anyone in the
company answer anything, and "procurement signed off the junction temperature" is a worse
failure than the 404 it replaced. The permission belongs to the **question**, because that is
where the expertise is.

**The authorisation check sits at the HTTP boundary, never inside a node.** LangGraph 1.2.11
re-executes an interrupting node from the top on resume and matches resume values to
`interrupt()` calls *by index*; a refusal inside the node would have already re-run its work and
would consume or misalign the pending interrupt.

**Test** a procurement user resumes an engineer's run at a procurement gate and is refused at an
engineering gate; an approval granted for one candidate does not carry to the next.

Both hold, over HTTP, against a run the graph actually paused — and both were confirmed to fail
when the check is removed, because a security test that passes for the wrong reason is worse
than none. `tests/test_roles.py` reads the rule names out of `rules.py` rather than from
evaluating a board: the obvious version ran one board, covered nine rules of twelve, and would
have passed while `energy_budget`, `footprint` and `rail_coverage` went unmapped.

## 12 · Fan-out and the matrix — **DONE**

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

Built as `continuity/matrix.py` (pure fan-out), `api/matrix.py` (`POST /matrix`) and
`routes/matrix.tsx`. Verified in a browser against three seeded product lines and four sourced
candidates: NCP1117 fails the gateway on thermal and is captioned *engineering*, LD1117 holds it
with **1.5 °C to spare** in its own colour, and the grid names which candidates clear every line.
**This is the screen that closes both coverage gaps** — every cell reports all five labels
including the zeroes, and margin travels end to end for the first time.

Two things the browser found that the suite could not:

- **`t_j_max` was missing from `DOSSIER_FIELDS`.** The thermal rule falls back to `temp_max`
  when no junction limit is known, and those are different quantities — NCP1117 is graded to
  125 °C *ambient* and rated to 150 °C at the *junction*. A stored dossier carrying the first
  and not the second checks every board 25 °C too harshly, with a verdict that reads fine.
- **The matrix did not install the stored-dossier lookup** a design run installs, so all four
  SOT-223 regulators fell back to the package table's single figure and produced four identical
  junction temperatures. Honest — the evidence row said *"package table (per-package
  approximation, board unknown)"* — and useless for choosing between them.

**Resolved 7 Sep, and the research corrected my first reading of it.** The 12 V did not come
from JLCPCB mis-transcribing TI's datasheet — it came from a *second manufacturer's* listing
under the same MPN, which PARTS.md had already flagged. So there were two causes and both are
fixed:

- **`api/matrix.resolve` refuses to choose between manufacturers.** One MPN, two listings,
  raises `Ambiguous`, and the grid names it. Picking the first was checking a board against a
  part nobody named.
- **A verified datasheet reading outranks a listing on `dossier.ENGINEERING_FIELDS`.** TI
  publishes 2 V–5.5 V recommended and 6 V absolute maximum; the listing said 12 V, double the
  voltage the part survives. Commercial fields stay the other way round — stock, price, lead
  time and lifecycle are the distributor's to state and no datasheet knows them, which is what
  `normalize`'s "a live listing is the buying truth" was always about. It was simply being
  applied to fields it was not written for.

The override is gated on an explicit `VERIFIED_PREFIX` marker, so nothing already stored
changes meaning: a fact recorded by an earlier run still only fills a blank and cannot quietly
outrank the listing it was copied from.

## 13 · AML, AVL and the two gates — **DONE**

**Files** policy layer, `graph/nodes.py`, `api/app.py`, `api/store.py`

**Done when** AML and AVL are separate lists; an unqualified MPN routes to engineering and
quality; a qualified part from an unapproved source routes to procurement; and an approval
records identity, timestamp, the rule that fired and a rationale.

**Test** the gate fires on an unqualified part with **no** electrical failure, since approval
cannot depend on failure.

Built as two engine rules — `part_qualification` and `source_approval` — for exactly that
reason. A gate that only asked once something else had already failed would clear an
unqualified part every time it happened to be electrically fine, which is most of the time.
Being rules, they also appear in every matrix cell and carry the same five coverage labels.

**No list is not an empty list.** `organisations.keeps_aml` / `keeps_avl` exist because that
distinction cannot be derived from an empty table: a company that never set an AML has not
asked the question, and answering it for them reports a policy breach on every part of every
board. `ApprovedLists` uses `None` versus `frozenset()` to keep the two apart, and the rules
report `not_applicable` for the first.

**The approval ledger completes item 11b.** `/resume` now carries the answering user into the
run through `Command(update=...)`, because only that request knows who is at the keyboard —
the graph is resumed by whichever process serves the call. `rationale` is a *separate* field
from `answer` and that turned out to matter: `answer` is matched against the options the run
offered, and prose it does not recognise is treated as guidance for the next attempt, so
somebody who typed their reasoning into it would have explained themselves and approved
nothing. The question block now shows which roles may answer, before they type, which also
closes the audit's 🟡 about a 403 arriving too late.

## 14 · Mailbox connector, both directions — **INBOUND DONE, TRANSPORTS BLOCKED**

**Files** new module, `api/app.py`

**Done when** an unread message with a PDF attachment starts a run, and a gate sends a real
approval request naming the decision, the evidence and the requester. A POST endpoint accepts
the same PDF so the demo never depends on mail delivery.

**Test** a PCN sent to the mailbox starts a run within one poll; a gate produces a delivered
email; the POST path produces an identical run.

**Verified live**, on a running server against the real model, with a hand-built PDF: every
field read back with its quoted line, and exactly the three product lines carrying the part
returned out of four. `tests/test_notices.py` builds that PDF without a library — the project
has no PDF *writer* and should not gain a dependency to test a reader — because every other
test in the file feeds plain text, which left the branch that actually matters unexercised.

**Built:** `continuity/notices.py` reads a PCN — PDF or plain text — under the same
claim-and-verify discipline as the datasheet extractor: every value comes back with the line
it was read from, and a line the document does not contain is refused. That check has teeth.
A model can otherwise quote a real sentence and hang any part number off it, which satisfies
containment while sourcing nothing, so the MPN must also appear *in the line quoted for it*.
A notice whose part number cannot be sourced returns nothing at all rather than a partial
guess, because everything downstream keys off that number.

`POST /notices` takes the document, persists it with its quoted lines — item 15 has to cite
the document that caused a change request, and "somebody said this part was going away" is
not a citation — and answers the question a notice raises and never answers: which of the
products we ship carry this part. That is `lines_exposed_to`, the b-tree probe item 10b made
the BOM a table for.

**Deferred by decision, 8 Sep** — see DEFERRED. IMAP polling in and SMTP out both need mailbox
credentials this project does not have. Nothing about them is hard — the reader and the store
are transport-agnostic and a poller is a loop around `notices.read` — but inventing a mail
account is not mine to do. BUILD already wanted the POST path *"so the demo never depends on
mail delivery"*, and that path is complete, so the demo does not need the mailbox; the
outbound approval request does.

## 15 · The change request — **DONE**

**Files** new module, store, frontend

**Done when** each affected line yields a persisted request carrying baseline and revision, the
notice that triggered it, the proposal with alternatives rejected and why, the evidence, **what
was not assessed**, cost split into recurring and one-time, and the approvals required.

**Test** the three demo lines produce three requests, each naming its unassessed checks.

`continuity/change.py` builds them. **Superseded by item 20:** a review now runs as three
concurrent substitutions on one stream through `POST /notices/{id}/review/run`, and the
one-shot endpoint below has no caller in the app. What it described was true when written and
the packet it produces is unchanged. `POST /notices/{id}/review` runs the whole flow in one
call — exposure finds the lines, the matrix checks every candidate against each line's own
stored conditions, and the request is that work written down. **One per line**, because the
answer differs per line, which is the finding a single manufacturer-wide recommendation
cannot express and the reason any of this exists.

Three things the document does that a proposal alone would not:

- **Every rejected alternative carries the sentence that killed it.** A proposal on its own
  asks to be trusted; one that shows its rejections asks to be checked. A *viable* alternative
  that simply was not chosen is recorded too, because the second choice is where the next
  notice starts.
- **`not_assessed` and `no_evidence` are separate fields.** "We do not answer this" and "we
  tried and had nothing to read" are different admissions, and folding them together loses the
  actionable one.
- **Cost splits recurring from one-time, and the one-time figure comes off the AML.** Item
  15a's DoD numbers — about $1,281 with an already-approved part against $15,656 qualified
  from scratch — make item 13's approved list pay for itself in the document. Recurring cost
  is `None` without a stated annual volume rather than assumed, because an assumed volume
  makes a plausible number out of nothing.

The manufacturer's own recommendation is tried **first**, so a request that departs from it
has visibly departed rather than never considered it — and on the gateway it does, with
*"159 °C junction against a 150 °C limit"* printed as the reason.

---

# Phase 4 · Demo assets

## 15a · Precedents — **WRITTEN AND SHOWN, NOT YET READ BY A REVIEW**

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

**Rejections are built**, and they were the missing half. A `precedents` table records both
outcomes against the conflict *signature*, and the two are deliberately asymmetric: a
**rejection is scoped to the board it happened on**, because a part that cooks the gateway
says nothing about a line running 20 °C cooler on half the current, while a **success is
evidence anywhere in the company** — already qualified on one product is the cheap answer on
the next, which is the entire distance between $1,281 a resolution and $15,656.

A ruled-out candidate is never proposed again and still appears among the alternatives
carrying the reason. Dropping it in silence would make the document read as though it had
never been considered, which is the first question its reader would ask. Verified end to end:
two reviews of one notice, the second declining the recommendation the first learned cooks
the gateway.

**The success half is written now.** Item 21 writes a `worked` precedent the moment a
substitution is approved, against the conflict's signature, and `/memory` reads it back and
shows it under the part it was about. That closed the writing gap this section was opened for.

**What is still missing is a consumer.** `worked_anywhere` has no caller anywhere in
`continuity/` — audited 9 Sep — so a part approved on line A does not surface as the cheap
answer when line B hits the same signature. `api/review.py` reads `rejected_on`, so the
rejection half is mechanised end to end, and the success half is currently only shown to a
person. The business argument this section opens with, $1,281 against $15,656, rests on the
half that is not wired. Logged 🟡 in [DEFERRED.md](DEFERRED.md).

---

## 16 · Seeded world — **DONE**

**The demo does not exist without this**, and it is not presentation work.

**Files** a seed script, fixtures

**Done when** five product lines exist with BOMs, operating profiles and revisions; three carry
AMS1117-3.3; AML and AVL records exist with LD1117S33 deliberately absent from the AML; and two
accounts exist — an engineer and an approver with a procurement or quality role.

**Test** the seed runs from an empty database and the demo plays end to end afterwards.

`tools/seed_world.py`, under test in `tests/test_seed.py`. Both halves hold: it builds from
an empty database, refuses a second run rather than doubling the world, `--reset` replaces it
and leaves one company, and the full flow plays — a notice reaches three of five products and
each gets a change request whose proposal differs.

**The AML is derived from what ships rather than picked.** A part in production has been
qualified by definition. The first version listed only the four regulators, and every board
then failed qualification for the modules and the capacitor — parts nobody was proposing to
change. Deriving it also gives LD1117's absence an honest reason: nothing ships with it.

**And the demo got better for it.** With both gates live the gateway declines the
manufacturer's recommendation on physics — *159 °C against a 150 °C limit* — and declines
LD1117 on qualification, then takes TLV1117: approved, and 35 °C of margin against LD1117's
1.5 °C. The better answer on both counts, and it took two gates on two different desks to
find it. That is a stronger beat than the one the scenario was written around.

**This also unblocks the red item from the last audit.** The seed writes the PARTS.md
readings as *verified* facts, which is the writer the verified-over-listing rule was built
for and did not have.

## 17 · The notice — **DONE**

**Done when** a PCN document exists that parses, **labelled as a constructed example** rather
than passed off as a real manufacturer notice. It recommends NCP1117ST33 — plausible, since
onsemi is a genuine AMS1117 second source — and the recommendation fails the gateway.

**Test** the parser extracts every declared field from it, and reports the fields it cannot find
rather than inventing them.

`docs/world-finals/notices/`, written by `tools/make_notice.py` on top of `tools/pdf.py` — a
very small PDF writer, added because the project reads PDFs everywhere and could not produce
one. Both halves hold, offline against the real documents and live against the real model,
in `tests/test_notice_document.py`. The seed's end-to-end test now uploads the actual PDF
rather than four typed lines, and the suite refuses a document that was edited without being
regenerated.

**Two documents, because the second one is the test.** `PCN-2026-114` states every declared
field. `PCN-2026-118` is a preliminary notice that withholds two of them, the way early
notices really do: the last-order date is *to be advised* and there is no recommendation.

**And building it properly found two defects a typed fixture never could.** The full notice
carries four dates and only one ends ordering. Against the real model the reader returned
**2027-09-30, the last time *ship* date** — quoted honestly from a real line, verified by
every check we had, and six months of runway the notice does not give. The instruction now
names which date is wanted; removing it reproduces the wrong answer on demand. The
preliminary notice exposed the other: `Recommended replacement: none.` is a real line, and
`none` passes the part-number shape test, so the review would have gone looking for a part by
that name. A word a notice uses for absence is no longer a part number, and — the same rule
the affected part already lived under — a recommended part is refused unless the line quoted
for it actually prints it.

## 18 · KiCad — **DONE**

**Files** new module

**Done when** a project bundle yields a BOM through `kicad-cli` and the board renders with the
footprint consequence of the chosen substitute.

**Note** pin the KiCad version. `pcbnew`'s SWIG bindings run headless but are deprecated from
KiCad 9 with removal planned for 11; the replacement IPC API needs a running GUI until 11.
`kicad-cli` SVG export is the dependable path for before-and-after evidence.

**Test** a known project yields the expected BOM rows and a rendered board.

`continuity/kicad/` — a runner, a bundle, a bill of materials, a footprint swap, the design
rule check and the render — with `api/boards.py`, `line_boards`, and a **THE BOARD** section
on every change request. Under test in `tests/test_kicad.py` and `tests/test_boards.py`,
which split at exactly the line that matters: everything that *decides* something runs with
no container at all, and the layer that shells out runs against KiCad itself. The research
that had to happen first is [tasks/ITEM-18.md](tasks/ITEM-18.md).

**Pinned to `kicad/kicad:9.0` in a container**, and it is checked before anything is
written. The tag is amd64 only, whatever Docker Hub's page claims, so Apple silicon needs
`--platform linux/amd64` and emulation does the rest.

**The verification is on somebody else's board.** `fixtures/kicad/propico` is
[ProPico](https://github.com/diminDDL/ProPico), MIT, drawn in KiCad 7 by somebody who never
heard of us, carrying a real AMS1117-3.3 in SOT-223 at U3. An ingestion path tested only
against a file we wrote proves nothing about the one a customer sends.

**KiCad answers, we report.** The substitute is placed where the retired part sits, its nets
carried pad by pad *by function*, and the same design rule check runs before and after. On
this board NCP1117 in SOT-223 adds nothing — the pads it lands on are already there — and a
SOT-23-5 in the same position takes unconnected items from 1 to 4 and adds four shorting
items and three clearance violations, each naming both ends with coordinates. That is the
decision no parametric search reaches: the cheaper part costs a layout revision on this
board and none on that one.

**The delta is the finding, never the count.** The upstream board arrives with fifty-four
violations and one unconnected item before anything is touched.

**Three things this refuses to do.** It does not route. It does not infer a pinout from a
package, so `catalogue.py` is a table of datasheet readings and **LD1117S33TR is absent from
it** — ST publishes its pin connections as a figure, and a figure is not extractable text.
And it does not wire a pad it was given no net for: a SOT-23-5's enable and no-connect stay
bare and are named on screen.

**Two corrections against what was assumed.** The plan had a normalisation pass to bring an
older board up to the pinned version before writing to it; `pcbnew` parses the 7 file and
writes 9 on save, and the swap against the untouched upstream file gives the identical DRC
answer, so there is no pass. And the render needs `--page-size-mode 1`: fitted to the board,
the SVG's coordinates have no fixed relationship to the design, and the before and after
cannot be cropped to the same rectangle.

**Found in the browser, fixed here.** A notice reviewed twice listed every product line
twice, because the listing returned every request ever written rather than the current one
per line. Every document is still kept — a change request is a record — but two of them for
one line is a document that contradicts itself.

---

# Phase 5 · The product around the engine

**Opened 8 Sep, after the first flow pass.** Phases 1 to 4 built the engine, the enterprise
layer and the board, and every one of them is tested. They were built as endpoints and three
new screens hung beside the 1.0 shell, and the old centre of gravity was left in place — a
product line is still *a design run that has not happened yet*. [DEFERRED.md](DEFERRED.md)
carries the nine findings; this phase is the fix.

**The shape, decided 8 Sep.** The product line is the centre. An EOL review is a **run on a
product line**, not a document about one: it swaps the retired part, re-checks the whole
board against every department's rules at once, streams its reasoning, stops at a gate
addressed to the desk that owns the failing constraint, and on approval **applies** the
change. The notice is the trigger. The three runs happen **concurrently**, which is the
multi-board machinery SCENARIO-B marks as the most demoable moment in the scenario, and it is
what turns the pacing problem into the argument: a team does these legs one email at a time.

## 19 · The shell and the product line page — **done 8 Sep**

**Files** a page-chrome component, `routes/line.tsx`, `api/lines.py`

**Done when** every screen shares the chrome `/lines` already has, a row opens the product
line rather than the brief entry, and that page shows what a product line *is*: revision,
ambient and rail, the bill of materials from `line_parts`, a component graph, the attached
board, and the notices that reach it.

**Note** the graph is derivable today and nothing builds it. A design run's slots and edges
come from the planner; a stored line's come from its profile, whose rails carry `source` and
`members` — the seeded Gateway is `vin 5 V → u1 → 3v3 → u2, c1`.

**Test** a seeded line renders its parts, its graph and its exposure with no thread in
existence, and the words "Never run" appear nowhere.

## 20 · The substitution run — **done 8 Sep**

**Files** `graph/substitute.py`, `api/review.py`

**Done when** a review of a notice runs one substitution per affected line, concurrently, on
one multiplexed stream, and each run emits the same event vocabulary the workspace already
renders — reasoning, checks, conflicts, a question carrying the roles that may answer it, and
an approval.

**Note** one stream, not one per line. Browsers cap around six HTTP/1.1 connections per
origin and the client already streams over `fetch`; three streams plus the page's own calls
sit on that limit, and three sequence spaces race. Every event carries its line.

**Note** no planner. The board exists. The run is: place the candidate, re-check the whole
board, route the failure, ask, apply.

**Test** three lines run at once from one notice and finish with three different verdicts —
applied, paused at a desk, and no viable part — and the paused one refuses an answer from a
desk that does not own it.

**What actually happens, 9 Sep.** The concurrency, the stream, the per-line verdicts and the
403 are all built and tested. The *three different kinds* of verdict are not reachable in the
seeded world: all three lines find a candidate that clears, and every question is addressed to
engineering, so nothing is paused at another desk and nothing comes back with no viable part.
The refusal is covered by `tests/test_review_api.py` rather than by the demo. This is the 🟡
in [DEFERRED.md](DEFERRED.md) about every column ending at engineering, and it is a question
about the seeded world rather than about this item.

## 21 · Applying the change — **done 8 Sep**

**Files** `api/review.py`, `api/store.py`

**Done when** an approved substitution writes the new part into `line_parts`, bumps the
revision, records the approval against the person who gave it, records a **successful**
precedent, and leaves the product line page showing the new part in its graph, its bill and
its board.

**Note** this is what closes the successful-precedent gap open since item 15a. A rejection is
scoped to its board; a success is evidence anywhere in the company.

**Test** after approval the line's stored bill carries the substitute, the revision has
moved, and a second notice on another line offers the precedent.

## 22 · The notice arrives by email — **done 9 Sep**

**Files** `continuity/mail.py`, `api/notices.py`

**Done when** a notice forwarded to a mailbox appears in Continuity without anybody uploading
anything, and the upload path still works unchanged as the fallback.

**Note** IMAP polling, not a webhook: it needs an account and an app password and no public
URL, so the venue's network is not on the critical path. `CONTINUITY_MAIL_HOST`,
`CONTINUITY_MAIL_USER`, `CONTINUITY_MAIL_PASSWORD`.

**Test** a message with a PDF attachment becomes a stored notice with `source` recording the
mailbox it came from, and a message with no notice in it is left alone rather than guessed at.

**Verified live 9 Sep against a real Gmail mailbox.** `continuity/mail.py`, started from the
app's lifespan when the three variables are set and silent when they are not.

A forwarded `PCN-2026-114.pdf` became a stored notice with no upload: the right part, the
right last-order date, and the quoted line it came from. The three unrelated messages beside
it were read, found to hold no notice, and left alone. `CONTINUITY_MAIL_ORG` takes an email
address as well as an organisation id, because a reseed mints a new id and a stale one fails
by quietly finding no product lines.

`deliveries` is the whole IMAP conversation and `collect` decides what becomes a notice, so
everything worth getting wrong is tested without a server. `tools/check_mail.py` proves the
credentials on their own, because "the mailbox will not let us in" and "we read the message
wrongly" are different problems and only one of them is ours.

Four decisions worth knowing:

- **The read position is a stored UID, not the `\Seen` flag.** Marking messages read is the
  obvious way to remember what has been handled and it breaks the moment anybody opens the
  mailbox in a browser, which is the first thing a person does when checking that their
  message arrived. `mail_cursor` holds the UID with the folder's `UIDVALIDITY`, because the
  RFC lets a server renumber a folder and says every remembered UID means nothing when it
  does. The cursor goes into `deliveries` rather than a bare UID, since only that function
  can see the server's validity before choosing the search.
- **`imap-tools`** rather than raw `imaplib`. Apache-2.0, no runtime dependencies of its own,
  and the traps in reading a message are all in the parsing. It does parse with the compat32
  policy, so `mail.parse` re-reads the bytes under `email.policy.default`; without that every
  real message would have yielded no documents while every test passed.
- **Attachments first, the body only when nothing readable was attached.** A PCN is usually a
  PDF and sometimes pasted, and a signature logo is on almost every corporate message.
- **A message with no notice is left alone.** Nothing stored, nothing deleted, nothing
  guessed. The position still advances past it, and the loop does not poll at all while the
  model is unavailable, so no message is passed over unread.

**The one thing a run-through has to know:** Gmail files a forwarded notice as spam. An
attachment, no sending history and often no subject is close to a textbook spam signature, and
the poller reads `INBOX` only, on purpose. `tools/check_mail.py` reports mail sitting in a
quarantine folder and names the filter that stops it.

## 23 · Memory, on the company's record — **done 8 Sep**

**Files** `api/recall.py` (new), `api/store.py`, `routes/memory.tsx`

**Done when** memory reads what the company actually has — the parts across every product
line, the notices received, the change requests raised, the precedents on both sides and the
approvals given — rather than only what a design run left behind.

**Test** a seeded company with no design runs at all has a memory worth reading.

The reads live in `store.memory_for_user` and the assembly in `api/recall.compose`, which is
pure, so the shape of a memory is testable without a database. Each part carries every board
it sits on **and the reference designator it sits at**, the notice that retired it in the
document's own words, and one entry per thing that was decided about it: recommended,
worked, ruled out, approved, or waiting on a desk.

Three things the work turned up, all fixed:

- An approved decision was remembered twice. Answering one writes the decision's own row
  *and* an approval in the same request, so memory listed both and the screen read as one
  board approving the same part twice. The approval is the fuller record because it names
  the person, so a settled decision is now shown through it. A **declined** one is still
  listed on its own, because a refusal writes no approval and nothing else remembers that
  somebody said no.
- Ten of eleven part facts appeared to cite a datasheet line reading *"source unavailable"*.
  `part_facts.source` carries a marker and a quotation in one string; `recall.fact_from`
  splits them, and the panel uses quotation marks only when there are words to quote.
- A retired part cited its notice to `api`. The upload now records the document's filename.

**Lifecycle comes from the notice's own date**, and the two answers differ in the way a buyer
cares about: a last order date that has passed makes a part `obsolete`, and one still ahead
makes it `nrnd`. A notice that withholds its date, as `PCN-2026-118` does, still gets `nrnd`.
Nothing here overwrites a lifecycle a distributor stated.

## 24 · The walkthrough goes — **done 8 Sep**

**Done when** the replay, its route and the first-sign-in redirect are gone, and signing in
lands on the product lines. It teaches a story the product no longer tells, and this is a
finals demo rather than an onboarding funnel.

---

# Phase 7 · The second flow pass, 9 Sep

Sparsh ran the app end to end for the second time. Every finding is one symptom of the same
mistake as Phase 5, made again in a smaller way: **the product line page was built beside the
design workspace instead of being it.** A second screen that renders a graph and a bill of
materials worse than the screen that already renders a graph and a bill of materials.

The decision, taken 9 Sep: **Plan A.** `/lines/:id` becomes the workspace. `/design/:lineId`
survives and is reached from the product's own menu, so the Singapore design run and the 900
tests behind it keep working.

The beat this serves, in his words: all product lines functional, show how a line is added,
say an important part is going end of life and send the email on stage, Continuity announces
it, then go to the product and show the graph with the retired part in red.

## 25 · The product line page is the workspace — **done 9 Sep**

**Files** `api/review.py`, `review/useLineReview.ts`, `review/ReviewTrace.tsx`,
`routes/line.tsx`, `routes/lines.tsx`, `board/BoardConsequence.tsx`

**Done when** `/lines/:id` renders with the workspace's own components rather than a second
implementation of them: the component graph, the trace panel beside it, the bill of materials.
The notice banner carries **REVIEW THIS LINE** and the review runs *on this page*, so the
question and **APPROVE AND APPLY** arrive in the trace panel where a person is already looking.

**What shipped.** `POST /notices/{id}/review/run` takes an optional **`line_id`**, and that is
the whole of the backend change. One endpoint, one engine, one set of frames: the product line
page asks the question about itself and `/changes` asks it about the company, and the two
cannot drift into meaning different things by a review. `useLineReview` holds the run and
`ReviewTrace` renders it beside the graph, using the design workspace's own `ReasoningLine` so
the two panels are the same panel to look at.

**It is the design workspace, not a page that borrows from it.** The first attempt put the
panes into `Page` — the constrained, scrolling container `/lines` and `/matrix` use — which on
a wide screen is a narrow strip of content in the middle of an empty field, and which was a
second implementation of a layout this application already had. `shell/workspace.ts` now owns
the one answer to *is this route locked to the viewport*, `AppFrame` and `AppShell` both ask
it, and `/lines/:id` is in it. Three panes, full height: the trace, the picture, the bill.

**The trace is a pane, not a popover.** It briefly had a CLOSE button, which made the left
third of the workspace vanish and took the board toggle with it. What is coming for this
product lives at the top of that pane rather than in a banner across the page, because the
notice is the reason to run anything and it belongs where the reader already is.

**The idle pane carries the check the page already runs** — *"22 checks, nothing failed"* —
which gives the green picture the number that computed it, and is where a **failing** rule
finally gets a sentence. That was logged 🟡: a check failing painted a part red and said
nothing anywhere. What is deliberately not there is what could not be checked.

**The banner is no longer a link away.** It was one button that navigated to `/changes`, which
is how a whole run-through was spent looking for a review that was on another page. It now
carries **REVIEW THIS LINE** and, beside it, **THE NOTICE** for the document.

**The toggle.** Once the run has a part to place, **COMPONENTS / BOARD** swaps the graph for
`BoardConsequence` on this product line's real project, before and after, placed on arrival
rather than behind a second button — choosing BOARD is already the request.

**Colour in the trace panel means a rule's verdict and nothing else.** The first version gave
every line the design workspace's green tick, which put the mark of a pass beside *"159 °C
junction against a 150 °C limit"* — the single most important sentence in the whole flow.
Narration is neutral now, and the five coverage labels have five marks. Same discipline as
item 27's colours.

**Cyan is seeded from the notice, and had to be.** The intended middle act — the position goes
cyan while the engine works on it — never rendered. Measured on screen: the run's own first
mention of the position arrives with the burst of per-line frames at the *very end*, because
everything before it is discovery about the part rather than about this board. Waiting for the
engine to name the slot showed it for a fraction of a second, sixty seconds after the button.
The notice already says where the part sits, needs nothing computed, and the banner above is
rendering the same fact — so the run starts from it and the engine's own answer replaces it.

**Note** the row menu on `/lines` gains **DESIGN RUNS**, opening `/design/:lineId`. Clicking
the row still opens the product. The design flow is reachable, and it is no longer the thing
you get by accident. `/design/:lineId` on a line with no runs used to open the **brief
screen**, which asked *"What are you building?"* about a product that ships today — every
seeded line is in exactly that state, so the menu item looked broken. It says there are none
and offers to start one. Seeding a design thread for a shipping product would be inventing a
synthesis run that never happened.

**Note** the rail icon for `/changes` was still `mark_email_unread`, the one `/notices` had.
It is `change_circle`: a notice arrives, a request is written, a change is applied, and the
envelope described only the first third.

### What the fourth pass changed

- **The check is cached and warmed.** `POST /lines/{id}/check` took four to seven seconds
  on every visit and never got faster, because the answer was thrown away each time and
  resolving three parts is three network calls. It is keyed on a digest of the bill, the
  profile and the revision, so applying a substitution invalidates it by changing it; and
  the API checks every line once at startup, so the first person to open one is not the
  person who waits. **Measured: 4.1 s → 11 ms.** One input can change without the key
  changing — a distributor's stock — and the docstring says so.
- **The page header is 64 px, not 48.** At 48 with a 10 px subtitle the product's name was
  a strip of grey nobody could read across a room. The KiCad project's name moved out of
  that subtitle and into the board pane's own header, which is the pane it is about.
- **`design/BomTable` offers the datasheet control only where it can be used.** A row whose
  listing states no package rendered the same *Attach PDF* as every other one, disabled —
  identical text, identical styling, `disabled` on a visually hidden input — so it read as a
  control and did nothing when pressed. The explanation sat underneath as body text, which
  ran a sentence about thermal table columns down the whole column, and then as a `title`,
  which nobody hovers. Three presentations of one fact; not drawing an unavailable
  affordance is better than all of them, and what is left points at the rows where a
  datasheet would actually change a verdict.

### What the second pass changed, and why the first was wrong

Repurposing the design page meant *using its components in its grammar*, and the first two
attempts used its components in a layout of my own. Sparsh's words: **"You are literally
redesigning a good UI component and making it shittier in the process."** He was right.

- **The notice is a conflict, so it opens where a conflict opens.** `design/ConflictPanel`
  replaces `design/BomTable` on the right when a board has something wrong with it. An
  end-of-life notice against a product line is exactly that, so it opens there —
  `review/NoticePanel` — with **REVIEW THIS LINE** inside it and a header button that reads
  `End of life (n)`, beside the same status chip the design workspace carries. It had been a
  banner across the page and then a block at the top of the trace, and both were a third
  place for something this application already has a place for.
- **A past decision opens in that same drawer.** `RequestCard` moved out of
  `routes/changes.tsx` into `review/RequestCard.tsx` and both surfaces render the one
  component. The reasoning that changed *this* product belongs on this product: proposal,
  every rejection with the sentence that killed it, evidence, the board consequence, cost,
  and the desks that signed — without leaving the page.
- **The bill of materials is `design/BomTable`'s table**, sticky head, zebra rows, and the
  conflict row lit red with the part it is about. The two panes used to disagree: a part red
  on the graph was an ordinary row in the bill.
- **The board toggle is always there** once a project is attached, in the middle pane's own
  header. It used to appear only when a live review had a candidate and vanish on reload,
  so *show me the board* was answerable for about a minute a day. `GET /lines/{id}/board/render`
  draws the board as it is; with a candidate — from a run or from an earlier decision — it is
  `BoardConsequence`'s before and after.
- **REPLACE BOARD and the BOARD panel are gone.** A project arrives with the design; the row
  menu on `/lines` already has *Attach board* for the case where it did not. The panel said
  a filename and a byte count, which is not something anybody looks at a product to learn.

**The graph is one size now.** It filled whatever box it was given, so the same three parts
drew at 0.47× on a laptop and 1.2× on a projector. `buildGraphLayout` sizes the picture from
its own content instead — a tier with nothing in it is not drawn, and the height follows the
row count to the same ceiling as before — and the pane scrolls rather than shrinking. A full
design board is laid out exactly as it always was; a three-part product line is drawn small
instead of drawn sparse.

**Verified in a browser** on the seeded world, twice end to end. Gateway: TLV1117LV33DCYR, 35
°C spare, board clean at U1 SOT-223 → SOT-223, applied, Rev C → **Rev D**, banner gone, three
parts green. Sensor node: NCP1117ST33T3G, 84 °C spare, applied, **Rev D**, U1 onsemi. Cabinet
controller: NCP1117ST33T3G, 11 °C spare. The position holds cyan for the full run.

**Found while verifying, and fixed:** `/lines/{id}/check` was returning **500 on every seeded
product line**, so the page a demo opens with was painted entirely by its fallbacks. See
`parts/dossier._FLOAT_FIELDS`.

**Test** a seeded line renders the graph, the trace panel and the bill, and a review started
from the notice panel finishes without leaving the page.

## 25a · Every seeded product line arrives already described — **done 9 Sep**

**Files** `tools/seed_world.py`, `api/app.py`

**Done when** `/design/:lineId` on a seeded product line opens a finished run rather than the
brief screen, because a product that ships did not arrive by somebody being asked *"What are
you building?"*.

**What it records.** Not a synthesis. A product line enters Continuity by having its bill of
materials and its operating profile entered — RUNNER step 2 — and that is the run this
writes: the parts the company recorded, the rails the profile states, and **every check from
`rules.evaluate` on the board those two make**, which is the same call `/lines/{id}/check`
makes when the page opens. Seeding a synthesis would be inventing work that never happened.

**The trace is the record; the checkpoint is a cache.** Restoring a run read LangGraph's
checkpointer and gave up when it could not, even though every frame the client draws the
board from is in `run_events` — which is how the live client draws it in the first place.
`_board_from_frames` rebuilds slots, edges and the supply from the stored `plan` and
`selection` frames. That is what lets the seed write a run without executing a graph, and it
also means a run whose checkpoint was lost no longer loses its board.

**Test** every seeded line has exactly one finished run of 36 frames, and its board restores
from the frames alone with three parts, their supply and their edges.

## 26 · The seeded world ships with its boards attached — **done 9 Sep**

**Files** `tools/seed_world.py`

**Done when** the five seeded product lines already have their KiCad projects, so the demo
does not open by zipping a fixture and uploading it. A company that ships five products has
five projects; making that a demo step was an accident of item 16 landing before item 18 and
nobody joining them.

**What shipped.** **Three** real projects, one per affected line, each drawn by somebody
else and each carrying the retired part at a different designator: ProPico at U3, the
WS2812 WiFi controller at U1, the OpenJBOD RP2040 at U2. One file attached to three products
would claim they are the same board, which anybody can check by opening two of them.

**A board is a design, not a bill.** The first attempt imported ProPico's forty-one rows as
the product line's bill of materials, which dragged thirty-eight passives in front of rules
with no business checking them, and I defended the resulting `evidence_missing` noise as
honest coverage labelling. It was a scope violation wearing honesty as a costume. Bills stay
at three parts: the regulator, the load, and the output capacitor. `api/boards._consequence`
reads the board's own bill out of the file when it runs, so a project is self-describing and
never needed importing. See FLOW.md §7a.

**Test** a freshly seeded line reports its board without anything being uploaded, no two lines
report the same project, and the board consequence runs on all three.

## 27 · The graph means something — **done 9 Sep**

**Files** `continuity/linegraph.py`, `api/lines.py`, `design/ComponentGraph.tsx`

**Done when** the graph tells the story in three acts, and each colour is a different kind of
claim so that none of them is unearned:

- **Green before anything happens** — the engine checked this line under its own stored
  conditions and it passes. Computed, not asserted. `matrix.build_matrix` already does exactly
  this check and nothing calls it for a line's own incumbent parts.
- **Red at the retired part** — a *fact from the notice*, not a compatibility verdict. It
  needs nothing computed and claims nothing the notice does not say.
- **Grey while a review runs** — true, because the board is genuinely being re-checked.
- **Green again on approval** — the verdict the review actually produced.

**What shipped, and where the description above was wrong.** Green is the **resting state**,
not something the page waits for. A shipping product line renders green immediately and a
part is repainted only when something is wrong with it. The first attempt made green wait for
the check and painted everything grey until it returned, which made five working products
read as broken for several seconds on the page a demo opens with.

`POST /lines/{id}/check` runs the engine per line and repaints a part red if a rule actually
fails. It does not gate the colour and it produces **no text on the page**. An earlier version
put a coverage paragraph under the picture; see the second governing rule at the top of this
file for why that was worse than the grey it replaced.

**A shipping line has to be checkable with no distributor reachable.** `_resolve_quietly` used
to catch only ambiguity, so a timeout took the whole check down, and there was no fallback.
`dossier.part_from_facts` now builds a part from the readings this company recorded, which are
better evidence than a listing rather than a degraded substitute. Verified with the
distributor made unreachable: all five lines, 22 checks each, nothing unresolved.

**Test** a seeded line with no notice against it renders every slot valid, the same line under
a notice renders the retired slot in conflict and the rest valid, and a line checks clean with
no distributor answering at all.

## 28 · The notice announces itself — **done 10 Sep**

**Files** `shell/`, `routes/lines.tsx`

**Done when** a notice arriving by email raises a notification wherever the user is, naming
the part and how many products it reaches, and the affected rows on `/lines` change to show
it without a reload. Tasteful: one line, dismissible, not a modal.

**Note** this is the moment the demo turns on. He sends the mail on stage and the app has to
react while he is talking, or the beat dies waiting for somebody to press refresh.

**Note, from the third pass on 10 Sep**, the sequence this has to serve, because it decides
what updates and not just what pops up. The mail goes out at the start of the explanation of
how an engineer adds a product line. Twenty to thirty seconds pass while he keeps talking, on
`/lines` rather than parked on `/changes`. The notification then arrives wherever he is, the
affected rows on `/lines` change, a product line already open turns its regulator red on the
power tree and in the bill, and it offers the review. Only then does he go to `/changes`.

`routes/changes.tsx:19,54` already polls on ten seconds and is the only poll in the product.
Extending that into one provider above the router, which raises the toast and lets every route
refetch off the same tick, is cheaper than a second transport. See
[RESEARCH-3rd-Passthrough.md](RESEARCH-3rd-Passthrough.md#r1-the-notice-has-to-announce-itself).

**Test** a notice stored while `/lines` is open changes the affected rows and raises the
notification without a navigation.

**Verified.** Playwright opened `/lines` and an affected product line, delivered
`PCN-2026-114` after both pages established their initial notice baseline, and observed the
dismissible `AMS1117-3.3 affects 3 product lines.` notification on both. The list row changed
to `1 notice`; the open product changed from `End of life (0)` to `(1)`, without navigation.

## 29 · `/notices` becomes `/changes`, and stops being a page for uploading — **done 9 Sep**

**Files** `routes/notices.tsx` → `routes/changes.tsx`, `main.tsx`, `shell/`

**Done when** the page is a list of what has arrived and what it affects, the upload is the
fallback it actually is rather than the page's headline, and a received notice is **selected
by default** so the review is reachable without knowing to click a 10px chip.

**Note** the bug this fixes: a mailed notice arrives, the page shows it as an unselected chip,
and the copy reads *"Receive a change notice to begin"* — which is false, and is why the
review looked missing. The banner on a product line navigated here with nothing selected,
which made it worse.

**Note** the name. A change notice arrives, a change request is produced, a change is applied.
One word carries the whole vocabulary, and `/notices` describes only the first third.

## 30 · Three lanes, not three columns — **done 9 Sep**

**Files** `review/ReviewColumns.tsx` → `review/ReviewLanes.tsx`

**Done when** the company-wide run renders as one row per affected product line rather than
side-by-side columns of streaming text.

**Note** the reasoning, since the current shape was a deliberate choice and is being reversed.
What has to land is *simultaneity* and then *disagreement*. Nobody reads three traces at once,
and three narrow columns of 10px monospace on a projector is noise. One legible row each —
the product, what it is trying now, its state — makes the parallelism obvious, and the three
verdicts read down a column, which is the comparison worth pointing at. Any lane expands in
place for the product worth going deep on. It also survives five affected lines, where five
columns would not.

**What shipped.** `review/ReviewColumns.tsx` → `review/ReviewLanes.tsx`. One row per affected
product line: the product, the newest thing that board has said, and its verdict. The
verdicts align down a single column, which is the comparison the whole scenario exists to
point at — NCP1117ST33T3G on one row and TLV1117LV33DCYR on the next, seen without reading
anything. A row expands in place and the others stay as they are.

**The question stays out of the fold.** A decision waiting on a desk is the one thing on
that page nobody should have to expand a row to find, so it renders under its lane whether
or not the trace is open.

**Verified in a browser** on the seeded world: two affected lines advancing together on one
stream, two different answers, expanding one leaving the other collapsed.

**Test** three lanes advance together on one stream and end in three readable verdicts, and
expanding one shows its full trace without collapsing the others.

## 30a · A finished review can be read back — **done 9 Sep**

**Files** `api/replay.py`, `api/lines.py`, `api/store.py`, `review/useLineReview.ts`

**Done when** reopening a product line shows the trace of the review that changed it, in the
left pane, the way reopening a design run shows its own.

**The asymmetry this fixes.** Every frame a design run emits is written to `run_events`; a
review streamed its reasoning to whoever was watching and kept only its conclusions. So a
line that had been reviewed showed a part number and a date — the answer with none of the
working — on a product whose whole claim is that a person can see why a substitution was
chosen.

**Nothing new is stored.** `decisions.document` already holds every candidate the run tried,
the sentence that settled each, and the winner's verdicts; `api/replay.frames_from`
reassembles the trace from it, and the frames go through the same reducer a live run goes
through. One thing is *not* reconstructed and is not invented: each candidate's origin —
*"recommended by the notice"*, *"found in the distributor's catalogue"* — is not stored per
attempt, so a replayed line reads "Trying LD1117-3.3." where the live one said more.

**The change request is demoted, not removed.** Clicking a notice used to open the change
request in the drawer, which duplicated `/changes` — that page lists the same document for
every affected line. The trace is *how* this board reached its answer and belongs in the
left pane; the change request is the document somebody signs, and it is one line at the end
of the trace.

**Test** a line that has been reviewed replays its trace ending in `line_done` with the
proposal it chose, and a line that has never been reviewed replays nothing.


---

# Phase 8 · The cross-team response, 10 Sep

**Opened after the third flow pass, and built the same day.** Items 31 to 39 are done; what
each one turned out to involve is under its own heading, including the two things this phase
found that its plan had wrong.

The assigned topic is one question: *how does your tool coordinate the cross-team response —
design validates alternatives, procurement checks availability, and production confirms
assembly compatibility?* The build answers it with one desk.

**Nothing in this phase is a talking point.** A gap here is built, not explained.

## What it looks like now

One notice, three products, and the answers differ in where they stop:

| Product line | Answer | Stops at |
|---|---|---|
| Sensor node | NCP1117ST33T3G, 84 °C to spare | four signatures, nothing failed |
| **Gateway** | TLV1117LV33DCYR | **procurement**, on 1,133 in stock against a 5,000 build |
| Cabinet controller | NCP1117ST33T3G, 11 °C to spare | four signatures, nothing failed |

Every trace, lane and change request groups its verdicts under the desk that owns them.
Every substitution is signed by each department that examined it, in any order, and the bill
does not move until the last signature. Each desk has a queue of what it owes, with a count
on the rail, and the presenter moves between four real sessions from the rail rather than
signing out.

## Two things the plan had wrong

**Item 38 could not work as written.** `GATE_RULES` was two rules wide, so `availability`
failing discarded the candidate rather than routing it — raising a stock minimum would have
deleted the Gateway's answer, not sent it to procurement. Item 32 exists because of that and
comes first.

**The two selection paths disagreed.** `review.choose` proposes a candidate whose only
failures are answerable; `change.for_line` required `cell.ok`, so the same candidate was a
proposal in the stream and a rejection in the document. Invisible until `availability`
became answerable, at which point the Gateway's change request lost its proposal entirely.
Both now make the same two passes against one definition, in `roles.ANSWERABLE_RULES`.

## What was already decided and never built

[SCENARIO-B.md](SCENARIO-B.md) settled the design on 4 September and its own gap analysis
listed five things. Three shipped. **Two did not, and they are the two this phase exists for:**

| From the 4 Sep gap analysis | State on 10 Sep |
|---|---|
| 🔴 Multi-board fan-out | built, item 12 |
| 🔴 **Rule ownership** — tag each rule with an owning role so findings can be attributed and escalations routed | **half built.** `roles.py` is the tag. Attribution never reaches a screen, routing never fires, and the table is missing a department |
| 🟡 Approved-vendor list | built |
| 🟡 **Role-specific rendering of a shared finding** | **not built at all** |
| 🟡 Escalation addressed to a role rather than to "the user" | built in `/design`, dead in the EOL flow |

The same document also states the answer to *how do we show it*, and it has not moved:
**"Each role sees the same verdict in its own terms. One finding, three renderings — a view
layer over one shared result, never three engines."** And the standard it is held to:
**"Any change to a released design must be approved before implementation — no exceptions."**

Its open question *"how this is demoed on stage in the time available"* was never answered.
Item 37 answers it.

## The mechanism, verified 10 Sep

- `review.choose` (`review.py:152-162`) hardcodes `roles=("engineering",)` for any candidate
  that clears. Only its second pass, reached when **nothing** clears, calls `decision_roles`.
- `change._approvals_for` (`change.py:293-309`) falls back to engineering when nothing failed.
- `api/store.py:71` is `ROLES = ("engineering", "procurement", "quality")`. No production.
- `roles.py:30-31` routes `footprint` and `footprint_compatibility` to engineering, and
  SCENARIO-B assigns them to production.
- **`GATE_RULES = ("part_qualification", "source_approval")`** (`review.py:37`). Everything
  else is `physical` — *"failures no signature can clear"* — so `availability` and `footprint`
  failing means the candidate is rejected outright and **procurement and production cannot be
  asked even when their own rule is the thing that failed**.
- `answer_decision` (`api/review.py:690`) is `allowed.intersection(user.roles)`, which is
  first-response semantics on a set of desks the routing table says must *all* answer.

See [RESEARCH-3rd-Passthrough.md](RESEARCH-3rd-Passthrough.md#r8-the-cross-team-response-is-the-problem-statement-and-one-desk-answers-everything)
for the argument and [R11](RESEARCH-3rd-Passthrough.md#r11-showing-four-desks-and-demoing-them-with-one-presenter)
for the approval semantics and the stage question.

## 31 · The four desks exist — **done 10 Sep**

**Files** `api/store.py`, `roles.py`, `tools/seed_world.py`, `tests/test_roles.py`

**Done when** `ROLES` carries `production`, `footprint` and `footprint_compatibility` route to
it, and the seed creates accounts holding all four. Nothing else in this phase can be right
until the department the scenario names is something the product can express.

**Note** four, not three, and the research says four: a change control board's composition
*"should mirror the change's blast radius: engineering, quality, manufacturing and procurement
at minimum"* (SCENARIO-B). Manufacturing is the topic's production. Quality owns the approved
manufacturer list. Lead with the three the topic names and let quality be the fourth.

**Test** every role appearing in `ROLES_BY_RULE` exists in `store.ROLES`. The existing test
asserts every rule is mapped; this is the other direction, and it is the one that would have
caught a department the routing table believes in and the product does not.

## 32 · A department's own rule is a decision, not a wall — **done 10 Sep**

**Files** `review.py` (`GATE_RULES`), `tests/test_review.py`

**Done when** every rule a department owns can be answered by that department. Today only
`part_qualification` and `source_approval` are gates; `availability` failing is treated as
physics and the candidate is discarded, so procurement is never asked about a stock problem
that is procurement's entire job.

**Note** this is the item that makes 38 possible, and I had 38 planned wrongly without it.
The distinction to keep is real: a thermal failure is a wall, because no signature lowers a
junction temperature. A stock shortfall is a decision — procurement can bridge-buy, accept a
lead time, or say no. A package change is a decision too, and its answer is *production
accepts a board revision*, which is a different sentence from *this part does not fit*.

**Test** a candidate failing only `availability` is `gated` rather than `physical`, and its
proposal is addressed to procurement.

## 33 · Every check carries its department, and every screen renders it that way — **done 10 Sep**

**Files** `roles.py`, `api/review.py`, `change.py`, `review/ReviewTrace.tsx`,
`review/ReviewLanes.tsx`, `review/RequestCard.tsx`, `routes/matrix.tsx`

**Done when** the trace, every lane and every change request show the result **per department,
pass or fail**, on every candidate:

```
DESIGN         8 checks, all clear · 35 °C thermal margin
PROCUREMENT    availability clear · 1,020,639 in stock at JLCPCB, an approved source
PRODUCTION     footprint clear · SOT-223 → SOT-223, a drop-in, no layout change
QUALITY        part qualification clear · on the approved manufacturer list
```

**Note** this is SCENARIO-B's *role-specific rendering of a shared finding*, four months of
argument already settled: **one finding, several renderings, a view layer over one shared
result, never several engines.** Every figure above is computed today. The department comes
from `roles.py`, which both the graph and the matrix already read, so no second source of
truth is created. A finding may have more than one owner and that is correct rather than an
oversimplification to fix — `part_qualification` is engineering and quality by design.

**Test** a review of the Gateway emits a department against every check frame, no rule is
unattributed in the change request document, and a rule with two owners renders under both.

## 34 · A substitution on a shipping product needs every affected department to sign — **done 10 Sep**

**Files** `review.py` (`choose`), `change.py` (`_approvals_for`), `api/review.py`

**Done when** `choose` stops hardcoding engineering, and the desks required are every
department whose rules were evaluated against the change.

**Note** the current behaviour asks a desk only when there is a question for it, so a good
answer raises nobody. The standard SCENARIO-B already quotes is the opposite: *any change to a
released design must be approved before implementation, no exceptions*. That is what makes the
cross-team beat fire without inventing a failure, and it is why this is not gaming the demo.

**Test** the Gateway's change request names every department whose rules ran, and applying is
refused until they have all answered.

## 35 · A decision holds more than one signature — **done 10 Sep**

**Files** `api/store.py`, `api/review.py` (`answer_decision`)

**Done when** answering as one desk records that desk's approval and leaves the decision
pending, the last outstanding desk applies it, and the same desk cannot sign twice.

**Note** **the table already exists.** `approvals` carries `decision_id`, `line_id`, `roles[]`,
`rule`, `user_email` and `rationale`. No migration; `decisions.state` becomes a function of the
approvals against it. The rule is **parallel and all-must-approve**, not sequential: sequential
review is the round trip this product exists to remove, and the published guidance is explicit
that first-response *"is unsafe when two independent controls or separation of duties are
required"*, which is exactly `part_qualification`. This closes the 🟡 open since 8 September.

**Test** a decision addressed to two desks stays pending after the first signature, applies on
the second, and one desk answering twice is refused. Rewrite
`test_a_decision_can_only_be_answered_once`, which currently asserts the behaviour being
replaced.

## 36 · Everyone can see what is waiting for them — **done 10 Sep**

**Files** `api/decisions.py` (new), `shell/SideRail.tsx`, a decisions surface

**Done when** signing in as any desk shows every decision addressed to it across every product
line, with enough context to answer without navigating, and one can be answered from there.

**Note** there is no such endpoint: `_pending_roles` and `_pending_question` in `app.py` belong
to the design graph and are thread-scoped. DEFERRED has carried *"nothing tells the desk that a
decision is waiting for it"* since 8 September. The frontend already receives the signed-in
user's roles on `PublicUser` (`lib/api.ts:26`) and no route uses them, so nothing on screen
ever says whose turn it is. Pairs with item 28: the same provider that raises the notification
carries **2 waiting on you**.

**Test** a decision addressed to production appears for the production account and not for the
engineer, and the engineer answering it is refused with the desk named.

## 37 · The presenter can be any desk without logging out — **done 10 Sep**

**Files** `shell/`, `api/auth.py`

**Done when** the demo can move between desks in one gesture, holding a real session per desk,
and a desk that may not answer is refused for real.

**Note** SCENARIO-B's unanswered question. The pattern is a **principal switcher** holding
several genuine sessions rather than one account viewing as another: a *view-as* simulation
cannot sign, and signing is the whole point. Every reference implementation found does it in
the header, with the current desk always visible. The multi-pane variant — the same decision
seen from every desk at once, including the desk with nothing to do — is the strongest single
frame for this scenario, because an empty pane is the most concrete evidence that the routing
is real rather than cosmetic. See [R11](RESEARCH-3rd-Passthrough.md#r11-showing-four-desks-and-demoing-them-with-one-presenter).

**Test** switching desks changes what `/auth/me` returns, and an answer submitted from the
wrong desk is still a 403.

## 38 · Three product lines, three desks — **done 10 Sep**

**Files** `tools/seed_world.py`, `profile.py`

**Done when** one notice produces three answers that stop in three different places.

**Note** **needs item 32 first, or it cannot work.** `availability` failing today does not route
to procurement, it discards the candidate. Once it is a gate, the two honest levers are a real
annual volume on one product line's operating profile — TLV1117LV33DCYR has 1,133 in stock at
JLCPCB, so a line shipping 5,000 a quarter fails it for a real reason — and `LD1117-3.3`, which
is already electrically fine and off the approved manufacturer list on all three boards.
Neither invents a failure. Both need a number he is happy to defend on stage.

**Test** the three lanes end at three different desks, and each names the rule that put it
there.

## 39 · The coordination that was removed, counted — **done 10 Sep**

**Files** `change.py`, `review/RequestCard.tsx`

**Done when** the change request states what was checked before anybody was asked: three
products, four candidates, every rule, four departments, in one pass.

**Note** the topic hands us the clock — *within 48 hours* — and no surface carries a time figure
of any kind. The honest number is not a fabricated saving, it is the count of round trips that
did not have to happen, and it is derivable from what already ran.

---

# Phase 6 · Presentation

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

Moved to [DEFERRED.md](DEFERRED.md), which is now the running list and carries a severity
against each item. These three stay here because they are answers to questions rather than
work items:

- The `/projects` retry loop has no backoff — one 401 became fifteen requests.
- Nothing configures logging, so application warnings reach production logs only through
  Python's last-resort handler, unformatted.
- Output-capacitor **stability** remains unassessed. Item 8 checks explicit violations of a
  stated requirement; proving stability needs simulation. Say so plainly when asked.

## Open with the organiser

Submission deadline for the finals work, pitch and Q&A length, what criterion 4.2 means by
"product features", venue network reachability, and booth requirements. See
[README.md](README.md).
