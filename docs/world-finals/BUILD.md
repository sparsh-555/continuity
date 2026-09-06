# Continuity 2.0 — build

Ordered work. Each item names the files it touches, what *done* means, and its own acceptance
test, so the test cannot drift away from the item it proves.

[SPEC.md](SPEC.md) is the contract. This is the sequence.

## The rule that governs all of it

**Nothing ships behind a label we could have built.** *Not assessed* is for work genuinely
outside scope. It is never cover for something skipped. A judge who finds a label hiding an
unbuilt feature asks about it first, and "we ran out of time" costs the room.

## Order, and why

Two dependencies drive it. The **operating profile** determines what every θJA claim and every
matrix cell means, so it comes before both. **Coverage semantics** determine what green means,
so they come before anything aggregates cells. Getting either wrong later is rework of
everything above it.

---

## 1 · Real fixture, real parts

Everything downstream quotes these numbers.

**Files** `backend/tools/eol_differential.py`

**Done when** the four parts carry specs sourced from JLCPCB through `graph.sourcing` — MPN,
manufacturer, package, voltage limits, current limits, temperature grade, stock, price — with
no value invented and no manufacturer's specification attached to another's listing.

**Test** the script reproduces the SPEC matrix: A passes for all candidates; B fails
NCP1117ST33 on thermal; C fails TLV1117LV33 on voltage; AMS1117-3.3 passes all three at its
worst published θJA.

---

## 2 · Operating profile

**Files** `backend/continuity/engine/models.py`, `engine/rules.py`, `api/store.py`

**Done when** `ambient_max_c` is a field of the profile and `temp_range` means component grade
only — today one object conflates them. Every thermal verdict cites which ambient it used and
where that number came from.

**Test** the same board evaluated at 25 °C and 70 °C ambient returns different verdicts, and
each verdict names its ambient. A board with no profile returns *evidence missing* for thermal
rather than silently assuming 25 °C.

---

## 3 · Coverage semantics

**Files** `engine/models.py` (the `Verdict` status), `engine/rules.py`, `api/events.py`,
`frontend/src/app/design/`

**Done when** every rule returns one of **satisfied / failed / not applicable / not assessed /
evidence missing**, and a cell is green only when every applicable check is satisfied.

**Test** a two-part board reports `interface_role_match` as *not applicable* rather than
passing; a part with no stated θJA reports *evidence missing* rather than falling back
silently; the UI shows the count of unassessed checks on a green cell.

---

## 4 · Two bug fixes

**Files** `backend/continuity/reviewer.py`, `engine/policy.py`

**Done when** the reviewer's system prompt no longer claims a larger linear regulator has the
same junction temperature — same power, different θJA, different temperature, and we are
currently misinforming the model. And the repair cap rejects at the boundary rather than
permitting a slot at `repair_count == 3`.

**Test** a unit test asserting the cap refuses a fourth repair; a reviewer prompt test that the
misleading sentence is gone.

---

## 5 · θJA from the datasheet

**Files** `backend/continuity/parts/datasheet.py`, `parts/normalize.py`, `engine/rules.py`

**Done when** θJA comes from the PDF with its quoted line **and its mounting condition**, the
extraction binds the value to the correct table column rather than only checking a quote
appears somewhere, and the cache is keyed by document identity rather than by MPN — today a
cached result can shadow a newly uploaded datasheet, which is a live demo hazard.

**Test** each of the four datasheets yields the right θJA with the right quoted line; uploading
a different datasheet for the same MPN returns the new value, not the cached one.

---

## 6 · Product lines

**Files** `api/projects.py`, `api/store.py`, `frontend/src/app/routes/`

**Done when** a product line holds a BOM, an operating profile and a revision, and the five
demo lines exist with three carrying AMS1117-3.3.

**Test** exposure matching returns exactly the three affected lines from an MPN.

---

## 7 · Fan-out and the matrix

**Files** new orchestration module, `api/app.py`, `frontend/src/app/design/`

**Done when** one candidate is evaluated against N boards with results that keep their board
and candidate identity through evaluation, repair and reconnect — a repair changes the
candidate, so a result must not silently stay in the original candidate's row.

**Test** the demo case produces the full matrix with every cell attributable to a board, a
candidate and an owning department.

---

## 8 · AML, AVL and the two gates

**Files** policy layer, `graph/nodes.py`, `api/app.py`, `api/store.py`

**Done when** AML and AVL are separate lists; an unqualified MPN routes to engineering and
quality; a qualified part from an unapproved source routes to procurement; and an approval
records **identity, timestamp, the rule that fired, and a rationale**, scoped to the candidate
and revision it was granted for.

**Test** an approval granted for one candidate does not carry over to a later one — accepted
exceptions are keyed by rule and slot today, so a waiver can be inherited. The gate fires on an
unqualified part that has **no** electrical failure, since approval cannot depend on failure.

---

## 9 · Mailbox connector, both directions

**Files** new module, `api/app.py`

**Done when** an unread message with a PDF attachment starts a run, and a gate sends a real
approval request naming the decision, the evidence and the requester. A POST endpoint accepts
the same PDF so the demo never depends on mail delivery.

**Test** a PCN sent to the mailbox starts a run within one poll; a gate produces a real
delivered email; the POST path produces an identical run.

---

## 10 · Footprint compatibility, for real

**Files** `engine/rules.py`, footprint data

**Done when** the rule compares land pattern and pin function rather than a package-size
ceiling, and reports *not assessed* only where a mapping genuinely is not available.

**Test** SOT-223 to SOT-223 reports compatible; SOT-223 to SOT-23-5 reports incompatible for
land pattern; a part with an extra pin function reports the unmapped pin rather than passing.

---

## 11 · The change request

**Files** new module, frontend

**Done when** each affected line yields a request carrying baseline and revision, the notice
that triggered it, the proposal with alternatives rejected and why, the evidence, **what was
not assessed**, cost separated into recurring and one-time, and the approvals required.

**Test** the three demo lines produce three requests; each names its unassessed checks
explicitly.

---

## 12 · KiCad

**Files** new module

**Done when** a project bundle yields a BOM through `kicad-cli` and the board renders with the
footprint consequence of the chosen substitute.

**Note** pin the KiCad version. `pcbnew`'s SWIG bindings run headless but are deprecated from
KiCad 9 with removal planned for 11; the replacement IPC API needs a running GUI until 11.
`kicad-cli` SVG export is the dependable path for before-and-after evidence.

**Test** a known project yields the expected BOM rows and a rendered board.

---

## What each item earns

| # | Claim it makes true |
|---|---|
| 1 | Every number on stage is quotable |
| 2 | The answer is board-specific, which is the whole thesis |
| 3 | Green means something, and gaps are visible rather than hidden |
| 4 | We stop misinforming the model |
| 5 | θJA is cited, not guessed |
| 6 | "Three of your five lines" is computed |
| 7 | One substitute, opposite verdicts — shown, not asserted |
| 8 | Cross-team coordination with real authority and a real record |
| 9 | The system reaches outside itself |
| 10 | "Production confirms assembly compatibility", from the brief |
| 11 | An approver sees what they need, including what we did not check |
| 12 | Onboarding from a file engineers already have |
