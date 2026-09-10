# FLOW.md — what runs, and what happens on the day

Two parts, and they answer different questions.

**Part one · The machine** is what actually executes when a notice arrives: every stage, who
decides it, the file that does it, and where a model is and is not involved. It is written to
be *checkable* — if a stage here does not match the code, one of the two is wrong and it is
worth finding out which.

**Part two · The demo** is the beat, in the order it is told, with what is on screen and what
would be a bug.

[RUNNER.md](RUNNER.md) is the run-through, [DEMO-DAY.md](DEMO-DAY.md) is what you say over it,
and [OPERATING.md](OPERATING.md) is how to start everything and what breaks. [BUILD.md](BUILD.md)
is the work and its order. This is what the thing does.

Anything below marked **[not built]** does not exist yet and is named as a gap rather than
described as behaviour.

---

# Before anything else

**Continuity's entire pitch is that it checks parts. A surface that says it could not check
one destroys that claim in seconds.** A failure to check is a bug to fix, not a state to
render: a shipping product line must be checkable with no distributor reachable, and it is.
Coverage honesty belongs in the change request, where somebody is deciding whether to sign,
never on a page a person looks at for five seconds. See BUILD.md, "The second rule, learned
the hard way on 9 Sep", for what shipping the caption instead cost.

---

# Part one · The machine

## Where a model is, and where one is not

The claim this product rests on is that **no compatibility verdict is produced by a model**.
That is about who *executes the check*, and it is checkable: here is every model call in the
codebase, and which of them the end-of-life flow reaches.

| # | What the model does | Where | In the EOL flow? |
|---|---|---|---|
| 1 | Reads a change notice into declared fields, each quoted from the document | `notices.py:212` | **yes** |
| 2 | Turns a distributor's payload into the engine's declared fields | `parts/normalize.py:411` | **yes** |
| 3 | Reads θJA and a junction limit out of a datasheet, bound to the table column | `parts/datasheet.py:273` | **yes** |
| 4 | Judges whether a search hit is the right *kind* of part | `interpret.py:197` | no — needs `purpose`, which only a design run passes |
| 5 | Classifies a free-text answer to a supply question | `interpret.py:86` | no |
| 6 | Classifies an answer to an escalation as accept / stop / redirect | `interpret.py:112` | no |
| 7 | Turns a brief into requirements | `api/bom.py:146` | no — BOM-validation path |
| 8 | Infers a power tree from a pasted parts list | `api/bom.py:232` | no — BOM-validation path |
| 9 | Plans a board from a brief | `planner/plan.py:491` | no — design runs |
| 10 | Chooses which repair to try | `reviewer.py:332` | no — design runs |

**Three, and all three are readers.** Every one produces *claims about a document*, and every
one is verified before it is believed: the notice's fields must be quoted from lines that are
in the notice, the datasheet's θJA must sit in the column the document prints it in, and
normalisation may only fill fields the engine declares. None of them decides whether a part
fits a board.

The verdicts come from `engine/rules.py`, which is deterministic and takes no model.

## 0 · What a company has before anything happens

| Thing | Where it lives | Who wrote it |
|---|---|---|
| Product lines, each with a revision | `product_lines` | the engineer |
| A bill of materials per line, by reference designator | `line_parts` | uploaded, or read out of a KiCad schematic |
| An operating profile per line — ambient, mounting, rails with `source`, `members`, `i_load`, and the two quantities the money rests on: `build_quantity` for the stock minimum and `annual_volume` for the recurring cost, each with a stated source | `product_lines.profile` | the engineer |
| The approved manufacturer list and approved vendor list | `approved_parts`, `approved_vendors` | quality and procurement |
| Verified part facts — datasheet readings that outrank a distributor's table | `part_facts` | whoever read the datasheet; today the seed |
| A KiCad project per line | `line_boards` | the engineer |
| What was ruled out before, per board | `precedents` | earlier reviews |

**`None` and an empty list are different things.** An organisation that keeps no approved
list has `None` and the qualification rule reports *not applicable*; one that keeps a list
approving nobody rejects everybody. That distinction cannot be derived from an empty table,
so `organisations.keeps_aml` and `keeps_avl` record it.

