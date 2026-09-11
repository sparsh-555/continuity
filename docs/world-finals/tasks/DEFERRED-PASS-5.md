# Task · DEFERRED pass 5 — the page the review lives on

> **Status: pass 5 is complete, 11 September.** Eight items, P20 to P27.
>
> Three things the building of it exposed that were not on the list, and the third is the one
> that mattered:
>
> - **The trace was drawn at a pace only the replay had.** `pacedDelay` was called from the
>   hydration effect and from nowhere else, so clicking START THE REVIEW put every frame on
>   screen in one burst — a cached run looks instantaneous — while leaving the page and coming
>   back showed the paced version. That is exactly the split Sparsh described, and it was two
>   defects rather than one: the pacing was never on the live path, and the replay restarted
>   from its first frame on every mount.
> - **The stored trace had no order, and the sort that claimed to restore it had never had
>   anything to sort by.** `review.replayFrames` sorts by `seq`; the frames `api/replay`
>   rebuilds from `decisions.document` carry no `seq` at all. The read-back is per decision, so
>   a company-wide review replayed as one board, then the next, then the next. The run's own
>   order is now recorded as it streams (P24), which is the same session's second finding.
> - **The board consequence lost its reader for a few hours.** P25 took the board off the
>   change request at Sparsh's request, and `request.board` was the only thing the card
>   rendered it from — so a KiCad run was happening in the background and writing a field no
>   screen showed. He asked for it back the same day, and it is back (P25a below).

Passes 2 and 3 made the product correct. Pass 4 made it say what it did. This one is about the
page the whole scenario happens on: `/changes` was a wide column of ten-pixel text on an
animated background, and the review inside it was the only thing on the screen that mattered.

**Repository** `~/Documents/GitHub/continuity`. **Baseline** main at `4192148`, working tree
clean. **Suite** at the end of the pass: 1231 with a database · 53 frontend · lint clean ·
browser spec green in 58 s · 622 recorded calls (re-count before quoting any of these).

The rules are the ones in [`DEFERRED-BRIEF.md`](DEFERRED-BRIEF.md) and the top of
[`BUILD.md`](../BUILD.md). Test first, watch it fail, fix, watch it pass, revert the fix and
confirm the test fails again. One commit per item, `type: description`, no scope. Rows move to
*Resolved here* with what fixed them, and the counts are recounted by counting.

## The decisions, taken with Sparsh on 11 September

1. **`/changes` takes the design workspace's frame.** A solid ground with no animated board
   behind it, the viewport held rather than the page scrolling, two panes that scroll inside
   themselves, and the product's own type scale rather than 10px ad-hoc sizes. The notice stays
   beside the review it raised instead of a screen above it.
2. **Three lines per lane while a run is arriving, one when it stops.** He chose the rolling
   window over auto-expanding the lanes: the trace has to be visible on all three boards at
   once, which is the simultaneity, without turning the page back into the column of scrolling
   traces it was rebuilt to stop being.
3. **`/approvals` goes.** It was a second place to sign the same decisions the lanes already
   ask for, and the count of what a desk owed was on the page nobody was looking at. The rail
   badge moves to CHANGES and the page gains a strip at the top naming what is waiting.
4. **Four ticks per row, not a sentence.** *0 of 4 signed. Waiting on DESIGN, PROCUREMENT,
   PRODUCTION and QUALITY* is the same statement in words, and the desk names stay beside the
   marks so the row survives greyscale and a projector.
5. **A before-and-after timeline for the missing round trips**, shown once above the lanes
   rather than on each of the three cards. It was three identical paragraphs on three documents
   and read as boilerplate; it is the same three numbers every time, because it is about the
   desks and the handoffs rather than about the board.
6. **The rejected candidates get standing blocks**, each with the sentence that killed it and
   the failing check printed in full. He went looking for them, found a closed disclosure
   triangle, and concluded they had been deleted with the matrix page.
7. **The board leaves the card.** It lives on the product line's own BOARD pane, where it has
   its own button and its own reason to be. **Reversed the same day**: a background KiCad run
   whose result no screen shows is a cost with no reader, so it is back on the card and the
   pane keeps its own on-demand placement.
8. **The invite is real, and it is enforced.** Tick projects, name the person, and the tick
   decides what they can open. See P27.

## Order

P20 first, because removing a page invalidates documentation in four files and the citations
are cheaper to fix while nothing else is moving. P21 and P22 are the two that change what the
recording looks like. P24 is backend and independent of the rest, so it lands on its own.
P23 and P25 both rewrite `ReviewLanes`'s render, so they are serialized. P26 and the documents
come last.

