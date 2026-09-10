# Task · DEFERRED pass 2 — the coverage admissions, the replay, and the board in the document

**Repository** `~/Documents/GitHub/continuity`. **Baseline** main at `7b2af45`, working tree
clean. **Suite** 942 offline · 1150 with a database · 1162 with KiCad, ~170 s · 24 frontend
tests · 619 fixtures (re-count before quoting any of these).

The rules that govern this work are the ones in [`DEFERRED-BRIEF.md`](DEFERRED-BRIEF.md) and
the top of [`BUILD.md`](../BUILD.md): nothing behind a label we could have built; a failure
to check is a bug to fix, not a state to render; coverage honesty belongs in the change
request, never on a page seen for five seconds. Test first, watch it fail, fix, watch it
pass, **revert the fix and confirm the test fails again**. Measure before and after anything
about speed. One commit per item, `type: description`, no scope, the attribution lines from
`git log`. When an item is done its row moves to *Resolved here* with what fixed it and what
it exposed, and the header counts are re-counted by counting.

## Decisions taken with Sparsh, 11 Sep

1. **The three never-checked rules are built, not disclosed.** (Supersedes the morning
   decision, which kept the admissions and moved them off the trace.) `emc`,
   `output_capacitor_stability` and `signal_integrity` become real engine checks; the
   `not_assessed` concept is deleted everywhere. **The new rules must not take over the
   demo's existing narrative beats** — all three are green on the demo world with
   datasheet-quoted arithmetic, and the 159 °C / TLV1117 / NCP-on-the-cool-lines story is
   preserved exactly. AMS's tantalum sentence reads as a characterization, not a
   requirement (satisfied on value); the rules sit after `capacitor_requirements` in
   evaluation order; the Samsung capacitor publishes no ESR anywhere (searched 11 Sep), so
   the stability comparison is violation-only on what each manufacturer does publish.
2. **The board consequence is stored, asynchronously.** The review fires each line's KiCad
   consequence when its proposal is chosen; it lands on the stored document seconds later
   while the question waits on desks. Cards render the picture from storage, no button, and
   the 0.25 s replay headline survives.
3. **A worked precedent's signature drops the refdes.** `eol|{retiring}` — an end-of-life
   conflict is about the part, not the designator, and the demo's boards carry the part at
   U3, U1 and U2, so the refdes-scoped signature could never match across lines. Rejections
   stay scoped to the board they were measured on.
4. **All three affected lines state an annual volume** on the operating profile (numbers
   below, drafted for veto).
5. **Voltage minimums: published where published, derived where derivable, sourced either
   way.** TI's 2 V is quoted; the capacitor records −25 V as a non-polarized part whose
   rating is symmetric; the three LDOs that publish no minimum record `Vout + dropout` with
   the derivation named in the source line, never dressed up as a quotation.

One incident to carry forward: while scoping P1, a broad `grep '^DATABASE_URL\|^CONTINUITY'`
over `backend/.env` printed the model key, the Neon password and the mailbox password into
the session transcript. All three need rotating; the sweep was the exact anti-pattern
`common/security.md` names. The .env change in P1 is the hazard removal, not the remediation
— rotation is.

## Order

P1 first because it removes a hazard rather than a defect. P2 and P3 change what the demo's
documents say and must land before P6, which replays those documents — the replay has to
agree with the live run from the first commit. P7 and P8 are the two biggest and touch the
most, so they come after the review path is settled. P9 and P10 are small and independent.
P11 is stretch: take it only if the rest is green and the evening is long.

Files shared between items — `api/review.py` (P3, P4, P5, P6, P8), `ReviewLanes.tsx` (P2,
P6), `RequestCard.tsx` (P2, P8) — mean these are serialized commits from one pair of hands,
not parallel agents. The plan is one pass, not one diff.

---

## P1 · `backend/.env` names a local database

**Row** (live 🟡): a local run started without an override writes real rows to production
Neon.

**Why it is safe to change.** `.env` is gitignored; the deployed instance gets its
`DATABASE_URL` from the platform, and `env.load` deliberately lets an injected variable win
over a stale `.env`. The only reader of the Neon URL in that file is a developer who forgot
to name a database on the command line — exactly the habit the row wants gone.