## 1 · A notice arrives

**Two ways in, and they meet at the same reader.** A mailbox is polled every fifteen seconds
by `mail.py`, started from the app's lifespan when `CONTINUITY_MAIL_*` is set; and a PDF can
be uploaded through `POST /notices`, which is the fallback and stays unchanged.

The mail half keeps its read position as a stored UID with the folder's `UIDVALIDITY`, not as
the `\Seen` flag, so that opening the mailbox in a browser does not make the poller skip the
message. Attachments are tried before the body. A message that holds no notice is left alone:
nothing stored, nothing deleted, nothing guessed at.

`notices.py` asks the model for `{reference, mpn, manufacturer, effective_date,
replacement_mpn, reason}` **and the exact line of the document each was read from**. That ask is recorded and
replayed like every distributor call, keyed on a digest of the extracted text and a
fingerprint of the instructions — so a reworded prompt re-reads rather than believing an
answer to a question it did not ask, and a document nobody has recorded is refused rather than
fetched. The checks below run on a replayed answer exactly as on a live one: a recording is
the model's answer, not a licence to believe it. Then code checks:

- every quoted line appears in the extracted text,
- the part number appears *in the line quoted for it* — otherwise a model can cite any true
  sentence and hang any part number on it,
- the date is ISO-shaped and is the one that ends *ordering*, not the issue date, the
  response-by date or the last time ship,
- a word a notice uses for absence — `none`, `to be advised` — is not a part number.
- the reference number appears *in the line quoted for it*, the same rule the replacement part
  number lives under. It labels a notice in the list, so one hung off a line that does not carry
  it is a citation that sources nothing — and on screen it is indistinguishable from a real one.

The same notice arriving twice is one notice. `save_notice` returns the id it already holds
for this company's `(mpn, effective_date, replacement_mpn)`, so a PCN forwarded to the mailbox
and uploaded through the page is one change to act on — while the preliminary `PCN-2026-118`
and the full `PCN-2026-114`, which name the same part and say different things, stay two.

A notice whose MPN cannot be sourced from its own text is refused outright, because every
step after this keys off that part number.

## 2 · Exposure

`store.lines_exposed_to(org, mpn)` — one indexed query against `line_parts`, no model, no
distributor. *"This reaches three of the five products you ship, at U1 on each."*

This step is commodity: SiliconExpert, Z2Data and PCNshark all match a notice to a bill. It
is not the differentiator and the pitch should not claim it is.

## 3 · Candidates — where a replacement comes from

`review.candidates_for`, in this order, and each candidate carries **why it is on the list**:

1. **The manufacturer's own recommendation**, from the notice. First because it is the answer
   everybody in the room already has, and on a board it does not suit, watching it fail is
   the point.
2. **What already resolved this retirement somewhere in the company**, from
   `store.worked_anywhere` under the signature `eol|{retiring}`. The signature carries no
   reference designator on purpose: an end-of-life conflict is about the part, and the demo's
   three boards carry it at U3, U1 and U2, so a refdes-scoped signature could never match
   across lines. A part that already resolved this is the cheapest answer the company owns,
   and it says so — *resolved this on the Sensor node*. The beat lands on the **second**
   notice about a retirement, because the first has no precedent to read.
3. **The approved manufacturer list**, filtered to the same category. The cheap resolution:
   roughly **$1,281** against **$15,656** to qualify a part from scratch.
4. **The distributor's catalogue**, searched in the same package. This is the only leg that
   can produce a part nobody here has ever bought, and therefore the only one that can
   produce a decision that belongs to quality rather than to engineering.
5. **Anything a person typed**, last, as an override. Nobody should have to.

Minus **what this board already ruled out** (`precedents`, scoped to the line: a part that
cooks one product says nothing about a cooler one).

**What could not be considered is said and stored.** A candidate that reached `consider` and
resolved to nothing, or came back ambiguous, is named in the run's preamble with the sentence
that stopped it and written to `notices.review_skipped` — so the NOT CHECKED panel survives a
reload rather than living in component state. A catalogue hit the search itself filtered out is
the search shaping its shortlist, not a skip, and stays out of this.