Files shared between items — `review/ReviewLanes.tsx` (P22, P23, P25), `review/laneState.ts`
(P22, P23), `routes/changes.tsx` (P20, P21, P22) — mean these are serialized commits from one
pair of hands, not parallel agents.

---

## P20 · The approvals page folds into the page the change is on

**Why it went.** `/approvals` was built because three of the four people who must sign a
substitution had no way to find it. That was true when the decision lived only on a product
line's page. It stopped being true when the lanes learned to hold the question, and nobody
noticed: two screens were asking the same question and taking the same answer, and the count of
what a desk owed sat on the one the reader was not on.

**What replaces it.** The rail badge moves from the removed entry to **CHANGES**, still counting
only `mine`. `/changes` gains a strip above the panes naming what is waiting on this desk, each
row carrying the product line, the part, the rule being accepted, four ticks, and a link to the
notice that raised it. **One component does the ticks**, `review/Signatures.tsx`, so the strip,
the lane and the change request cannot disagree about who has signed.

**Done when.** A desk with nothing waiting sees no strip and no badge; a desk with two sees
three ticks' worth of truth on each row; signing from the lane updates the strip without a
reload. Verified by driving it with four desks.

---

## P21 · `/changes` is a screen, not a column

**The defect, as Sparsh found it.** *"The notice text is too small even on full screen. The
overall UI design looks bad for a page that contains the review — the pulsating electric
background is distracting."*

**What changed.** `ownsTheViewport` (was `isWorkspacePath`) gains `/changes`, which is one
predicate doing both halves: `AppShell` gives it the solid ground the design workspace has, and
`AppFrame` stops painting the animated board behind it. `Page` gains a `fill` variant so the
header stays put and each pane scrolls inside itself. Every 10px and 11px size on the page moves
onto the design system's own scale — `text-data-tabular` at 13px for data, `text-body-md` at
14px for prose.

**Why the background and not *a* background.** The rule the codebase already states is that
motion belongs behind a graph the run is drawing. Behind a column of prose it is decoration, and
a reader trying to follow a trace on it is reading through interference.

**Done when.** `/changes` scrolls inside its two panes and never as a page; the left pane holds
the notice while the right pane holds a trace taller than the window; the header never moves.

---

## P22 · One pace, for the run and for the replay

**The defect, as Sparsh found it.** *"The trace when I first click on 'Start a Review' still
runs extremely quickly. The actual checks streaming is not visible at all. The streaming
component is only visible when the review page opens up... and reloads every time I come back to
the changes/ page instead of being there."*

**Three faults behind two sentences.**

1. `pacedDelay` was called from the hydration effect alone. The live path went straight from
   `runReview`'s `onFrame` into the reducer, so a cached run landed in one burst.
2. `pacedDelay(position)` ignored its input's length, so a two-word narration and a full verdict
   had the same dwell — which is what made it read as a machine printing rather than as a run
   being followed. It now takes the line's text and scales with it, bounded at both ends.
3. Nothing remembered that a notice had already played, so every mount replayed it from frame
   one.

**One queue for both paths.** Frames from the live stream and frames from the database go into
the same array and are drawn by the same `setTimeout` chain, so a running review and a recorded
one cannot come to mean different things on the way to the screen. The frame is taken out of the
queue as a value rather than read from a cursor inside a `setState` updater, which is the
mistake that crashed this component on 11 September.

**Remembered in `sessionStorage`, not in a module.** A module-level set survives client-side
navigation and dies on F5, which is the wrong line to draw: an accidental refresh four minutes
into a walk-through would put the whole review back to its first frame. Session scope is what a
reader means by *come back to the page*. Every read and write is guarded, because private
windows make `sessionStorage` throw.

**Measured, on the rebuilt world:** a full three-line review takes **80 seconds** at the current
constants, with all three lanes moving throughout. `FRAME_FLOOR_MS` and `FRAME_CEILING_MS` in
`review/laneState.ts` are the only dial, and nothing else in the product delays anything.

**Done when.** Clicking START THE REVIEW shows lines arriving rather than appearing; leaving and
returning, and refreshing, shows the review at its end rather than starting again; SKIP TO THE
END is present for the whole of it.

---

## P23 · A lane shows its last three lines while it is still arriving

**Why.** One line replaced every few hundred milliseconds is motion without information: the
reader sees that something is happening and cannot read what. Three show the trace moving. The
row's header says nothing while the run is on, because repeating the newest line above the block
that contains it is the same sentence twice.

**Done when.** All three lanes visibly advance at once; a lane that has stopped shows one line
and its verdict; expanding one still shows the whole trace.

---

## P24 · The run's own order is recorded, so a replay interleaves