1. `backend/.env`: `DATABASE_URL=postgresql:///continuity_demo`.
2. `backend/.env.example`: add a `DATABASE_URL=postgresql:///continuity_demo` line with the
   one-line reason (production is named explicitly, never defaulted to).
3. `OPERATING.md`'s environment section gains the same sentence.

**Done** = a bare `cd backend && ../.venv/bin/python -c "from continuity import env; ..."`
started with no override resolves to the local database; `demo.sh` behaviour unchanged (it
already names the database everywhere). No commit can carry the local file — the DEFERRED
row closes on the example and the doc, and the row says so.

## P2 · The three never-checked rules are built (R5, superseded 11 Sep evening)

**Row** (live 🟡 + the ⚪ beneath it): the three not-assessed rules are paragraph-length on
the trace and lead the collapsed lane; `Could not be checked: voltage overlap` reads
identical to them.

**The decision that changed this item.** The morning plan kept the admissions and moved
them around. Sparsh overruled it: *either the three rules check something real or every
mention goes — no "we didn't check this" anywhere, and the new rules must not take over the
demo's existing narrative beats.* So the rules get built, and the demo's story — NCP1117
proposed on the cool lines, rejected at 159 °C on the Gateway, TLV1117 the Gateway's answer
— is preserved exactly. All three rules are **green on the demo world** with
datasheet-quoted arithmetic and margins; their teeth are real and unit-tested.

### 2a · `output_capacitor_stability` — the published stability condition, per regulator

Sits beside `capacitor_requirements` in RULES (after it, so a multi-failure candidate still
leads with thermal — the Gateway keeps 159 °C). Violation-only, the same discipline its
sibling follows: a failure needs published numbers on both sides. The Samsung
CL31A226KAHNNNE publishes **no ESR anywhere** (Samsung's spec, Samsung's product page,
LCSC, DigiKey, Mouser and the aggregators all checked on 11 Sep; the only ESR-adjacent
figure is DF ≤ 0.1 at 120 Hz, which cannot be compared against a loop-frequency window
without the frequency mismatch this codebase refuses), so the comparison rests on what each
manufacturer does publish:

| Part | Published condition | Source | Verdict on the demo board |
|---|---|---|---|
| TLV1117LV33DCYR | "internally compensated to be stable with 0-Ω ESR"; >0.5 µF effective | TI SBVS160C §8.2.2.1 | satisfied — inside by design; 22 µF against the 0.5 µF effective minimum |
| NCP1117ST33T3G | Cout ≥ 4.7 µF, ESR within 33 mΩ (typ)–2.2 Ω required; ceramic permitted within the limits | onsemi NCP1117/D, Output Capacitor | satisfied — 22 µF fitted, 17.3 µF above the minimum; ceramic permitted; the ESR window is quoted in the verdict |
| LD1117S33TR | "Only a very common 10 µF minimum capacitor is needed for stability" | ST LD1117 front page | satisfied — 22 µF against the 10 µF minimum |
| AMS1117-3.3 | "22 µF solid tantalum will ensure stability for all operating conditions" — a characterization, not a requirement | AMS DS1117 | satisfied on the published value — 22 µF fitted |

Failure branches (unit-tested with constructed parts): a capacitor that **publishes** an ESR
outside a published window fails with both numbers quoted; a rail below a published
stability minimum fails; a regulator whose datasheet states Cout is mandatory, with no
output capacitor fitted on the rail, fails. New fields: `esr_stable_from_ohms`,
`esr_stable_to_ohms`, `esr_source_line` on regulators; `esr_ohms` on capacitors (None on
both demo caps — the field exists so the comparison runs where manufacturers publish it).

### 2b · `emc` — does the substitution change the board's emissions character?

Compares the candidate's regulation (linear/switching, from each part's published topology,
already in the model) against the part it replaces (`slot.baseline`, which `substitute()`
already records). Both linear → satisfied with the physics stated; a switching substitute
for a linear part (or the reverse) → failed. Every candidate in the demo is an LDO, so this
is green everywhere — a real check with a real failure branch, not a label.

### 2c · `signal_integrity` — the rail's worst published deviation vs the loads' windows