**Every one of them is asked for by number and manufacturer**, from `store.recorded_manufacturers`
— this company's own bills first, then its approved list. An MPN alone does not name a part:
JLCPCB lists `TLV1117LV33DCYR` under Texas Instruments and under JSMSEMI, whose listing states
a 12 V supply ceiling where TI's states 5.5 V, and only TI's fails the 12 V cabinet
controller. Asking by number took whichever listing came back first. The same record answers
`/matrix` and the notice-driven matrix, and `search.live_stock` carries the manufacturer too,
so a stock figure belongs to the part in hand rather than to another company's listing of the
same number.

Four things the catalogue leg had to learn, each measured against JLCPCB:

- The query is built from the rail and the family — *"3.3V LDO regulator"* — never from the
  part's own description, which is a parametric blob and returns the part itself.
- The pool is 25 deep, because the top of the list is four listings of the retired part and
  the real alternatives start at the seventh hit. Hits are normalised **a batch at a time and
  concurrently**, in pool order, stopping as soon as the limit is met — it used to walk all 25
  sequentially, which was measured at 52 s one day and unfinished after 140 the next. Order is
  preserved, so the candidate set under replay is unchanged.
- The search is filtered by the retiring part's own input voltage, so a regulator that cannot
  take this board's rail is not offered as a substitute for it.
- Another manufacturer's listing of the retired part number is filtered out before it is
  normalised: it is the part that is going away.
- A fixed regulator with a different output is not a substitute for this position.

## 4 · The board each product line is checked as

`profile.board_from(profile, bom, specs)` builds an engine `Board` out of stored data: slots
from the bill, rails from the profile, ambient and mounting from the profile.

Every part is resolved through the distributor **with the manufacturer its own bill records**.
Resolving by part number alone is ambiguous — three manufacturers list AMS1117-3.3 — and
asking without it has broken two features in this project.

The company's **verified part facts are installed for the whole run**
(`normalize.set_dossier_lookup`). Without them every SOT-223 part falls back to one figure
from the package table and NCP1117 has no junction limit at all, so it clears every board —
including the one where it runs 159 °C against onsemi's 150 °C.

## 5 · The substitution run

`review.attempt(board, slot, candidate)` — put the candidate where the retired part sits and
re-check the **whole board**, not the slot. A regulator moves the rail it makes, and a check
scoped to one position would clear a part that browns out everything downstream.

Seventeen rules run on every board, every time:

`voltage_overlap` · `interface_role_match` · `pin_budget` · `current_budget` ·
`thermal_dissipation` · `availability` · `part_qualification` · `source_approval` ·
`footprint` · `footprint_compatibility` · `capacitor_requirements` · `temperature_rating` ·
`energy_budget` · `rail_coverage` · `output_capacitor_stability` · `emc` ·
`signal_integrity`

Each of the last three stacks published figures rather than asserting anything: the stability
condition each regulator states, the regulation type of each part, and a regulator's output
accuracy plus its load regulation against every load's supply window. Those figures are
**hand-read datasheet values recorded as dossier facts**, so they survive the company's own
record — which is exactly what three of them did not do on the first pass, and why a rule can
test green against fixtures while declining in the product.

**The last three were an admission until 11 September.** A fifteenth entry in `RULES` called
`not_assessed` checked nothing and declared the three questions this engine did not answer for
any board, so that an approver had an honest denominator. Sparsh overruled keeping it: either
the three check something real or every mention goes. They are real now — the published
stability condition per regulator, the regulation type of the candidate against the part it
replaces, and the rail's worst published deviation against every load's supply window — and
the `not_assessed` label is deleted from the vocabulary. All three are satisfied on the demo
world, so none of them takes over the story the other fourteen tell.

Each returns one of four coverage labels — `satisfied`, `failed`, `not_applicable`,
`evidence_missing`. Margin is an attribute of *satisfied*; acceptance is an attribute of
*failed*. There is no fifth label and no verdict without one.

The three product lines run **concurrently on one stream** (`api/review.py`). One stream
because browsers cap around six connections per origin and three sequence spaces would race,
and the client drops anything at or below its high-water mark.