**The defect, found while checking P22 in the browser.** `replayFrames` sorts by `seq`. The
frames the read-back rebuilds from `decisions.document` carry no `seq`, because the
reconstruction is per decision — so the sort was a stable no-op and a company-wide review
replayed as *Cabinet controller, then Gateway, then Sensor node*. The simultaneous answer is the
entire claim of Scenario B, and the recording would have shown its opposite.

**Why it cannot be reconstructed.** The interleaving is a fact about the run. Per-decision
records do not contain it, and interleaving them by position would be inventing an order that
nobody observed.

**What changed.** `notices.review_trace` (jsonb, additive, `IF NOT EXISTS`), written once when
the stream ends — in a `finally`, because a run somebody stopped still happened. The read-back
serves the recorded frames when it has them, each keeping the run's `seq`, with the unmarked
opening lines carried on the first row where the client reads them. A notice that ran before the
column existed falls back to the reconstruction, one lane at a time, which is what it had.

**A question that has been answered is not re-asked.** The recorded trace holds the frame the run
asked with, and it stays there after somebody signs. Whether it is still a question is a fact
about the decision, read from the decision — the same rule `/lines` already follows.

**Done when.** Three boards advance together in a replay; every frame carries the run's own
sequence number; an older notice still replays.

---

## P25 · The card loses the board, and the rejected parts stand up

**What left.** `BoardConsequence` comes off `RequestCard`. The board is on the product line's own
BOARD pane, where the toggle is the question and the picture has somewhere to live.

**What arrived.** `CONSIDERED AND REJECTED` was a disclosure triangle reading *N of checks*.
Sparsh went looking for the rejected parts, found a closed row, and concluded the matrix's
content had gone with the matrix. Each rejected candidate now has its own block: the sentence
that killed it, and **the failing check printed in full** with its desk. The checks that passed
are counted and folded away, because twenty-two satisfied verdicts per candidate buries the one
line worth reading.

**One consequence, and it is not resolved.** `request.board` was what the card rendered, and
nothing reads it now: the background KiCad placement the run fires for each line produces a
field no screen shows. Open row below.

**Done when.** Every rejected part is visible without a click, with its failed check named; no
board picture appears on any card.

---

## P25a · The board comes back, and says what it is doing while it does it

**Two requests and one defect, all from watching the pass run.**

The board is back on the change request. The argument for taking it off was that the question
it answers belongs to the product line, and that argument is still true — the BOARD pane keeps
its own placement and its own button. What was wrong was the cost: `attach_board_consequence`
fires a KiCad run per line in the background, and the card was the only thing that ever
rendered the result. **A background job whose output no screen shows is a cost with no reader**,
and that is what it had become for a few hours.

**And the ten seconds are now visible.** A cold board takes that long — read the placements,
place the part and carry its nets, refill the zones, run DRC twice, render two pictures — and
the pane sat on *PLACING…* for all of it and then put everything on screen at once. The
operations were already timed for the WHAT RAN block; `board.consequence` now takes an
`on_step` callback fired from the worker thread as each one finishes, and
`POST /lines/{id}/board/consequence/stream` sends them and ends with the identical payload the
plain endpoint returns. **The steps on the wire are the same objects that end up on the
result**, asserted by a test rather than by a comment, and measured on the real world at 1.7 s,
2.7 s, 5.3 s, 9.1 s and 11.0 s.

Sparsh's other two asks landed with it: **SKIP TO THE END is gone**, and a finished review no
longer replays on arrival at all, which is what P22 half-did and this finished. That control
only made sense to somebody who knows they are watching a playback.

---

## P26 · What the missing round trips are worth, drawn

**Why.** *"It is the same for every board except the recurring cost, and it looks like what it
will cost rather than what it is saving."* Both halves were right. The paragraph was identical on
all three cards because it is about the desks, not the board — and a sentence about time is the
one thing a reader cannot check at a glance, because *5.2 hours and 2.7 days* reads the same
whether the queueing is most of it or none of it.

**What it is.** Two timelines on one scale: one change passed desk to desk, with a queue between
each pair, against this change, examined by every desk at once. The queue dominates the drawing
because it dominates the elapsed time, which is the finding. Each queue is derived from the
stated total and the counted crossings rather than split by eye, so the drawing cannot disagree
with the sentence underneath it. `roundTripLegs` is the pure function and has its own tests,
including the zero-crossings case that would otherwise put `Infinity` in a width.

**Shown once.** Above the lanes on `/changes`, because it is the same three numbers on every
board. On `/lines/:id`, where the card is the only thing on screen, it stays on the card.

**Done when.** The drawing is to scale; the constants are named with their sources in the same
block; no card in the company view repeats it.

---

## P27 · A project is shared, and the share is a grant

**The question this answers.** *How do teams share the projects* is the first thing a judge
asks about a cross-team product, and every screen showed the work while saying nothing about
the team. Four desks signed one change and the sharing had to be taken on faith.

