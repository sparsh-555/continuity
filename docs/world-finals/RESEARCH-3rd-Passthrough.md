# RESEARCH-3rd-Passthrough.md

The third walk through the built product, 10 Sep. Ten findings, each checked against the code
before it was written down.

This file holds the part that needs thinking about: what the code actually does, what the
options are, what other people have published about the same problem, and a recommendation
where there is one to make. [DEFERRED.md](DEFERRED.md) carries the one-line version of each
with a severity, and points back here.

Four of these are decisions rather than defects, and they are marked **decision** where they
are. Nothing below has been changed in the code.

---

## R1 The notice has to announce itself

**Finding 2.** A notice arrived by email, the server read it, and nothing on screen said so
except the `/changes` list and the product line pages once they were opened again.

### What the code does

`routes/changes.tsx:19` sets `ARRIVALS_MS = 10_000` and `:54-61` polls `listNotices()` on that
interval, which is why `/changes` picks up a mailed notice on its own. **That is the only poll
in the product.** `routes/lines.tsx` and `routes/line.tsx` fetch once on mount and never
again, and `shell/` has no notification component of any kind. The server side is fine:
`mail.POLL_SECONDS = 15.0`, so the notice is in the database within about fifteen seconds of
being forwarded.

This is BUILD item 28, still the only unbuilt item, and its own note already says *"this is
the moment the demo turns on. He sends the mail on stage and the app has to react while he is
talking."*

### What the pass added to it

The sequence Sparsh wants to run is now specific, and it is worth writing into the item
because it changes what has to update:

1. He is on `/lines`, talking about how an engineer adds a product line and what it carries.
2. The mail goes out at the start of that explanation. Twenty to thirty seconds pass while he
   keeps talking, which is the dead time the current build spends staring at `/changes`.
3. The notification arrives wherever he is. One line, dismissible, naming the part and how
   many products it reaches.
4. The affected rows on `/lines` change without a reload, and a product line already open
   turns its regulator red on the power tree and in the bill, which is the join that already
   works on load.
5. It offers the review. He goes to `/changes` and says *this is where Continuity gathers
   what has to change across every affected product line*.

### What to build

The transport is already decided by the existing poll: extend it rather than open an SSE
channel for a list that changes a few times a day. Concretely, a small provider above the
router that polls `listNotices()` on the same ten seconds, keeps the newest id it has seen,
raises a toast when that changes, and exposes the notice count so `/lines` and `/lines/:id`
can refetch off the same tick. One timer for the whole app rather than one per route.

The honest caveat to state in the pitch if anybody asks: this is a poll, not a push. Say so.

---

## R2 Every lane should stream its own trace

**Finding 3.** The company-wide run shows one line of narration per product and then a
verdict. What is wanted is what a single product line's review pane shows, three times over,
running at once.

### What the code does

The server already sends everything needed. `api/review.py:361` emits a `candidate` frame per
attempt and `:375` emits a `check` frame per verdict, both carrying `line_id`
(`review.py:502-503` stamps every frame with the line it belongs to).

**The lanes throw those frames away.** `review/ReviewLanes.tsx:129-161` handles
`review_started`, `reasoning`, `question`, `line_done` and `error`, and has no case for
`candidate` or `check`. So an expanded lane can only ever show narration, and the twenty-two
rule verdicts that make up the argument never reach that screen at all. The single-line pane
does handle them: `review/useLineReview.ts:75-90` is the same reducer with the two extra
cases, and `ReviewTrace` renders them with a green tick, a red cross or a dash.

So the trace he wants in the lanes is a frontend change to a component that is already
receiving the data.

Two other facts from the same file matter for the design:

- `_run_line` emits `check` frames **only for the winning candidate** (`review.py:372-376`),
  in one burst after the candidate loop. The losers' verdicts are computed and are in
  `decisions.document`, but they are not streamed.
- `review.py:365-368` has an explicit `await asyncio.sleep(0)` between candidates so the three
  boards interleave rather than finishing in the order they started. The concurrency is real:
  three `asyncio.create_task(worker(line))` writing into one queue (`review.py:593`).

### The speed question, which is a decision

**decision.** Replayed, the whole run is 0.25 s. Nobody can read three traces in a quarter of
a second, so streaming them changes nothing on its own.

There are exactly three honest options and one dishonest one.

| | What it is | Cost |
|---|---|---|
| **Run live** | `./demo.sh --live`. The wait is real because the distributor really is being asked | Two minutes, and it has failed to finish before |
| **Pace the reveal** | The frames are all in hand at 0.25 s; the client renders them at a readable rate | Only honest if the UI never claims work is still happening |
| **Show it finished** | Let it land instantly and walk the completed traces by hand | No sense of simultaneity |
| ~~Sleep in the server~~ | Delay frames to look like work | Fabricating latency. Not on the table |

The second is the one worth thinking about, and the distinction that makes it defensible is
one the research is explicit about. Multigrid's page on reasoning UX separates **generated
model reasoning** from **real pipeline events**, and says of the latter that they are
*"actual observed system behaviour, and they are the most trustworthy thing in this list"*,
adding that filling a wait with real activity is legitimate *"specifically because the work is
real. The same treatment applied to a fabricated 'analysing…' sequence would be theatre."*
Continuity's frames are pipeline events and deterministic verdicts, not chain-of-thought.
Replaying them at reading speed is a playback control over things that genuinely happened, in
the order they genuinely happened, which is not the same act as inventing a delay.