**One review, two surfaces.** `POST /notices/{id}/review/run` takes an optional `line_id`,
and that is the only difference between the two places a review is started from: `/changes`
asks the question about the whole company, and a product line page asks it about itself.
Same endpoint, same engine, same frames, so a review cannot come to mean one thing on one
screen and something else on another.

## 6 · Who is asked

Every candidate lands in one of three states, and this is the routing the whole scenario is
about:

| State | Means | Who signs |
|---|---|---|
| **clear** | nothing failed | engineering — a released design is approved before it changes, never after |
| **gated** | the only failures are rules a department owns | five rules, in `roles.ANSWERABLE_RULES`: qualification to engineering and quality, source approval and availability to procurement, both footprint rules to production |
| **blocked** | something physical failed | nobody. No signature turns 159 °C into 150 °C |

A clear candidate is preferred over a gated one, because an approved part costs a twelfth of
a qualification. Within a state, the discovery order above decides.

The question carries the roles that may answer it, and a `decisions` row records it —
proposal, gate rule, roles, and **the whole run as evidence**. Nothing is suspended: by the
time a person is asked the work is finished, so the answer can arrive tomorrow, from another
browser, from somebody who never watched it.

## 7 · The decision

`POST /decisions/{id}`, and the authorisation is at the HTTP boundary: a decision addressed to
a desk the answerer does not sit at is refused with a 403 naming what they hold, before anything is
written.

Approving does five things in one request, and they are the difference between a
recommendation and a change:

- the substitute is written into `line_parts` at the reference designator it replaces,
- the revision moves,
- the approval is recorded against the person, with the rule and the rationale,
- a **successful** precedent is written against the conflict's signature,
- and the product line's own page shows the new part in its power tree, its bill and its
  board.

The part applied comes out of the run's own record rather than being resolved again, because
resolving by MPN alone is ambiguous — three manufacturers list AMS1117-3.3 — and that is how
the first applied substitution landed on a bill with no manufacturer.

Declining writes the refusal and leaves the board carrying the retired part, which is a real
answer and is remembered as one.

**An approved decision that carried a gate rule is a waiver, and a waiver is not a pass.**
`store.accepted_waivers_for_line` reads it back as `(rule, subject, mpn, revision, roles)` from
the approval the owning desk signed, and `review.accepted_verdicts` marks the matching failure
`accepted` without touching its status, its detail or its evidence. `rules.blocking` stops
routing it and every screen keeps reporting it — so the released revision says *failed and
accepted* with the arithmetic under it, and the next change to touch that board does not put
the same shortfall to the same desk again. It is scoped to the rule, the slot, the candidate,
the revision and the desk that owns the rule; change any one of those and the failure blocks
as it did before.

## 7a · What is on the bill, and why it is three parts

Asked on 9 Sep after a real board was attached and its forty-one rows were briefly imported.
Writing it down because it is easy to re-derive wrongly.

**A product line's bill is the regulator, the load, and the output capacitor.** That is not a
limitation, it is the exact set an LDO substitution depends on: the part being replaced, the
load that sets its current, and the capacitor that sets its stability. `SPEC.md` specifies the
third one deliberately — `capacitor_requirements` is *"the first thing a hardware engineer
attacks on an LDO substitution"*, because the four regulator datasheets disagree. AMS1117 asks
for 22 µF solid tantalum, TLV1117LV requires 1.0 µF ceramic X5R or X7R and is stable with no
ESR, and the other two characterise at 10 µF.

**Nothing else on a real board is affected by swapping a regulator.** The decoupling around an
MCU sits on the same rail without being part of the regulator's operating conditions. Importing
it puts thirty-eight parts in front of rules that each report evidence missing, which is scope
creep wearing honesty as a costume. The Singapore proposal drew this boundary first: *"the
boundary is drawn at block-level validation … synthesis requires pin-level connectivity, a
substantially larger data problem."*

**The passives are checked, by the tool that is authoritative about them.** The board
consequence runs KiCad's own design rule check before and after, and DRC looks at clearances
and connections against every object on the board. So the split is: **we check the three parts
the electrical substitution depends on, and KiCad checks the whole board for what a new
footprint does to it.** Neither side guesses, and neither claims the other's ground.

