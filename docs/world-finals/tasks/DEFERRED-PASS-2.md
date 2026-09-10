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

1. **The three not-assessed rules stay in the change request and come off the trace.** The
   signer keeps the honest denominator; no run leads with what the engine declined. The
   matrix keeps every verdict — it is the full working, opened deliberately.
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

## P2 · The two coverage admissions, separated (R5)

**Row** (live 🟡 + the ⚪ beneath it): the three not-assessed rules are paragraph-length on
the trace and lead the collapsed lane; `Could not be checked: voltage overlap` reads
identical to them; both are the wrong colour-pairing on the request.

### 2a · Off the trace, on the document

`engine/rules.py` keeps returning the three on every board — the denominator is real and
stays. The filter belongs at the two places the trace is *spoken*, so the live run and the
rebuilt one cannot disagree:

- `api/review.py`'s emission loop (`emit(stream.check(verdict))` for the winner) skips
  verdicts whose `status == "not_assessed"`. That status is produced by `not_assessed()`
  alone, so nothing else is silenced.
- `api/replay.frames_from` skips the same verdicts when rebuilding from
  `decisions.document`. The document is untouched — `change.for_line` still collects
  `not_assessed` from the stored attempts.

The design-run trace already names them once at the end (resolved 7 Sep) and is left alone.
**Collapsed lanes** then show the last real verdict — on the Gateway that is
`FAILED · availability`, which is the sentence the demo wants leading that lane.

### 2b · The two admissions stop looking identical

`RequestCard.tsx` renders `not_assessed` and `no_evidence` in the same tone today. The
boundary (`OUTSIDE THE ENGINE'S SCOPE`) and the gap (`COULD NOT BE CHECKED`) get different
headers, and the gap names its rule, because only the gap is ever somebody's job to fix.

### 2c · The voltage minimums, sourced

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

**Tests**: one for the emission filter (a run's check frames carry no `not_assessed`), one
for `frames_from` agreeing, one per behaviour of the RequestCard distinction, and the
existing suite re-run — several tests assert today's amber and must be updated to assert
green with the evidence line naming the derivation.

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