Per rail with a regulator source: stack the regulator's published output accuracy and load
regulation, and check the rail stays inside every load's published supply window
(ESP32-C3 and WROOM-32E 3.0–3.6 V; STM32F103 2.0–3.6 V — all already sourced). Real mV
margins in every satisfied verdict; a stack that exits a window fails. TI's 1.5% and ST's
±1% are verified from the front pages; the remaining accuracy/load-regulation figures get
read from the four datasheets' electrical characteristics with the same discipline as the
vmin readings. New fields: `vout_accuracy_pct`, `load_regulation_pct`, each with its source
line.

### 2d · The voltage minimums, sourced (unchanged from the morning plan)

`tools/eol_differential.py` gains `vmin` on five parts, `PARTS.md` documents each reading,
and the seed writes them as verified facts (it already does, via `EVERY_PART`):

| Part | vmin | Source line |
|---|---|---|
| TLV1117LV33DCYR | 2.0 | TI SBVS160C §6.1, recommended operating conditions: VIN 2 V to 5.5 V |
| CL31A226KAHNNNE | −25.0 | Rated 25 V, non-polarized — the rating applies to either polarity |
| AMS1117-3.3 | 4.4 | VO 3.3 V, dropout 1.1 V @ 800 mA — regulating needs VIN ≥ VO + dropout; no minimum is published |
| LD1117S33TR | 4.4 | ST DocID2572 Rev 38: VO 3.3 V, dropout 1.1 V @ 800 mA — derived as above |
| NCP1117ST33T3G | 4.5 | onsemi NCP1117/D: VO 3.3 V, dropout 1.2 V @ 800 mA — derived as above |

The derived three say so in their source line — a judge reading the evidence row sees the
reasoning, not a number pretending to be quoted. Expected effect, to be verified on the
rebuilt world: `no_evidence` is empty on all three requests and the amber
*publishes no minimum* lines are gone from every cell.

**Tests**: engine tests per rule and per failure branch; the trace test asserts the three
rules' real verdicts stream for the winner and that no `not_assessed` status exists at all;
`test_seed`'s denominator assertion flips to asserting the three rules return real
verdicts; the suite re-run. `not_assessed` machinery is deleted everywhere it appears —
`models.NOT_ASSESSED`, `rules.not_assessed`, the `CheckStatus` literal, `change.py`'s
field, `api/lines.py:295`, `matrix.py`'s counts, `matrix.tsx`'s label, `api.ts`'s two
types, RequestCard's not-assessed block, the design-run one-line mention, the morning's
trace filters in `api/review.py` and `api/replay.py` (superseded — nothing left to
filter), and `eol_differential.py`'s `COVERAGE_LABELS`. The `no_evidence` admission
disappears from the demo world through the vmin facts below; the field stays in the model
for live parts whose manufacturers publish nothing, where it is a fact about the data
rather than about the engine.

## P3 · Annual volume on the operating profile

**Row** (8 Sep 🟡 + the live ⚪): every request says *no annual volume stated*; the figure
belongs beside `build_quantity`, which already lives on the profile with a stated source.

1. `profile.py`: `annual_volume: int | None` and `annual_volume_source: str | None`,
   validated like `build_quantity`.
2. `tools/seed_world.py` `profile_for` writes them — **numbers for veto**: Gateway **20,000**
   (its stated 5,000 a quarter, annualised), Sensor node **12,000**, Cabinet controller
   **4,800**, each sourced *"2026 production plan, annualised"*. Not tuned to anything: no
   stock figure or cost depends on them.
3. The review reads the line's profile. `ReviewRequest.annual_volume` is **removed** from
   both the streaming run and the one-shot endpoint — the profile is the one place the
   number lives, and an accepted-but-unread field is the smell another DEFERRED row already
   names.
4. `change.for_line` takes the volume from the caller as today; the callers pass the
   profile's figure.

**Done** = a rebuilt world's three requests each carry `recurring_annual` (e.g. the
Gateway's TLV1117 at +$0.1178 a unit → $2,356 a year against 20,000), and no surface says
*no annual volume stated*. If the line page header renders profile facts trivially, it
gains the figure; if not, it does not — the request is the surface that matters.

## P4 · A worked precedent is read (signature without the refdes)

**Row** (8 Sep 🟡): `store.worked_anywhere` has no caller; the $1,281-vs-$15,656 half of the
pitch is not wired.