**A board therefore never needs its bill imported.** `api/boards._consequence` reads the
board's own bill out of the file when it runs, so the project is self-describing and the two
records are about different things at different levels of detail.

## 8 · The board consequence

`continuity/kicad/` — for a product line with a KiCad project attached, the substitute is
placed where the retired part sits, its nets carried pad by pad **by function**, and the same
design rule check runs before and after. KiCad answers; we report the difference.

This is production's leg of the scenario: same package is a substitution, different package
is a board revision. On the verification board a SOT-223 drop-in adds nothing and a SOT-23-5
takes unconnected items from 1 to 4 with four shorting items behind it.

Pinouts come from `kicad/catalogue.py`, a table of datasheet readings. A part not in it gets
no board consequence and says so — LD1117 is absent because ST publishes its pin connections
as a figure, and a figure is not extractable text.

**The screen keeps what it was given.** A placement is remembered for the session, keyed on
the product line, the retired part and the candidate, so toggling away from BOARD and back
paints the picture rather than starting KiCad again — which used to take the board away and
put **PLACING…** in its place whenever anything behind the page refetched.

## 9 · What is remembered

All of it is read back on `/memory`, assembled by `api/recall.compose` from `line_parts`, the
notices, the precedents, the approvals and the open decisions. It used to read `threads` only,
so a company that had never run a design here had no memory at all.

- **Rejections**, scoped to the board they happened on, so the next notice does not
  re-litigate them.
- **Change requests** — the ECR packet: proposal, every rejection with the sentence that
  killed it, evidence, what could not be checked, the cost split, and the desks that must
  sign.
- **Approvals** — identity, timestamp, rule, rationale, and the line they were given on.
  Shown on `/memory` under the part they were about.
- **Successes**, written the moment a substitution is approved rather than proposed. Not
  scoped to a board, and the asymmetry is the point: a rejection is about the board it
  happened on, and a part already qualified somewhere in the company is the cheap answer on
  the next product.

**A retired part looks retired on the graph**, without being clicked: a duller, desaturated
fill and a heavier ring rather than the pale outline it used to wear, the lifecycle word under
the part number so the colour is never the only carrier, and warm dashed edges to the boards
that still carry it — which is a different statement from the grey dashed edge that means
*was here and was replaced*. `routes/memoryGraph.ts` holds those decisions and the canvas only
draws them.

---

# Part two · The demo

Five products, one company, one notice. [RUNNER.md](RUNNER.md) has the run-through and
[OPERATING.md](OPERATING.md) has the commands; this is the story. Timings are from live runs on the seeded world.

## Before you start

Seeded and signed in as the engineer, sitting on `/lines`. The KiCad project attached to one
product line. The notice PDF ready to drop in.

## 1 · This is what the company ships

`/lines`. Five products, each with a revision, a part count, an ambient and a status. Open
one: its power tree, its bill of materials, the board it is built from. *This is a product
line, not a design run — Continuity knows what this company ships and under what conditions.*

Say how a product line gets here: **NEW PRODUCT LINE** takes a brief, or a KiCad project is
attached and its bill is read out of the schematic.

## 2 · The problem, before the tool

An end-of-life notice arrives with a last-order date. Somewhere in the company, three
products carry that part and nobody yet knows which. The cross-team response is a sequence of
round trips — design proposes, procurement replies on stock, production objects on footprint
— and each leg is a day or two of email. That is where the 48 hours in the brief goes.

## 3 · The notice arrives

Drop `PCN-2026-114.pdf` in. Continuity reads it, and shows the line it read the part number
from. **Reaches 3 of the 5 products you ship.**

Point at the date: four dates on that page and only one ends ordering.

## 4 · All three products at once

**START THE REVIEW.** Three columns, running together, about a minute:

- the manufacturer's recommendation tried first, on every board,
- then the approved list, then the catalogue — each candidate saying where it came from,
- each board's own conditions applied to each candidate.

**What comes back does not agree**, and that is the point:

| Product | Answer | Why the obvious one lost |
|---|---|---|
| **Gateway** | TLV1117, 35 °C to spare | NCP1117 → *159 °C junction against a 150 °C limit* |
| **Cabinet controller** | NCP1117, 11 °C to spare | TLV1117 → *rated to 5.5 V, vin at 12 V is above that* |
| **Sensor node** | NCP1117, 84 °C to spare | — |

Two answers, three products, and the rejections are different physics on each. A single
manufacturer-wide recommendation cannot express this, and neither can a parametric search.

The same run is on each product's own page under **REVIEW THIS LINE**, where the trace sits
beside that board's power tree and a toggle swaps it for the board itself, before and after.
Which one to open is a question about who is watching: the company view for the beat above,
the product view for one board somebody wants to go deep on.

## 5 · The decision that is not yours

Each column ends with a question addressed to a desk. Where a part is electrically perfect
and not on the approved list, that desk is **quality**, not engineering — the tool routes,
it does not decide. Signing in as the second account to answer it is a stronger beat than
approving it yourself.

**Built 10 Sep, Phase 8.** Every column used to end at engineering, because `review.choose`
hardcoded it for any candidate that cleared and the product had no production role at all.
Now every department that examined a change signs it, in any order, and the bill does not
move until the last signature. The Gateway stops at **procurement** on a stock shortfall
while the other two clear, so one notice produces answers that halt in different places.

Once the Gateway has all four signatures, its released Rev D says **failed and accepted** at
U1 rather than passing or failing: the shortfall is still true, procurement signed for it, and
the screen says both. That is the answer to *what happens to a failure somebody accepted*, and
it is why the same shortfall is not put to procurement again when the next change touches that
board.

**Watch for:** the quality gate still does not fire in the seeded world, because no line's
best answer is off the approved manufacturer list. That row is still open in DEFERRED.

## 6 · What it costs the board

Open the product line: the substitute placed on the real KiCad board, before and after, and
the connections it breaks reported by KiCad's own design rule check. Same package is a
substitution; a different one is a layout revision, and that inverts which part is cheap.

## 7 · The packet

One change request per product line: proposal, every rejection with the sentence that killed
it, evidence with its arithmetic, what could not be checked, the cost split, and who has to
sign. Continuity drafts the ECR. The board decides.

## 8 · The number

$1,281 to resolve with a part already approved, $15,656 to qualify one from scratch, and
three products triaged in a minute against days of round trips.

## If something fails on stage

- **The network.** `CONTINUITY_FIXTURES=1` replays every distributor call. The one step with
  no offline path is reading the notice, so receive it while you have a connection.
- **A column stalls.** The other two are unaffected — each product line is its own task and
  one failing emits an error on that column alone.
- **KiCad.** Needs Docker; without it the board section says so rather than guessing.

---

# The original design record, 6 Sep

Kept for the reasoning. Where it disagrees with Part one, Part one is what the code does.

**What was decided then and still holds:** the entry is an event rather than a brief; the
engine is untouched and fanned out across candidate × board; escalation gains an owner;
one screen with attribution rather than three role dashboards; decisions classify into the
industry's own buckets.

**What changed in the building:**

- *"A policy layer runs parallel to `RULES`, not inside it."* The approved lists became
  **engine rules** — `part_qualification` and `source_approval` — because a gate that fires
  on a part with nothing electrically wrong has to produce a verdict shaped like every other
  verdict. There is no parallel layer.
- *"Ten rules."* Fifteen.
- *"Pass / marginal / fail."* Four coverage labels, with margin as an attribute of satisfied.
- *"Sensor Node and Gateway take ME6211 at $0.0597."* ME6211 is not a candidate in the built
  demo: its datasheet gives 6.5 V absolute maximum, which rules it out on the 12 V product,
  and it was never made a sourced part. The SOT-23-5 beat lives in the KiCad tests instead.
- *"Display Unit."* The five products are Sensor node, Gateway, Cabinet controller, Bench
  supply and Handheld meter.

**The differential that settled the scenario**, from `tools/eol_differential.py`, is still
the argument in miniature: no single part solves all three boards, and the reasons are
different rules — one candidate fails on thermal where another fails on voltage.