The line to hold, if this is built: the run's own state must be truthful. A lane that has
finished must not say CHECKING while its recorded frames are still being drawn. The pattern
that fits is a transport, the way `jcurveiq-agent-run-panel` replays a recorded run through a
`setTimeout` emitter with a reset, and the way the interactive-explanation study gives its
reader playback controls to step forward and back through the reasoning
([arXiv:2510.22922](https://arxiv.org/html/2510.22922v2)). Label the control honestly, put the
elapsed real time somewhere, and it is a scrubber over a finished run rather than a fake one.

**Recommendation.** Build the trace first, because it is right at any speed and it is a
frontend-only change. Then decide the pacing separately, with the run-through in front of you.

### Sources

- [Progressive Disclosure of AI Reasoning, Multigrid](https://multigrid.ai/learn/reasoning-ux) — pipeline events versus generated reasoning; auto-collapse the trace the moment there is an answer to look at.
- [Improving Human Verification of LLM Reasoning through Interactive Explanation Interfaces, arXiv:2510.22922](https://arxiv.org/html/2510.22922v2) — step-by-step reveal with playback controls; graph-shaped traces reached 85.6% verification accuracy against 73.5% for a plain chain of thought, and 85.2% against 66.1% at identifying *which* step was wrong.
- [jcurveiq-agent-run-panel](https://github.com/diyakharb1029/jcurveiq-agent-run-panel) — a parallel-task run panel driven by a recorded fixture and a timed emitter, with a reset.

---

## R3 The changes page is doing three jobs

**Findings 4 and 5.** `/changes` is the notices list, the live concurrent review, and the
stack of finished change requests, one after another down a single reading-width column. The
review is hard to appreciate, and leaving the page loses it.

### What the code does

`routes/changes.tsx` renders, in this order and all in one scroll: the notices list
(`:160-196`), the selected notice with its provenance line and the override box
(`:200-236`), `<ReviewLanes>` (`:259-268`), and then one `<RequestCard>` per affected line
(`:270-280`). `Page … width="reading"` constrains the whole thing to a reading column, which
is why three change requests stack vertically and the third is a scroll away.

**Why the trace vanishes.** All lane state lives in `ReviewLanes`' own `useState`
(`ReviewLanes.tsx:95-100`). Navigating away unmounts the component, the effect at `:103`
aborts the stream, and the state goes with it. Coming back, `open()` runs
(`changes.tsx:98-116`) and fetches `listChangeRequests(notice.id)`, so what fills the screen
is the stored documents. Nothing is broken; there is simply no rehydration, and the finished
documents look like a replacement for the run because they arrive in the same column.

**The fix already exists in pieces.** `api/replay.frames_from(notice, decision)` rebuilds a
line's whole trace from `decisions.document`, and `GET /lines/{line_id}/reviews`
(`api/lines.py:317`) serves it for one product. There is no notice-level equivalent. A
`GET /notices/{notice_id}/reviews` that runs the same function over every decision under that
notice would let `/changes` come back to a finished run showing the run, and the store already
groups decisions by notice (`store.py:1151-1168`, `DISTINCT ON (notice_id, line_id)`).

### What the research says about the layout

The patterns that keep coming up are the same three, and they map onto what is already here:

**One pane per worker, with a ceiling.** The tiled-agent-layout writeup puts the practical
range at four or five panes and is blunt about what happens past it: *"a pane below readable
size shows motion but not content"*, which it calls **false supervision** — the supervisor
sees green animation rather than the error. Three affected product lines sits inside that
range, which is why lanes work here and would not at ten. It also names the failure this
screen has: *"attention thrashing: all panes update at once after a batch dispatch"*.

**Layered disclosure, three levels, not two.** The clearest statement of it is the
result / reason / evidence model: layer one is the answer with no interpretation needed, layer
two is one short line saying why *positioned next to the result*, layer three is the evidence,
citations and alternatives considered. Most readers never open layer three and *"its presence
matters more than its usage"*. Continuity already has all three artefacts. What it does not
have is them nested: the verdict, the reason and the change request are three separate blocks
in one column rather than one thing that opens.

**Master-detail, not a single scroll.** Every one of the agent dashboards found does the same
split: a list of runs on one side, one run's detail on the other, with the detail expanding in
place. Output Conductor calls it *"split-pane layout: master-detail pattern, list on left,
detail on right with animated width transitions"*, and pairs it with *"progressive disclosure:
step cards show summary by default, traces and evaluations expand inline"*. Google PAIR's
agent trace viewer does the same for structured traces in *"a multi-column layout"* with gap
compression for long runs.

### The shape this suggests

Split `/changes` along the seam it already has. The left is what arrived and what it reaches,
which is a list. The right is one thing at a time, and the lane a reader opens is that thing:
its trace streaming, its board before and after, its bill row changing, its question and its
change request, all in one pane that belongs to that product. The other lanes stay visible and
keep advancing, which is the simultaneity, and the reader is never scrolling past a finished
document to reach a running one.

Three consequences worth stating before anybody builds it:

- The width has to stop being `reading`. A three-pane run does not fit a reading column.
- The change request stops being a separate stack at the bottom and becomes the last layer of
  the lane it belongs to, which is what `/lines/:id` already does with its one-line
  *Change request · …* at the end of the trace.
- The notices list and the review are different enough that `/changes` should probably not
  hold the review's history too. A notice with a finished run needs to rehydrate, which is the
  endpoint above, not a fourth job for the page.

**decision.** This is a real redesign of the busiest screen in the demo, and it is the one
place where the two governing rules pull in opposite directions: more on screen at once is
what he is asking for, and *do not draw an affordance that cannot be used* is what stops it
becoming a dashboard of empty panes. Worth agreeing on the target layout before any of it is
written.

### Sources

- [Tiled Agent Layout, agentpatterns.ai](https://agentpatterns.ai/workflows/tiled-agent-layout/) — the four-to-five pane ceiling, false supervision, attention thrashing.
- [Explainable AI UX: Layered Disclosure Over Raw Logs](https://8080ai.hashnode.dev/explainable-ai-ux-layered-disclosure) — result, reason, evidence; match explanation depth to stakes; distinguish *what the system is doing* from *why it did it*.
- [output-conductor](https://github.com/brianchristopherbrady/output-conductor) — master-detail with animated width, timeline swimlanes, status-driven colour, progressive disclosure of step traces.
- [PAIR-code/agent-trace-vis](https://github.com/PAIR-code/agent-trace-vis) — Google PAIR's timeline view for structured agent traces, multi-column with gap compression.
- [React Bits Pro, Agent Activity](https://pro.reactbits.dev/docs/app-ui/agent-activity) — parallel agent lanes, collapsible run timeline with nested sub-steps and duration bars.
- [DeerFlow 2.0 frontend patterns](https://opentil.ai/@biao29/deerflow-2-0-frontend-multi-agent-task-execution-ux-patterns) — one card per subtask, collapsed card shows the tool currently running, expands to the full chain.

---

## R4 The board in the change request, and exporting it

**Findings 6 and 7.** No change request shows a board, and the control in the recap is a
button reading **PLACE NCP1117ST33T3G ON THIS BOARD**.

### What that button does

It runs the real substitution. `board/BoardConsequence.tsx:80-102` calls
`POST /lines/{id}/board/consequence`, which unpacks the stored KiCad project into a scratch
directory, reads its bill, resolves the pinout of both parts, swaps the footprint with
`pcbnew`, refills the zones on both copies, runs DRC before and after, and returns the two
cropped SVGs plus the findings that are new (`api/boards.py:231-305`). It takes several
seconds and it is the strongest single artefact in the product.

**Why it is a button and not a picture.** `RequestCard.tsx:97-101` renders
`<BoardConsequence>` without `auto`, and `BoardConsequence.tsx:106-108` only runs on mount
when `auto` is set. The product line page passes `auto` (`review/BoardPane.tsx:85`), so
choosing BOARD there *is* the request. The change request asks first, and the reasoning in the
comment at `:70-74` is that a document somebody is reading should not launch three KiCad runs
because it scrolled into view.

That reasoning is sound and the outcome is still wrong. On `/changes` there are three cards,
so a reader sees three buttons and no boards, and the demo's own claim that the substitution
is checked against the real layout is behind a control nobody presses. It is also, by the
letter of the second governing rule, a drawn affordance whose result the reader cannot
anticipate.

**The actual cause is upstream: the board consequence is not stored.** That is already a row
in DEFERRED. `_run_line` writes attempts and verdicts into `decisions.document` and nothing
about the board. If the review stored the outcome for the winning candidate the way it stores
the verdicts, the card would render it with no button, no wait and no KiCad call, and the
change request document would finally contain the board evidence it claims to weigh.

### Exporting the changed board

**This is buildable and the file already exists.** `kicad/board.py:191` writes
`kicad-after-{refdes}.kicad_pcb` next to the original, and `:206-212` writes the zone-filled
copies of both. `board.py`'s own docstring is explicit that *"the original board file is never
written to. The substituted copy is a new file beside it."* Then `api/boards.py:312`
does `shutil.rmtree(workdir, ignore_errors=True)` and the whole thing goes away.

So exporting is a matter of keeping something we already produce. Three levels, cheapest
first:

1. **The board file.** Return `kicad-after-*.kicad_pcb` as a download. One `Content-Disposition`
   response, and there is a precedent for exactly that shape in `api/app.py:704-708`, which
   already serves a design run's bill of materials as a CSV attachment.
2. **The project.** Re-zip the scratch directory with the substituted board in place of the
   original, so what comes down opens in KiCad as a project rather than as a loose file.
3. **Fabrication output.** `kicad-cli` will plot the changed board without the GUI:
   `pcb export gerbers -o dir/ board.kicad_pcb`, `pcb export drill`, `pcb export pos`,
   `pcb export pdf --mode-multipage`, `pcb export step`. We already run `kicad-cli` for the
   BOM, the SVG and DRC, so this is another invocation of a runner that exists. KiCad 9 also
   has `kicad-cli jobset` to run a declared set of exports in one go, and note that the
   singular `pcb export gerber` is deprecated in 9.0 and removed in 10.0, so use `gerbers`.

Level one is worth doing on its own: *here is the board with the substitute in it, open it
yourself* is a strong answer to a judge asking whether the change is real, and it costs one
endpoint. Level three is a bigger claim than this demo needs and can wait.

One caveat that has to be said with any of it: what comes out is a **placement**, not a
finished layout. The part is swapped and the zones are refilled, and nothing routes, re-checks
clearances by hand, or updates the schematic. The DRC delta on screen is exactly the statement
of what that placement cost, and the export should carry the same sentence.

### Sources

- [KiCad Command-Line Interface, official docs](https://docs.kicad.org/master/en/cli/cli.html) — `pcb export gerbers | drill | pos | pdf | step`, and `jobset`.
- [kicad-python board API](https://docs.kicad.org/kicad-python-main/board.html) — `save_as(filename, overwrite, include_project)`, `export_gerbers`, `export_pdf`, for the in-process path we already use for the swap.
- [KiExport](https://github.com/vishnumaiea/KiExport) — a worked example of packaging a full manufacturing set out of `kicad-cli`, including the zip layout, if level three is ever wanted.

---

## R5 The two coverage admissions

**Finding 8.** *Not assessed: emc, output capacitor stability, signal integrity* and *Could
not be checked: voltage overlap* appear on the change request, and the three declining rules
appear again as dashes with paragraph-long explanations in the individual validation trace.

### What the code does

They are two different things that currently look alike.

**The three are a declared boundary.** `engine/models.py:167-172` holds them as constants with
their reasons, and `engine/rules.py:1735-1753` returns them as `not_assessed` verdicts on
**every** evaluation of **every** board, scoped to the board rather than to a slot. The
docstring says why: *"Returning them on every evaluation gives an approver an honest
denominator without making a board look as if its geometry, emissions, or regulator stability
had been inspected."* None of the three is implementable from a bill of materials. EMC is a
measurement. Signal integrity needs geometry and a stackup. Regulator stability needs
simulation, and the part of it that *is* checkable from a datasheet — an explicit published
capacitor requirement — is already a separate implemented rule, `capacitor_requirements`.

**The fourth is missing data.** *Could not be checked: voltage overlap* is
`evidence_missing`, not `not_assessed`. It fires on this board because two parts publish a
maximum and no minimum, which is visible in the trace as the two amber entries reading *"is
within the 25 V maximum CL31A226KAHNNNE states, but it publishes no minimum"*. That is a fact
we could add. `tools/seed_world.py` is already the writer of verified datasheet readings for
PARTS.md, so a published minimum input voltage for those parts would turn the amber into a
green and remove that line from the document entirely.

So finding 8 splits cleanly:

- The `voltage_overlap` line is closeable by reading two datasheets and adding the values to
  PARTS.md. **That is the "add stuff" half, and it is small.**
- The three are not closeable, and the question is only where they are allowed to appear.

### Where they are allowed to appear

**decision.** BUILD's second rule already answers this for the demo surfaces and the current
build does not follow it. The rule says coverage honesty belongs in the change request, where
somebody is deciding whether to sign, and never on a page seen for five seconds. The three
dashes with their explanatory paragraphs in the validation trace are that prose on that page.

Three ways to go, and I would take the second:

1. **Remove the three rules.** Honest in the sense that the product stops claiming a
   denominator, dishonest in that a reader can no longer tell an unasked question from a
   passed one. It also throws away a genuinely good answer to *"what does it not do?"*
2. **Keep them in the document, take them out of the trace.** The change request keeps one
   line naming the three, because the person signing should see the denominator. The trace
   drops them, because a run that just checked twenty-two things should not end with three
   paragraphs about what it did not check. This is what the rule as written already asks for.
3. **Collapse them to a count everywhere.** *22 checked, 3 outside the engine's scope*, with
   the reasons behind a click. Cheapest, and it keeps the honesty in both places.

Whichever way, the two lines should stop looking identical, because one says *we do not answer
this* and the other says *we tried and had nothing to read*, and only the second is ever
somebody's job to fix. `RequestCard.tsx:81-95` already has the right comment about that
distinction and renders both in the same colour.

---

## R6 What the substitution matrix is for

**Finding 9.** Still not understood after three passes, and it sounds like other components
have taken its job.

### In one sentence

**The matrix is the only screen in the product that shows which department each answer belongs
to.**

That is not what I said last time, and last time was wrong in a way worth correcting.
`matrix.Cell.departments` (`matrix.py:105-117`) works out whose desk a cell lands on from what
actually failed on it, `api/matrix.py:112` serialises it, and `routes/matrix.tsx:67-69` prints
it under every cell, with `:345` summarising it as *"Decisions here belong to engineering and
procurement."* Nothing else in the product does that on the demo path.

So the three artefacts are not the same thing shown three ways:

| | What it answers |
|---|---|
| The **trace** | how *this* board reached *its* answer, rule by rule, in the order the run asked |
| The **change request** | what somebody signs for this board: the proposal, the rejections, the cost, the desks |
| The **matrix** | every candidate against every board at once, **and who owns each failure** |

The second thing only the matrix has: the losers' working. `api/review.py:372-376` streams
check frames for the winning candidate alone, so *LD1117 is not on the approved list* exists in
the review as one narrated sentence, while the matrix has its twenty-two verdicts and the
evidence behind each.

The sentence to say out loud is therefore: **the change request is the answer, the trace is how
one board got there, and the matrix is the grid both were cut from, with every department's
name on it.**

### Why it does not land

Two reasons, and the first is now the more serious.

**It is the only place the cross-team story is visible, and it is the one screen the
run-through calls optional.** That is a consequence of [R8](#r8-the-cross-team-response-is-the-problem-statement-and-one-desk-answers-everything),
not of the matrix itself. If the departments were attributed on the review and the change
request the way they are here, the matrix would go back to being the working rather than the
only evidence for the pitch.

**It asks the reader to supply what the review already knows.** `routes/matrix.tsx:148` starts
with a typed `u1`, `:257` needs the lines ticked by hand, the candidate MPNs are typed into a
box, and `api/matrix.py:225` refuses any line that does not carry that exact designator. Every
one of those three inputs is already in the notice and in the review that just ran.

**decision.** One prefilled link from a finished review or a change request into `/matrix`,
with the lines, the slot and the candidates in the query string, turns it from a form into a
destination. The endpoint already takes all three. The alternative is to cut it from the
run-through and leave it in the rail, which is worse, because an empty form behind a rail icon
is the first thing a curious judge will click.

## R7 A retired part should look retired in the memory graph

**Finding 10.** On `/memory`, `AMS1117-3.3` carries a thin outline and is otherwise the same
orange circle as every other part, and its edges to the three boards that still carry it look
like every other edge.

### What the code does

`routes/memory.tsx:427` fills **every** part node with the same `#f2a25c`, whatever its
lifecycle. `:436-441` adds a 2 px ring, `#ffb4ab` when the part is `nrnd` or `obsolete` and
`#f5d84a` when it merely has history, and that ring is the entire encoding. At the zoom the
graph settles at, a pale ring around a saturated fill is close to invisible, which is exactly
what the screenshot shows.

Edges are worse, in the sense that the information is there and pointed the other way.
`:466-468` already draws a dashed line, but `link.historical` means *was on this board and has
been replaced*. A part that is retired and **still fitted** draws a solid grey line identical
to a healthy one, so the three edges that carry the entire story of this demo are the three
least distinguishable things on the screen.

### What the research says

The consistent advice is narrower than it first looks.

**Do not add a channel per variable.** The lineage-visualisation writeup puts it directly:
*"the temptation is to encode type as shape, freshness as colour, size as node area,
ownership as border, staleness as line style, and confidence as opacity. The result is
unreadable."* This graph already spends shape on kind (circle for a part, square for a product
line), area on something, and ring colour on two different meanings at once. Adding more
without taking something away will not help.

**Colour must not be the only carrier.** This is WCAG 1.4.1, and the same writeup makes the
practical version of it: *"roughly one reader in twelve will not distinguish the red-green
pairing that most status encodings default to"*, and border weight is preferred over a
distinct colour partly because *"it survives greyscale printing and colour-blind readers"*.
For a projector or a shared screen this matters twice over.

**Vary lightness, not only hue.** The Erdős atlas commit is a good worked example of the
failure and the fix: two adjacent hues, red against orange, carrying the map's most important
distinction, replaced by dark red against light amber *"differing in LIGHTNESS as well as
hue"*, with the root given a distinct **shape** rather than a slightly darker fill, and every
label carrying a status glyph so the map reads in greyscale.

**Dashed borders are a conventional state style.** G6's element-state documentation uses
exactly this for an error state: a `lineDash: [4, 4]` border plus a lighter fill plus a badge,
stacked as a named state on top of the default style.

### What to do

The cheapest change that would actually read, in order of effect:

1. **Change the fill, not the ring.** A retired part should be a different, desaturated fill
   with a heavier stroke, so it differs in lightness as well as hue from the healthy orange.
   The ring can then go back to meaning one thing.
2. **Give it a glyph.** A small mark on the node, or the lifecycle word under the label
   beside the MPN, so the state survives greyscale, colour blindness and a screenshot taken
   away from any legend.
3. **Style the edges into it.** Dash or tint every edge whose endpoint is a retired part, and
   keep the existing dash for *historical* by distinguishing the two: one is dashed and grey
   for **was here**, the other should be dashed and warm for **is here and going away**.
   Line width survives everything, so weight is the safer of the two channels.
4. **Put a legend on the screen.** Four rows. The current graph has no key at all, so every
   encoding on it is folklore.

None of that is large. All of it is in one file.

### Sources

- [Rendering Lineage DAGs with Graphviz](https://www.provenance-tracking.com/storage-indexing-query-optimization/lineage-visualization-and-reporting/rendering-lineage-dags-with-graphviz-in-python/) — do not encode six variables at once; colour plus marker as a mechanical rule; border weight survives greyscale.
- [WCAG 2.1, Understanding Success Criterion 1.4.1: Use of Color](https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html) — colour must never be the only visual means of conveying information.
- [G6, Element State](https://g6.antv.antgroup.com/en/manual/element/state) — named states stacking fill, stroke, `lineDash` and a badge, which is the shape of the change here.
- [erdos-frontier-atlas, accessible legend commit](https://github.com/techno-optimist/erdos-frontier-atlas/commit/e47de0fe80264789aba887add54aeb3be5f32275) — a worked before-and-after: lightness as well as hue, shape for the special case, glyphs on labels, and an in-figure legend.

---

## R8 The cross-team response is the problem statement, and one desk answers everything

**New finding, and it outranks everything else in this file.** Every product line, every
proposal and every change request in the demo is approved by engineering. Procurement and
production never appear.

### What the scenario asks for

The assigned topic, verbatim from [SCENARIO-B.md](SCENARIO-B.md):

> A critical component just went end-of-life, affecting 3 product lines. The engineering team
> needs approved substitutes within 48 hours. **How does your tool coordinate the cross-team
> response — design validates alternatives, procurement checks availability, and production
> confirms assembly compatibility?**

Three departments, named. SCENARIO-B's own table maps them onto rules that already exist:
design takes the eight electrical rules, **procurement takes `availability`**, and
**production takes `footprint`**.

### What the code does

**There is no production desk.** `api/store.py:71` reads
`ROLES = ("engineering", "procurement", "quality")`. The third department the problem statement
names does not exist in the product, and cannot be assigned, granted or signed as.

**The two rules that are production's route to engineering.** `roles.py:30-31` sends both
`footprint` and `footprint_compatibility` to `("engineering",)`.

**A clear answer is hardcoded to engineering.** `review.choose()` has two passes
(`review.py:152-172`). The first returns any candidate that clears every rule with
`roles=("engineering",)` written into the call. Only the second, reached when **nothing**
clears, asks `decision_roles(gate)` and can route elsewhere. So a department is consulted only
when the answer is a compromise, and never when it is good.

**The change request does the same thing.** `change._approvals_for` (`change.py:293-309`)
collects the desks that own *failing* rules and falls back to `DEFAULT_DECISION_ROLES`, which is
engineering, when nothing failed. All three cards therefore read *APPROVALS · engineering*.

**And the matrix agrees, by the same rule.** `matrix.py:105-117` gives a cell the desks that own
its failures, with the comment *"a cell that raises none is owned by nobody."*

**The seeded world cannot fail procurement's rule.** `availability` fails when stock is below
`requirements.min_stock`, which defaults to 100 (`engine/models.py:468`). Every candidate has
thousands at JLCPCB, so it passes. A lifecycle concern is reported as *satisfied* with a margin
note, not as a failure.

**The candidate search cannot fail production's rule either.** `_search_query` looks for parts
in the retiring part's own package, so a SOT-23-5 candidate is never sourced. The only proof
that a package change breaks the board lives in a test.

**Net effect on screen:** grep the frontend and the words *procurement* and *production* appear
exactly once, in a code comment in `ReviewLanes.tsx:72-73`. On the whole ten-step run-through,
no department but engineering is ever named.

### Why the current framing is wrong

FLOW.md §5 says *"in the seeded world an approved part clears every board, so every column
currently ends at engineering. See DEFERRED — it is a flow decision, not a defect."* DEFERRED
carried it at 🟡 with *"the routing exists and is enforced at the HTTP boundary; the seeded
world just does not reach it."*

Both are too soft, for two reasons. The routing table is missing a third of the scenario, which
is not a property of the seeded world. And the question asked is *how does your tool coordinate
the cross-team response*, so a demo in which one desk approves everything does not answer it.
This is now 🔴.

### Three ways out, and they are not alternatives

**1. Attribute every rule to its department, pass or fail. Do this one first.**

The engine already checks all three departments' constraints on every candidate. What it never
does is *say so*. Grouping the verdicts by desk on the trace and on the change request would
read:

```
DESIGN            8 checks, all clear · 35 °C thermal margin
PROCUREMENT       availability clear · 1,020,639 in stock at JLCPCB, an approved source
PRODUCTION        footprint clear · SOT-223 → SOT-223, drop-in, no layout change
```

Every one of those is already computed and already true today. This is an attribution and a
presentation change, not engine work, and it turns the strongest sentence in SCENARIO-B —
*every candidate is checked against all three departments' constraints simultaneously, before
anyone sees it* — from a claim into a screenshot. It is also the honest version of the pitch:
the value is that the round trips were **removed**, not that three people signed.

**2. Add the production desk and move its rules to it.** `ROLES` gains `production`;
`footprint` and `footprint_compatibility` move there in `roles.py`. `tests/test_roles.py`
already asserts every rule appears in the table, so the change is caught if it is half done.
The seed's second account can hold quality **and** production, or a third account can exist.

**3. Make one line stop at a different desk, so the handoff is real on stage.** Two honest ways,
and neither invents anything:

- **Procurement.** Give one product line a `min_stock` that reflects its volume. A gateway
  shipping 5,000 units a quarter needs 5,000 parts, and TLV1117LV33DCYR has 1,133 in stock at
  JLCPCB. That is a genuine availability failure and it routes to procurement today, with no
  code change beyond putting the figure on the operating profile.
- **Quality.** Have one line's best answer be a part that is electrically fine and not on the
  approved manufacturer list. `LD1117-3.3` already is exactly that on all three boards; it loses
  only because a clear candidate exists. Removing the clear candidate from one line's reachable
  set, or ranking on the approved list rather than on clearance, makes the *"this is not your
  decision"* beat fire.

**decision.** Whether to do 3 at all is a real choice. Option 1 alone makes the cross-team claim
visible and provable without touching the world; option 3 makes it dramatic and costs a change
to the seeded data that has to be defensible when a judge asks why that number is there. My
recommendation is 1 and 2 now, and 3 only if the answer to *why does the Gateway need 5,000
parts* is a sentence he is happy to say.

### One consequence for an existing row

**The 🟡 "an engineer can qualify a part alone" becomes 🔴 the moment any of this is fixed.**
`roles.py:20` addresses `part_qualification` to engineering *and* quality with the words *"it
needs both"*, and the decision row carries one state and one `decided_by`, so whoever answers
first settles it. Today that never fires because no decision ever reaches two desks. Fix the
routing and it fires on stage, in front of the person asking how the cross-team response is
coordinated.

---

## R9 Whether a model should make the board change, and gpt-6-astra

**Finding 7, second half.** *"Are we not using the agent to change the part in real time?"*

### What actually makes the change today

No model touches the board. `kicad/board.py:158-215` writes a swap specification as JSON, runs
`swap_footprint.py` inside the KiCad container through `pcbnew`, refills the zones on both
copies in separate interpreters, and runs DRC before and after. The pad-to-net mapping comes
from `kicad/catalogue.py`, a table of datasheet readings, mapped **by function** rather than by
pad number. It is deterministic, it is tested, and the original file is never written to.

That is the right architecture and it is the pitch. A model that edited a board file would be
a model producing a compatibility outcome, which is the one thing this product says it never
does. So the answer to *why not let the agent do it* is: because then nobody could check it,
and the whole claim rests on the check.

**What is missing is not agency, it is visibility.** The swap happens in a scratch directory in
under a few seconds and the screen shows two pictures at the end. Nothing narrates the four
steps that actually ran, and `RequestCard` does not even ask for them
([R4](#r4-the-board-in-the-change-request-and-exporting-it)). Showing *placing the part ·
carrying 3 nets by function · refilling 687 zones · running DRC* as four real events would give
him the "watch it work" beat, and every line of it is a thing that happened.

### gpt-6-astra, on the record

Released 3 September 2026, API id `gpt-6-astra`. Standard pricing is $10 per million input
tokens and $50 per million output, with cached input at $1. Context is 1,050,000 with 128,000
max output, knowledge cutoff 30 April 2026, and `reasoning.effort` runs low, medium, high,
xhigh, max, defaulting to low. **Modalities are text and image in, text out.** Responses-API
tools include web search, file search, code interpreter, hosted shell, apply patch, computer
use and image generation. Enterprise access is off by default at launch and it is the first
model at OpenAI's Critical cybersecurity threshold, so availability is gated.

Two of its published numbers are relevant here, both self-reported by OpenAI:

- **BenchCAD 95.9%** geometric overlap, which tests reconstructing 3D objects from multi-view
  renders **by generating CAD code**, against 83.3% for GPT-5.6 Sol. That is the closest
  published evidence that a model can produce correct geometry from pictures.
- **ScreenSpot-Pro 92.7%** with no tools, and OSWorld 2.0 at 72.6%, which are GUI-grounding and
  computer-use scores.

Swapping it in is a configuration change on our side: `llm.py` speaks the OpenAI-compatible API
and `CONTINUITY_LLM_BASE_URL` plus `CONTINUITY_LLM_API_KEY` already select the provider. The
cost is the consideration, since DeepSeek is roughly two orders of magnitude cheaper per token
and the EOL flow makes three model calls.

### Where it would actually help, and where it would not

**Would not: making the swap.** See above. Deterministic today, and better for it.

**Would: reading a pinout that is a picture.** This is the concrete win and it closes a hole the
product currently announces. `kicad/catalogue.py` has no entry for `LD1117S33TR` because **ST
publishes its pin connections as a figure, and a figure is not extractable text** — so asking
for that part's board consequence refuses by name, and RUNNER lists that refusal as correct
behaviour. Astra takes image input. A datasheet figure could be read into a pad-to-function
map, **and the engine would still verify it**: the swap script maps by function, DRC runs
before and after, and a wrong reading shows up as broken connections rather than as a confident
answer. That is the model proposing and the engine checking, which is exactly the division this
product already defends.

**Would, more speculatively: repairing a layout when the drop-in breaks.** When a SOT-23-5
substitute takes unconnected items from 1 to 4, somebody has to move copper. That is real design
work, `apply patch` and `hosted shell` exist as tools, and the board file is text. It is also a
much bigger claim than this demo needs, and the honest floor — *this board needs layout work
before the substitution can ship*, which is what the screen says today — is already a good
answer.

**Recommendation.** Do not move the swap to a model. Consider Astra for the pinout figure, where
it converts a stated limitation into a capability with the verification already in place, and
decide it on cost rather than on capability.

### Sources

- [GPT-6 Astra model page, OpenAI API](https://developers.openai.com/api/docs/models/gpt-6-astra) — context, output, tools, effort levels.
- [GPT-6 Astra: A new generation of intelligence, OpenAI](https://openai.com/index/gpt-6-astra/) — BenchCAD 95.9%, ScreenSpot-Pro 92.7%, OSWorld 2.0 72.6%, rollout and pricing.
- [GPT-6 Astra System Card](https://deploymentsafety.openai.com/gpt-6-astra) — Critical cyber threshold and the deployment restrictions that come with it.
- [LLM Stats, gpt-6-astra](https://llm-stats.com/models/gpt-6-astra) — the pricing and context table, and the note that the benchmark figures are OpenAI's own rather than independently verified.

---

## R10 Making the board change visible when the change is tiny

**Finding 7, third half.** Zoomed in, the before and after pictures look identical.

### Why they look identical

Because almost nothing moved, and that is the correct answer. AMS1117-3.3 and NCP1117ST33T3G are
both SOT-223, `catalogue.footprint_for` returns the same footprint, and the swap therefore
changes the footprint's identity and its value text and leaves every pad where it was. The
product already says this out loud: *"The pads it lands on are the pads that are already
there."*

The problem is that **two identical pictures do not read as a computed result, they read as
nothing having happened.** The demo asks a viewer to take *no change* on trust at exactly the
moment it is trying to prove the substitution was checked against a real board.

### What the tools in this space do

Every KiCad diff tool solves this the same way, and none of them relies on the reader comparing
two pictures by eye.

- **Tinted overlay.** `kirin` offers five modes and the load-bearing one is *Red/Green*: base
  tinted red, head tinted green, **unchanged geometry grey**, so removed content is red and
  added content is green. `uchan-nos/kicad-diff-visualizer` uses the same idea with white for
  no difference, red for old-only and blue for new-only.
- **Blink.** `kirin` alternates the two on a timer and says plainly what it is for: *"good for
  spotting moves."* It is the astronomer's blink comparator and it is very hard to beat for
  finding a small change in a busy image.
- **Swipe.** A draggable divider, in `kirin`, `kicadiff` and `lukaj`. Worth knowing that the
  KiCad forum's own verdict on it is that it *"might require some passes to spot the
  difference"* and that something colour-based *"gives a much quicker overview of changes"*.
- **An SVG filter.** `KiCad-Diff` and `kiri` do the highlight with a `feColorMatrix`, which
  matters to us because **we already render SVG**. `BoardConsequence` puts two `<image>`
  elements in two `<svg>` viewports; tinting one and compositing them is a filter and a blend
  mode, not a new pipeline.
- **A structural diff beside the picture.** `kicadiff` prints what changed as text —
  `~ R1 value: 330 → 470`, and for boards a `Nets` section listing pads that were rewired,
  `R1.2: GND → /VCC`. It also runs `kicad-cli pcb drc` on both sides and reports the delta as
  new, fixed and unchanged violations.

### What to do here

**Add a third mode beside BEFORE and AFTER, and make the tiny difference legible rather than
asking anybody to find it.** In order of value for the effort:

1. **A tinted overlay.** Same crop, both renders composited, unchanged geometry grey. For our
   case it would light up the silkscreen value text and nothing else, which is the story: *the
   only thing that changed on this board is the part number printed on it.* That is a far
   stronger frame than two pictures that look the same.
2. **Say what changed in words, next to it.** We already know: the footprint identity, the value
   text, and the pad-to-net mapping. `outcome.wiring.wired` carries the mapping and
   `outcome.footprint.from/to` the identity, and neither is on screen. Two lines of text turn
   *looks identical* into *identical except this*.
3. **Show the counter-example.** The SOT-23-5 case exists only in
   `tests/test_boards.py`. A judge asking *how would I know if it did break* has nothing to look
   at. The strongest version of this pane shows the drop-in beside the part that does not fit.
4. **Blink, if a mode is wanted for the stage.** Cheap to add once both renders are in the DOM,
   and the most legible of the lot on a projector.

None of this needs a new KiCad invocation. Both SVGs are already in the response.

### Sources

- [markhakansson/kirin](https://github.com/markhakansson/kirin) — five compare modes, and the description of Red/Green and Blink.
- [sksat/kicadiff](https://github.com/sksat/kicadiff) — side-by-side, overlay and swipe, plus the structural component and net diff and a DRC violation delta.
- [Gasman2014/KiCad-Diff](https://github.com/Gasman2014/KiCad-Diff) and [leoheck/kiri](https://github.com/leoheck/kiri/) — the `feColorMatrix` SVG highlight approach, which is the one that fits our existing renderer.
- [uchan-nos/kicad-diff-visualizer](https://github.com/uchan-nos/kicad-diff-visualizer) — white / red / blue tri-colour convention, built on `kicad-cli` alone.
- [PCB diff with custom tool and kicad-cli, KiCad forum](https://forum.kicad.info/t/pcb-diff-with-custom-tool-and-kicad-cli/46664) — practitioners on why swipe is weaker than colour for spotting a small change.


---

## R11 Showing four desks, and demoing them with one presenter

**His question:** how do we show the department breakdown properly, and does it need multiple
sign-ins?

### The answer was already written, on 4 September

[SCENARIO-B.md](SCENARIO-B.md) settled it and nobody built it:

> **Each role sees the same verdict in its own terms. One finding, three renderings — a view
> layer over one shared result, never three engines.**

The external pattern literature says the same thing in its own words: *"design requester,
approver, admin, and observer views with the same canonical state but role-appropriate
actions."* So the breakdown is **not** four computations, four panels or four pages. It is one
result, grouped by the desk that owns each part of it, rendered wherever that result already
appears — the trace, the lane, the change request, the matrix cell. That is item 33.

The same document also answers *how many desks*: a change control board's composition *"should
mirror the change's blast radius: engineering, quality, manufacturing and procurement at
minimum."* Four, which is what he chose, and manufacturing is the topic's production.

One question from RESEARCH-BRIEF-2 §5 was never answered and can be closed now: *"can one
finding legitimately have several owners? Round one said our one-department-per-cell tagging is
an oversimplification."* Yes, and the code already models it — `part_qualification` is
addressed to engineering **and** quality. It is not an oversimplification to remove; it is a
case the rendering has to handle, so a rule with two owners appears under both.

### Does it need multiple sign-ins?

**Yes, real ones, and no, not by logging out.** Those are two different questions and the
literature separates them cleanly.

The WordPress *View as Role* module states the distinction better than anything else found:
a **view-as** simulation is *"visual only — it doesn't grant or remove actual permissions"*
and *"any actions you take are still done as you"*, whereas **login-as** *"actually switches
accounts"* and *"can perform actions as that user"*. Its own comparison table ends: *"use View
as Role when you want to check what a role can see. Use Login As User when you need to act as
a specific user."*

Continuity needs to **act**. A desk signing a change request is the entire beat, so a
simulation is not an option: it would be a drawn affordance that cannot be used, which is the
rule we already hold.

What that does not mean is signing out on stage. The pattern every reference implementation
uses is a **principal switcher in the header holding several genuine sessions**:

- `treasury-rfq-demo` walks a thirteen-step multi-party trade with *"switch principals using
  the dropdown in the top-right of the header"*, and is explicit that each view fetches
  *"independently with its own credentials, no god-view shortcuts."* A direct API call from
  the wrong principal *"returns 403 ACL_DENY — and the denial itself is logged."*
- The IAM Gatekeepers PAM walkthrough uses **role pills in the top-right**: *"switch roles
  using the pills in the top-right header to see how the same data looks from each
  perspective."*
- `RolesTab` solves it the heavy way, one isolated browser session per role, *"without
  constantly signing in and out."*

For us that is: keep a session per seeded account, switch with one control, always show the
current desk, and leave the 403 exactly where it is. Item 37.

### The frame worth stealing

`treasury-rfq-demo` also has a **multi-pane toggle**: the same workflow, four principals at
once, each pane fetching with its own credentials. Its own note on why it matters is the
sentence to take:

> *"The empty Crestline pane is the most concrete evidence that scoping is real, not
> cosmetic."*

Applied here: one change request, four panes — design, procurement, production, quality — each
showing that desk's own verdicts and its own button, and a desk with nothing to answer showing
nothing to answer. That is the cross-team response in one frame, it is impossible to fake, and
it makes the point without anybody switching anything. It also answers
[R3](#r3-the-changes-page-is-doing-three-jobs): this is what the right-hand side of a
master-detail `/changes` should hold.

Their presenter overlay is worth noting too — jump to a beat, hard reset, toggle the panes —
because `./demo.sh` already rebuilds the world in three seconds and that is the same idea at
the shell rather than in the app.

### How the approvals should actually work

The approval-pattern literature gives the vocabulary, and it changes one thing in the plan.

**Parallel, all-must-approve. Not sequential.** The published comparison is direct:
first-response *"reduces waiting, but the first valid response becomes decisive. It is unsafe
when two independent controls or separation of duties are required."* That is exactly
`part_qualification`, which `roles.py` addresses to two desks with the words *"it needs both"*,
and which `answer_decision` resolves with `allowed.intersection(user.roles)` — first response.
All-must-approve *"keeps the request in review until every current reviewer approves."*

Sequential review is the other option and it is the wrong one here, for a reason specific to
this pitch: sequential *"expresses ordered authority clearly, but every stage adds latency"* —
and the round trips are the thing this product claims to remove. The chain in *Chained
Collaboration* is the chain of **functions**, and the whole argument is that Continuity checks
all of them at once. The approval should read the same way.

Four more things from the same sources that the build should honour:

- **Authorisation is per transition, not per login.** *"Every state change should verify three
  things: the actor has permission for this transition, the transition is valid from the
  current state, and all prerequisite conditions are satisfied."* `answer_decision` does the
  first two; the third arrives with item 35.
- **An approver inbox is a named pattern**, not an invention: *"a `/approvals` page listing all
  pending tasks for current user"*, each carrying full context, the prior approvals in the
  workflow, and the decision controls. Item 36.
- **Escalation must be non-decisional.** *"It may notify, delegate, or flag the request, but
  only the authorised decision transition changes approval state."* Worth remembering when the
  outbound approval request is finally built.
- **Do not encode approval progress in colour or position alone.** *"Do not rely on color,
  initials, icons, or timeline position alone to communicate which approvals are missing or
  complete."* Two of four signed has to be readable as words.

### The one thing the research says we should not do

WORKBUDDY.md already reached the conclusion the external patterns support, for a different
reason: *"putting a desktop app, a mailbox and a Slack workspace into the critical path of a
live demo risks the larger number to chase the smaller one."* Cross-desk delivery over an
outside channel is the real-world answer and the wrong demo-day answer. Build the in-app inbox
and the switcher; leave the channel to DEFERRED.

### Sources

- [SCENARIO-B.md](SCENARIO-B.md) — our own 4 Sep research: one finding several renderings, the CCB's composition, and the standard that a released design is approved before implementation.
- [Approval workflow UX Pattern, UX Patterns Guide](https://uxpatternsguide.com/patterns/approval-workflow/) — route semantics, the state list, role-appropriate views over one canonical state, and the accessibility rule about not encoding progress in colour alone.
- [Approval Workflow Guide, Playcode](https://playcode.io/blog/approval-workflow-guide) — the first-response versus all-must-approve versus sequential comparison, and escalation being non-decisional.
- [Approval workflow blueprint, Vladimir Siedykh](https://vladimirsiedykh.com/blog/approval-workflow-blueprint-routing-audit-permissions) — authorisation as a per-transition contract; explicit, scoped, recorded overrides.
- [treasury-rfq-demo](https://github.com/abhinavg6/treasury-rfq-demo) — principal switcher, per-principal credentials with no god view, the multi-pane frame, and the empty pane as proof.
- [View Admin as Role, Switchboard](https://docs.wpswitchboard.com/modules/user-management/view-admin-as-role/) — the view-as versus login-as distinction, stated as a comparison table.
- [IAM Gatekeepers PAM demo](https://identitygatekeepers.com/pam-demo/) — role pills in the header, and a two-of-three multi-party approval walkthrough.
- [Approval workflows and multi-step routing](https://www.vibeweek.ai/grow/approval-workflows-multi-step-routing-chat) — parallel groups with a required count, and the approver inbox surface.


---

## What was not researched

**Finding 1**, the board pane saying *Drawing the board…* while it loads a stored render, is a
one-word change at `review/BoardPane.tsx:100` and needs nothing but doing.