1. `api/review.py:810`: the signature becomes `f"eol|{decision['retiring']}"`.
2. The run, after resolving the retiring part: `worked = {row["mpn"]: row["line_name"] for
   row in await store.worked_anywhere(user.org_id, f"eol|{notice['mpn']}")}`.
3. `review.candidates_for` gains `worked: Mapping[str, str]`, tried **after the notice's
   recommendation and before the approved list** — the manufacturer's answer is still first,
   and a part that already resolved this retirement is the cheapest answer the company has.
   New origin: *"resolved this on the {line_name}"*.
4. The rejection half is untouched — `rejected_on` is scoped to the board that measured it.

**Where the beat lands**: the first review of a part has no precedents, so this shows on
the *second* notice about the same retirement (the preliminary `PCN-2026-118` after the
full one was answered) — which is when the question "what do we already know?" is worth
asking out loud.

**Tests**: signature shape (no refdes) unit-tested; a worked part is offered with its
origin and does not duplicate an approved-list entry; a rejection on one board does not
suppress the part on another.

## P5 · What the review skipped is said and stored

**Row** (live 🟡): the NOT CHECKED panel does not survive reopening — and the streaming run
dropped the disclosure entirely (the `skipped` state in `changes.tsx` is rendered but never
populated; `_resolve_quietly` logs and returns `None`).

1. `review.candidates_for` reports what it could not consider: every candidate that reached
   `consider` and resolved to nothing or raised `Ambiguous`, with the sentence that stopped
   it. Catalogue hits filtered by the search are the search shaping its shortlist, not a
   skip, and stay out of this.
2. The run says each one aloud in the preamble — one line, the same register as *Trying …*:
   the MPN, the reason, *so it was not checked*.
3. Stored per notice: `notices.review_skipped` (jsonb, additive in `schema.sql`), written by
   the run beside the change requests; `GET /notices` returns it.
4. `changes.tsx` populates the existing NOT CHECKED panel from the stored list, so it
   survives navigation and reload like the requests do.

**Tests**: an ambiguous candidate is named with its sentence and stored; reopening the
notice shows the panel without running anything.

## P6 · A notice's review replays (R3's missing piece)

**Row** (live 🟡 + the ⚪ beneath it): lane state is `useState`; leaving the page loses the
run; returning shows only the stored documents. `decisions_for_notice` and
`replay.frames_from` both exist — the notice-level endpoint and the hydration are missing.