**Why it is not a panel that lists people.** The first draft of this was a roster, and it
would have been a label. The searches said the same thing twice: the teams that lost ground
had a collaboration surface that was not real, and one writeup states plainly that its role
identity was simulated for the demo. The codebase had already taken that position in
`create_user`'s docstring — *an invite button that did nothing would be worse than no button* —
which is why `add_user_to_organisation` had a store method, a seed call and passing tests and
no screen at all.

**The boundary moved.** Everything authorised on `org_id`, which answers *is this your
company's work* and cannot answer *is this yours*. Since today a product line is visible
because there is a `line_access` row for it. `lines_for_user`, `line_for_user` and
`lines_exposed_to` take a required `user_id`, so a caller that forgot stops at a type error
instead of widening what somebody sees; 26 call sites, and two internal ones that genuinely
mean the whole company call `lines_in_org` / `line_in_org` so the difference is visible where
it is made. `PATCH /lines/{id}` was renaming projects before it checked whether the caller
could open them, which is closed.

**The demo is unchanged and the invite is real.** The seed grants every desk every line, so
all four see all five. `priya@northwind.example` is seeded on her own with nothing, so the
invitation has somebody to bring in on every replica of the world. Verified on the running
world: she is invited to three projects, signs in to three rows, and gets a 404 on the fourth,
while all four seeded desks still see five.

**What it does not do, and the screen says so.** No invitation email. An address nobody has
signed up with is refused with a sentence rather than a 201, because there is no token, no
expiry and no acceptance route behind one.

---

## P28 · The changes page is three panes, and a signature has one home

**What Sparsh found driving it.** The change request sat under the lane that produced it, so the
third product's document was a scroll below the first and a reader comparing two of them lost
the trace they came from. And a desk's own work was in three places at once: the question and
the two buttons on the lane, the same four ticks again on the document, and the count of what
it owed in a pane at the top.

**It is the design workspace's shape now**: the desk on the left, the run in the middle, the
document on the right. Signing happens once, in the pane named after what the reader owes, and
the button names the desk rather than saying *my desk*, because four desks sign from this page.
A refusal lands beside those buttons and never on the board, since a 403 is a fact about the
desk and painting the lane FAILED over it would say the board failed a check it passed.

**The one figure that could not be made per board, and what replaced it.** Sparsh wanted no
number repeated across the three documents. The round trips are the same on all three, because
the same four desks sign all of them, and a different number per board would be a constant
divided by three. So the change-level figure is printed once, in the pane's empty state, with
the reason stated; and what goes on each board is its own money and its own physical
consequence, from `change.avoidance_for` and the DoD's DMSMS cost metric, where a normal
substitute is $34,000 and 25 weeks against $1,118,000 and 42 for a redesign. The basis says in
the same breath that those are defence programmes applied to a commercial board, which the
project's own research already flags.

**The desk accent reverts.** `isMine` on the change request, the lane trace and the line page's
four blocks did not read at that density, and emphasis belongs where a pane is about one desk.

**Two defects found by running it at a laptop width rather than a wide one.** Three fixed
columns add up to more than 1280 pixels, so the middle, which is the thing the page is for,
collapsed to a sliver of wrapped text; they are proportional with a floor each. And a truncated
flex child still paints its full text unless an ancestor clips it, so the board name ran under
its own verdict chip. Neither was visible at 2560, which is where every screenshot in this pass
had been taken.

---

## Open after this pass

| | Item | Why it is open |
|---|---|---|
| ⚪ | **An invitation cannot be sent to an address with no account.** | There is no token, no expiry and no acceptance route, and the screen refuses rather than pretending. Building one is a real piece of work and a decision about what an invitation is. |
| ⚪ | **Nothing removes a grant.** Inviting is a union and there is no un-invite. | *Bring this person in* and *take this away from this person* are different acts, and only the first was built. |

Two more that this pass ran into and did not create are already written down with their
reasoning in [`DEFERRED.md`](../DEFERRED.md): the board pane's churn through candidates a replay
merely tried, decided as staying, and the fallback replay's frames without a `seq`, which is now
the only path that carries none.

## What not to touch

- `backend/fixtures/**` is committed and is the demonstration's immunity to the venue's network.
  `backend/cache/**` is not committed and is not to be cleaned.
- The replay disclosure rules. Nothing on screen says a run is live, and nothing on screen says
  it is a replay either: `./demo.sh --check` prints it on every start, the recordings are
  committed, and the Q&A sentence in DEMO-DAY is where the claim is made honestly.
- `pacedDelay`'s bounds are asserted in `laneState.test.ts`. Changing the pace is changing that
  test, deliberately.
