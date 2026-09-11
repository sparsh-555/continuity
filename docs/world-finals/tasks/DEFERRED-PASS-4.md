# Task · DEFERRED pass 4 — the review as the artefact, and the demo's last mile

> **Status: pass 4 is complete, 11 September.** All eight items landed, P12 to P19. What each
> did is in the commits; what each exposed is below.
>
> Three things worth carrying forward from the building of it:
>
> - **The paced replay crashed the page on its first run.** The `setState` updater read a mutable
>   index, and React calls an updater when it renders rather than when it is handed over — by
>   which point later steps had advanced the index past the end and the reducer was handed
>   `undefined`. The file's own comment, four lines above, warned that an updater must stay pure.
> - **Two fields broke the client on documents written before they existed** — the replay's
>   `origin` and the appendix's `verdicts`. A stored record is not rewritten, so every reader has
>   to tolerate its absence. Both were found by opening the page; neither was visible to the
>   suite.
> - **The sign-in sweep is development-only, and committed.** `import.meta.env.DEV` gates it, so
>   it cannot reach a built frontend — `grep -c 'SIGN IN ALL FOUR DESKS' dist/assets/*.js` is
>   zero. Sparsh asked for it to stay out of the repository; committing it *gated* is stronger
>   than leaving a local diff, which the next checkout takes with it.

Pass 4 is the pass that makes the product into the demonstration. Passes 2 and 3 were about
being correct; this one is about being *legible* in five recorded minutes, without putting a
single false thing on screen. Nothing here is a new capability. Everything here is either a
defect Sparsh found by driving the product, or a presentation decision he took with the
research in front of him.

**Repository** `~/Documents/GitHub/continuity`. **Baseline** main at `e6da6c9`, working tree
clean. **Suite** 1215 with a database · 43 frontend · lint clean · browser spec green ·
622 recorded calls (re-count before quoting any of these).

The rules are the ones in [`DEFERRED-BRIEF.md`](DEFERRED-BRIEF.md) and the top of
[`BUILD.md`](../BUILD.md). The one this pass leans on hardest: **a surface saying it could not
check a part destroys the pitch in seconds, and a surface saying something untrue destroys it
permanently.** Test first, watch it fail, fix, watch it pass, revert the fix and confirm the
test fails again. One commit per item, `type: description`, no scope. Rows move to *Resolved
here* with what fixed them, and the counts are recounted by counting.

## What the research settled, 11 Sep

Four searches, commissioned by Sparsh's questions. The sources matter because two decisions
below rest on them.

**Showing four desks through one UI is the defensible pattern.** Multi-role demos are run as
separate isolated sessions per role, and the pattern to avoid is *acting as* another user,
because impersonation blocks mutations and leaves buttons that cannot succeed. The documented
failure is not the mechanism but disorientation — *when did the swap happen, whose view is
this* — which is why the active desk is made louder in P18. Demo craft guidance is explicit
that a presenter should pre-authenticate and never log in live, which is P17.

**The change request is the document, and the appendix is where rejected detail goes.** Arena's
ECO template carries number, product lines, description, reason, impact, approvers by
department, and an affected-items table with revision, **material effectivity** and
**inventory disposition**. Every convention for rejected alternatives — NEPA's *alternatives
considered but eliminated*, MADR's *considered options*, the decision memo — gives each
alternative **one line in the body and its full detail in an appendix**; NEPA's standard is
that a rejected alternative is *discussed briefly*, not analysed. The synthesis from the
second search: **the matrix is for coverage and audit; the prose is for conviction.**

**The saving is a multiplication with cited constants, not a formula.** No published method
converts counts into hours. What exists is constants, and the defensible move is to show the
arithmetic and cite each one:

- **Loch & Terwiesch 1999** ([doi](https://doi.org/10.1016/s0737-6782(98)00042-3)) publishes
  ECO task touch times — a solution proposal 2 h, simulation setup 30 + 90 min, a cost-impact
  check 45 min, parts ordering 45 min, PM approval 10 min, about **5 work-hours per ECO
  iteration against 56 hours of throughput**, with waiting 70–90% of it.
- **Herbsleb et al. 2001** ([pdf](https://herbsleb.org/web-pubs/pdfs/herbsleb-empirical-2001.pdf))
  measures the per-handoff stall at a mean **0.9 days same-site and 2.4 days across a
  boundary**.
- **APQC measure 100697** ([source](https://www.apqc.org/resources/benchmarking/open-standards-benchmarking/measures/engineering-change-order-eco-cycle-time))
  is the comparator: median **7.0 days**, n = 4,075, elapsed from change request to production.
- **Fagan inspection rates are refused**: they are per artifact size, and no source publishes
  a per-checklist-item review rate, so any rule-check-to-size conversion would be invented.
- The vendor blogs that price "handoff costs" (apphandoff, standin, ustechautomations) sell
  the thing they price and are out.

## Decisions taken with Sparsh, 11 Sep

1. **The replay is paced, with no badge on screen.** The frames play over time at reading
   pace, staggered rather than metronomic (P14). **No on-screen label marks it as a replay**,
   and the disclosure lives where his own documents put it: one line of DEMO-DAY's Q&A — *it
   is a recorded run of the real engine, and here is what still executes live*. **What we do
   not do is tell a judge the run is live.** The 622 recordings are committed, `./demo.sh
   --check` prints that it is replaying on every start, and the repository is public, so a
   claim of live collapses in the first question and takes the submission with it.
2. **The saving is computed, shown with its arithmetic, and its constants are cited in the
   code.** No "modelled" label on screen either; the Q&A carries the method and the sources
   (P16). The money half needs no such treatment at all, because it is fully real: one-time
   $1,281 and $0.0143 a unit at 4,800 a year are computed from the bill.
3. **The rejected candidates' verdict sets move into the change request** as a collapsible
   appendix, which is where NEPA, MADR and the decision-memo convention all put them (P13).
4. **The substitution matrix screen goes.** With the appendix in the document, the grid's
   remaining job is comparing one candidate across boards, and that is not worth a rail
   destination in a five-minute demonstration. The route, the rail item, the client and the
   run-through step all go, and the tests with them.
5. **The board consequence narrates its real steps and shows them happen** (P15).
6. **All four desks are signed in beforehand from the sign-in screen** (P17), and the active
   desk is made unmistakable (P18).
7. **A short chime joins the notice arrival** (P19).

## Order

P12 first: it is the defect Sparsh hit and it is the smallest. P13 next, because removing a
screen invalidates documentation in three files, and documentation landings are cheaper when
nothing else is moving. P14 and P15 are the two that change what the recording looks like, so
they come before the metrics in P16, which need the review's final shape. P17 to P19 are
independent and small. Documentation last, in one commit per document.

Files shared between items — `review/ReviewLanes.tsx` (P12, P14), `review/RequestCard.tsx`
(P13, P16), `lib/sseClient.ts` and `review/laneState.ts` (P14), `api/boards.py` and
`board/BoardConsequence.tsx` (P15) — mean these are serialized commits from one pair of hands,
not parallel agents.

---

## P12 · An answerable question stops offering a signature it already has

**The defect, as Sparsh found it.** Sign as the engineer on `/changes`, then revisit the page.
The lane's question comes back with **SIGN FOR MY DESK** and **LEAVE IT** still on it, under a
line that already says *Signed by DESIGN*. Pressing it is refused — correctly, by the server,
with *engineering already signed this* — and then **the lane's badge flips to FAILED**, because
`ReviewLanes.Verdict` renders `FAILED` whenever `lane.error` is set and the refusal was stored
there. A refused signature is not a failed board, and a lane that reads as failed on the screen
a judge is watching is the worst possible false statement this product can make.

**Two rules, and both already exist in the repository.** `/approvals` states its own:
*"Drawn only where it can be used. A desk that has already signed sees what it signed and no
buttons, rather than buttons that will 409."* The lane must hold the same rule — this is the
second place a question is answered, and two definitions of "may I sign this" is exactly the
drift `review.choose` and `change.for_line` already cost this project once.

**Where.** `review/ReviewLanes.tsx` — the question block, `answer()`'s catch, and `Verdict`'s
`lane.error` branch. `lane.signatures.signed` and the signed-in user's roles are both already
in hand, so nothing new is fetched.

**Done when.** A desk that has signed sees what it signed and no controls; a signature the
server refuses is reported as a refusal in the question panel and **leaves the lane's verdict
untouched**; and the browser spec covers the revisit. Verified by driving it, not by reading it.

---

## P13 · The rejected candidates move into the document, and the matrix screen goes

**What.** The change request gains an appendix: each rejected alternative with the reason it was
eliminated in the body, as now, and its **full verdict set** available on expansion — the
twenty-two checks, their evidence, their margins and the department that owns each. This is
NEPA's shape and MADR's shape, and it is what makes the document auditable on its own.

**The data is already stored.** `decisions.document.attempts[]` carries every candidate with its
verdicts — measured on the seeded world: **5 attempts, all 5 with verdict arrays, the largest
26 verdicts**. Only the *stream* omits the losers, which is why the lane shows the winner's
trace and nothing else. So this is a rendering job plus a payload check, not a new evaluation.

**What goes.** `routes/matrix.tsx`, its route in `main.tsx`, its rail item, its client functions
in `lib/api.ts`, its tests, and the **SHOW THE WORKING** link on `/changes`. The run-through's
step 9 is deleted. `api/matrix.py` and `matrix.py` stay: `evaluate_matrix` is what the notice
path and the review use, and only the screen is going.

**Done when.** The card lists every alternative, expands to the full set, and names the
department on each failure; `/matrix` is gone from the router, the rail and the run-through; and
nothing else regressed — the review path, the notice path and the seeded world all still work.

---

## P14 · The replay plays at reading pace

**What.** A replayed review's stored frames are applied over time instead of all at once. The
reasoning streams into the panel where the signature is asked for, so the argument is in front
of the reader before the buttons; the full trace stays one click below it. A control skips to
the end for anybody who does not want to wait.

**Not robotic, and not a metronome.** The interval is staggered — a base cadence with jitter
around it, so consecutive lines do not land on a beat. The rule the pacing exists under: the
run must remain a *recording played back*. Nothing is slowed down to look busier, no frame is
invented, no caption claims the model is working now, and the end state is byte-identical to the
instant path.

**Where.** `review/laneState.ts` and `ReviewLanes.tsx` for the hydration path; the pacing seam
already exists in `lib/sseClient.ts` — the milestone type and the pacing gate built for the
retired walkthrough, which have had no caller since the tour was deleted. Reuse that shape
rather than inventing a second one.

**Done when.** A replay takes long enough to read (measure it, and record the number in the
commit); the frames arrive in order; the final state is identical to the unpaced path, which
**has its own test**; the browser spec still passes, which means it still waits for the
change-request button rather than assuming an interval.

---

## P15 · The board consequence narrates its four steps, and shows them happen

**What.** The caption stops being one hardcoded sentence shown on every board — *"The pads it
lands on are the pads that are already there"* — and says what happened to **this** board:

- the pads carried **by function**, from the wiring the swap already computed: `1 → GND`,
  `2 → +3V3`, `3 → +5V` on the Gateway;
- the zones refilled on **both** copies, each in its own interpreter;
- **DRC run before and after**, and what changed between them — on the Gateway a footprint
  mismatch disappears, 7 to 6 — which is the honest way to show the check ran;
- and the render, which is the picture the reader is looking at.

**Then show each step happen** rather than only describing it: the swap, the refill, the DRC,
the render, as visible moments in the pane. This is the *watch it work* beat, and every frame of
it is a real step the substitution runs.

**The data is already on the wire.** The consequence payload carries `wiring.wired`,
`unwired_pads`, `stranded` and `counts` — measured live on the Gateway:
`{"wired": {"1": "GND", "2": "+3V3", "3": "+5V"}, "unwired_pads": [], "stranded": []}` and
`lib_footprint_mismatch: before 7, after 6`. Nothing new is computed; the sentence is simply no
longer written by hand.

**Done when.** Each board's narration differs and is derivable from that board's own payload;
the four steps are visible as they happen; and the wording never claims a check that did not run.

---

## P16 · The change request carries the saving, the disposition and the effectivity

**What, three additions to the document and no fabrication.**

1. **The saving, as a multiplication with cited constants.** Hours removed =
   `desks × boards × per-desk touch minutes` from Loch & Terwiesch's published ECO task times,
   plus `handoffs removed × per-handoff queue delay` from Herbsleb's measured 0.9-day same-site
   stall. Publish the range, show every multiplication on the card, and put each constant's
   source in the code beside it. **The number is whatever the arithmetic gives**, which will not
   be the scenario's 48 hours, and that is the point: a computed figure that survives *where did
   that come from* beats a chosen one that does not. The Q&A carries the sources.
2. **The disposition of the existing stock.** The Gateway's 1,133 units against a 5,000 build is
   already a disposition — bridge-buy, accept a lead time, or re-qualify — and today it reads
   only as a shortfall. An ECO carries the inventory disposition, and we have the number.
3. **The effectivity.** Which revision the change takes effect at, and from when. We hold the
   revision; the document should say it in the terms a change document uses.

**Where.** `change.py` for the computation and the document; `review/RequestCard.tsx` to render
it. The recurring cost is already computed and stays as it is ($0.0143 a unit at 4,800 a year).

**Done when.** Every input on the card is a number the system holds, the arithmetic is visible,
and no figure appears that is not either measured or a cited constant applied to a measured
count.

---

## P17 · All four desks are signed in before the recording starts

**What.** One control on the sign-in screen that signs in the four seeded accounts, so the rail
switcher works the moment the camera rolls. Four real sessions coexisting in one browser is the
existing design — `/auth/sessions` lists them and `/auth/switch` makes one active — so this is
four calls, not a new mechanism.

**Why it is not a shortcut.** Demo craft guidance says exactly this: pre-authenticate, and never
log in live. Typing an email and password on camera is dead time in a five-minute video.

**Where.** `routes/auth.tsx` (the sign-in screen) and `lib/api.ts`. The control must be
unmistakably a demo affordance rather than a product feature: it names the four desk accounts
and says it is for the seeded world.

**Done when.** One press leaves the rail switcher offering all four desks, and the ordinary
sign-in path is untouched.

---

## P18 · The active desk is unmistakable

**What.** The four-letter chip becomes loud: a coloured rail edge in the desk's own colour, and
the desk named in the header of the screens where a desk acts — the approvals queue, the lanes
that ask for a signature, and the product line whose change is being signed.

**Why.** The research is unambiguous about the failure mode of multi-persona demos: the audience
loses track of whose view it is looking at. Four desks in one browser is the right mechanism;
being unable to tell which one is on screen is the wrong presentation.

**Done when.** A person glancing at any frame of the recording can say which desk is signed in,
from the chrome alone, without reading the switcher.

---

## P19 · The notice arrives audibly

**What.** A short, quiet tone with the arrival toast. The product has no mute control, so this is
a sound with no way to turn it off, which is worth knowing and acceptable for a demo world.

**Where.** `hooks/useNoticeArrivals.tsx` and one small asset. Must not fire on the initial fetch,
only on a genuinely new notice, which is the same rule the toast already follows.

**Done when.** A notice delivered while the tab is open makes the sound once, and a page load
with notices already present makes none.

---

## Documentation, last

In this order, one commit each.

**RUNNER.md** — step 9 and its SHOW THE WORKING line go with the matrix; the checklist gains the
new beats where they belong; and step 5's lane checklist no longer describes a screen that is
not there.

**DEMO-DAY.md** — the matrix paragraph goes; the Q&A gains the two answers this pass was built
around: *it is a recorded run, and here is what still executes live*, and *where the saving comes
from, with its constants and their sources*. Both are told, neither is a badge.

**OPERATING.md** — the route table loses `/matrix`; the symptoms table gains the two things this
pass fixed, a lane that reads FAILED after a refused signature and a replay that finishes before
anybody can read it.

**DEFERRED.md** — P12's row and the matrix rows close into *Resolved here*; the header counts
recounted from the file.

---

## What not to touch

- **`api/matrix.py` and `matrix.py`.** Only the screen goes. `evaluate_matrix` is the notice
  path's own evaluation and the review's cross-line answer.
- **`backend/fixtures/`** and **`backend/cache/`** — recordings and cache, never cleaned.
- **The seeded world's story.** Three lines affected, NCP1117 refused on the Gateway at 159 °C
  against a 150 °C limit, TLV1117 losing the cabinet at 5.5 V against 12 V, the Gateway stopping
  at procurement on 1,133 in stock against a 5,000 build. Every item above is presentation; if
  one of them changes an answer, it is wrong.