1. `GET /notices/{notice_id}/reviews` in `api/notices.py`: per decision under the notice —
   `decision_id`, `line_id`, `line_name`, `state`, `proposal`, `gate_rule`, `roles`,
   `frames` (through `frames_from`, with P2's filter), and for `state = 'pending'` the
   **question rebuilt the way the run asked it** (`_decision_text`), so the replay can
   re-raise it rather than showing a verdict with no way to answer it. The one-shot
   `GET /{id}/review` listing stays as the requests' own path.
2. `ReviewLanes` hydrates on mount when the endpoint returns rows: lanes built from frames
   through the same reducer a live run uses, `running: false`, pending questions re-raised
   with live buttons, partially-signed decisions showing what they show live. **RUN IT
   AGAIN** stays; starting a run replaces the hydration exactly as it replaces a finished
   live run.
3. No new storage, no invented frames — the module contract in `api/replay.py` still holds.

**Tests**: the endpoint's frames for a stored decision match what `frames_from` builds
including the skip of `not_assessed`; a pending decision carries its question; hydration
and a live run render the same lane for the same decision.

## P7 · The matrix takes what the review resolved

**Row** (live 🟡): `LD1117-3.3`, `SPX1117M3-L-3-3/TR` and `XBL1117-3.3` — the names JLCPCB's
package search returns — come back *not found* because `matrix_api.resolve` re-sources by
exact-MPN search, and **no recording exists for those searches** (verified: the only
recordings naming them are the package search and per-part normalisations).

1. **Spike first, live**: one script, three `part_search.search(mpn, limit=10)` calls
   without `CONTINUITY_FIXTURES=1`, which records as it goes (the MCP endpoint needs no
   key). If an exact-MPN search returns the part — as it does for `AMS1117-3.3` and
   `TLV1117LV33DCYR` — the fixtures close the replay gap and the rest is plumbing. If it
   does not, stop and say so: the fallback (`jlc_get_part` by MPN, then `sourcing.choose`)
   is a different resolution path and is Sparsh's call, not a default.
2. `change.Alternative` gains `manufacturer`, filled from the attempt the run already
   holds, and it serialises.
3. `matrixLink.ts` carries `mpn|manufacturer` pairs (the separator matters: manufacturer
   names contain commas); `matrixPrefill` parses them.
4. `MatrixRequest` gains optional `candidate_manufacturers: dict[str, str]`; `_build`
   prefers it over `recorded_manufacturers` for the named candidates. The typed form path
   is unchanged — a person typing an MPN still gets the recorded-manufacturer behaviour.

**Done** = the SHOW THE WORKING grid on a rebuilt world carries all the review's candidates
as checked columns — `unresolved` empty, `ambiguous` empty — and the three parts' cells
carry their own manufacturers' names.

## P8 · The board consequence, stored asynchronously

**Row** (live 🟡 + the ⚪ beneath it): no change request shows a board; the consequence is
computed on demand and never stored. Decision 2 above.

1. `api/boards.py`: the endpoint's body — `board_bundle` + `_needs_kicad` +
   `to_thread(_consequence, ...)` — moves into one coroutine both callers share.
2. `api/review.py` `_run_line`: once the proposal is chosen and the decision saved,
   `asyncio.create_task` fires the consequence for (retiring, proposal). It never blocks
   the stream, and its failure is logged and swallowed — a world with no KiCad gets the
   button it gets today, which is the honest degradation that surface already renders.
3. A store method attaches the landed payload to the latest change request for
   (notice, line) — additive jsonb update; the run's request row is written milliseconds
   after the proposal while the consequence takes seconds, so the row exists first, and
   the attach is a no-op if it does not.
4. `RequestCard.tsx`: a request carrying a board renders the pictures from the stored
   payload — no button, no wait, and the same caption/crop treatment the on-demand path
   paints. A request without one keeps today's button.

**Measure**: the review's replayed wall-clock before and after (expect no change — the task
is off the stream); the time from run end to boards landed on all three requests.

**Tests**: the attach writes the payload where the listing reads it; a card with a stored
board renders it; the e2e board-evidence spec still passes on a rebuilt world.

## P9 · Two notices about one part are distinguishable

**Row** (live ⚪): the list labels every entry by MPN alone; the received date is stored and
the reference number is in the document, and neither reaches the list. The list rows in
`changes.tsx` gain the reference and the received date. Check what `GET /notices` carries
first and add the field at the API if the reference is not already there.

## P10 · The graph legend knows what it is looking at

**Row** (8 Sep 🟡): the legend offers *Valid / Conflict / Pending* on a board at rest, where
every node is `unchecked`. `design/ComponentGraph.tsx` derives its legend rows from the
states actually present on the board it was handed (a resting board offers *Fitted ·
unchecked*, a running one the states it has) rather than a fixed list.

## P11 · (stretch) The catalogue search works a bounded batch at a time

**Row** (live 🟡): `_catalogue_search` normalises up to 25 hits **sequentially** — measured
52 s one day, unfinished after 140 s the next. Fix: take the first batch of hits that pass
the cheap filters (`_same_part`, vout), normalise them **concurrently**, keep successes in
pool order until `CATALOGUE_LIMIT`, fetch the next batch only if the limit is unmet.
Order-preserving, so the demo's candidate set is byte-identical under replay — and that is
the acceptance test: the review's candidates and verdicts on the seeded world are unchanged,
with the live-path call count measured before and after.

## Documentation, last

Each item moves its DEFERRED row with what fixed it and what it exposed; the header counts
re-counted. RUNNER, DEMO-DAY, OPERATING and FLOW gain what changed: R5's trace silence and
the request's two separated admissions; the annual cost line; the worked-precedent origin on
a second notice; the stored NOT CHECKED panel; the replayed review on `/changes`; the
prefilled matrix carrying manufacturers; the board in the card; the notices list; the
legend. Re-walk RUNNER's steps on the rebuilt world before writing any of it down — several
steps assert exact strings this pass changes.
