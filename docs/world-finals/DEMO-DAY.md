# DEMO-DAY.md

What to say while each screen is up, and the answers to what somebody asks afterwards.

[RUNNER.md](RUNNER.md) is the flow and what a correct screen looks like. This is the spoken
layer over the same twelve steps, so the two are read side by side in a rehearsal and only this
one is read on the day.

**The format of the online demo is not settled yet**, so nothing here assumes a room, a stage
or a fixed length. The lines below are written to be said at a walk over the run-through, which
takes about twenty-five minutes.

---

## The story, in one breath

A company describes what it ships. A change notice arrives by email. Continuity finds every
product carrying the retired part, re-checks all of them at once against **all four
departments' rules**, reaches a different answer for each, and puts a signed change request in
front of every desk that examined it. Each desk signs for itself, the bill does not move until
the last one does, and on the last signature the part changes in the bill of materials, on the
power tree and on the board.

## The claim, and how to put it

A deterministic engine owns what is electrically broken. A language model owns which repair to
try. The engine re-checks the whole board after every change.

Say **no compatibility verdict is produced by a model** and mean it about *who executes the
check*, because that is what it says. Ten model calls exist in this system and the end-of-life
flow reaches three of them, all of them document readers, each one verified before it is
believed. The engine and the model are equal partners here, and neither is a bolt-on to the
other.

## The second claim, which is the topic's own question

The engine checks **design, procurement, production and quality** on every candidate, at the
same time, before anybody is asked anything. The industry name for what follows is an ECR going
to a change control board, and a board's composition mirrors the change's blast radius, which
is exactly those four.

So the sentence to say is not that Continuity coordinates people faster. It is that **the round
trips are gone**: nobody proposes a part and waits two days to hear procurement cannot buy it,
because procurement's rule already ran. What is left for the humans is four signatures on
evidence already gathered — *procurement's approval becomes one click on evidence already
gathered, instead of three days of investigation they run themselves.*

**Two surfaces, and knowing which is which is the whole navigation.** `/changes` is the company
view: what arrived, what it reaches, every affected line running together, and what this desk
owes at the top of the page. `/lines/:id` is one product: its power tree, its bill, its board
and its own review. The same endpoint runs both, narrowed by `line_id`, so they cannot come to
disagree about what a review is. There was a third, `/approvals`, and it was a second place to
sign the same decisions the lanes already asked for.

**Which desk you are is in the rail and in every header**, and it switches between four
real sessions. Not an impersonation: a desk that has to sign has to be signed in.

---

## Step by step

### Step 1 · Sign in, and open a product line

This is the design workspace pointed at a product that already exists. The same three panes,
the same proportions, the same components as the design flow.

**Nothing is wrong with this product yet.** The notice has not arrived, so this is what a
company looks like on an ordinary Tuesday, and it is the picture the red one in step 7 is worth
comparing against.

Green because this product ships and the engine confirms it. The page checks the board against
this line's own ambient, rail and load, and green means green because it was computed.

### Step 2 · How the product line got here

An engineer describes the product, or uploads a bill of materials, and from then on Continuity
knows what the company ships. **NEW PRODUCT LINE** is that door, and you do not have to walk
through it here.

What is on screen is the run in which this line was described: its parts, its rails, and every
check the engine produced on the board those two make. It is not a synthesis and does not
pretend to be, because a product that ships did not arrive by somebody being asked what to
build.

**Then say the line that frames everything after it:** *these are Northwind's five product
lines, and three of them carry the same regulator.*

**On the standing lists, if they come up here.** The approved manufacturer list is derived
from what Northwind already ships, which is what an AML is: seven parts, every one of them
already in production. `LD1117S33TR` is absent for an honest reason, which is that nothing
ships with it yet. The approved vendor list holds one vendor, JLCPCB.

### Step 3 · The boards are already there

Three different designs drawn by three people who have never heard of us, each carrying a real
AMS1117-3.3 in SOT-223, each at a **different reference designator**.

Say that out loud if anyone asks how the substitution finds the part. It resolves the position
per board, because no two products put the same chip in the same place.

### Step 4 · The notice arrives by email

This is the trigger, and it is worth saying that nobody pressed anything.

**Say the cost while it flies.** Resolving an end-of-life part with one that is already
approved costs about $1,300. Redesigning the board costs upwards of $950,000. What separates
them is whether anyone can prove the cheaper option works, and industry averages forty weeks
over that proof.

The recurring half is on each change request by name, because every affected line now states
an annual volume on its own operating profile with a source: the Gateway's TLV1117 is
**$0.1172 a unit against 20,000 a year, so $2,344**, and the two NCP1117 lines are $171.60 and
$68.64. Nothing is assumed — a line with no stated volume shows no recurring figure rather
than a plausible number made out of nothing.

**On the Gateway turning red:** nothing was recomputed to make that happen. The notice names a
part, the bill says the part is fitted, and red is the manufacturer's statement rather than a
verdict of ours.

### Step 5 · Three lanes, four departments, one stream

On not typing into **TRY A PARTICULAR PART TOO**: the candidates are *found*, and saying so is
the point. The notice's own recommendation first, then the approved manufacturer list in the
same category, then the distributor's catalogue in the same package. That box is an override
for a part somebody wants tried anyway, and it is deliberately not the way in.

**Point at the right-hand column.** The three verdicts stack vertically and they disagree, and
that disagreement is the whole argument: the manufacturer's own recommended replacement is
right for two of these products and would cook the third, and the third survives on a different
part for a reason that is about that board and no other.

**Then point at the departments.** Every candidate was checked against design's rules,
procurement's, production's and quality's **at the same time, before anybody was asked
anything**. Expand a lane and they are four labelled blocks over one shared result. That is
the cross-team response: not three people being asked faster, but the round trips removed.

And they do not all end in the same place. The Gateway's answer stops at **procurement** —
1,133 in stock against a build of 5,000 a quarter — while the other two clear outright. One
notice, three products, and the desk that has to think about it is different.

Expand one lane and the other two stay as they are. Every rejection carries the sentence that
killed it.

### Step 6 · Four desks sign, and only then does the product change

**This is the answer to the topic's own question**, so say it while the signatures are going
in. The industry calls this an ECR going to a change control board, and a board's composition
mirrors the change's blast radius: design, procurement, production, quality. A substitution
on a released design is approved before it is implemented, never after.

What Continuity changes is not who signs. It is that **procurement's approval is one click on
evidence already gathered, instead of three days of investigation they run themselves.**

Say the bill is unchanged after the first three. That is the point: no desk can apply a change
on its own, and the tool routes rather than decides.

Then, on the last signature, four things happen at once, and they are the difference between
a recommendation and a change:

- the part is written into the bill of materials,
- the revision moves from Rev C to Rev D,
- every signature is recorded with the desk it was given for and why,
- and the successful precedent is written, so the next notice does not re-litigate it.

### Step 7 · The product line, changed

The notice is joined to the fitted bill, so applying the change takes it away rather than
leaving a warning about a part the board no longer carries.

And the left pane holds the whole review that changed it. **Reopening a reviewed product line
shows the working, not just the answer.**

### Step 8 · The same review, on one product

This is the same endpoint, the same engine and the same frames as step 5, narrowed to one
board. The difference is who it is for: step 5 is the company view, this is the view for one
product somebody wants to go deep on.

**Three colours, three different kinds of claim.** Red was the notice's statement, cyan is work
in progress, green is a verdict.

On the two board pictures being all but identical: that is the correct answer for a true
drop-in, because the pads it lands on are the pads that are already there.

On the board saying **U2** while the power tree says **U1**: the bill this company keeps and
the project somebody else drew are two documents, and the substitution finds the position in
each on its own terms.

**The other half of that argument is in the tests**, because no SOT-23-5 part is a sourced
candidate yet. Placing an `ME6211C33M5G-N` at the same position takes unconnected items from 1
to 4 and adds four shorting items and three clearance violations. It is
`backend/tests/test_boards.py::test_a_smaller_package_breaks_connections_on_this_board`.

### Step 9 · The document, one click from the product

Two artefacts, deliberately kept apart. The **trace** is how this board reached its answer and
lives in the left pane, because that is what somebody on this product wants. The **change
request** is what somebody signs, with cost, approvals, the board consequence and whatever
could not be checked, and that is one line at the end rather than the answer to every click.
`/changes` lists the same document for every affected line, which is the company view of it.

### Step 4b · When a part is retired twice

A manufacturer often issues a preliminary notice and then a full one for the same part, and
that is what `PCN-2026-118` and `PCN-2026-114` are. They both retire `AMS1117-3.3` and they do
not say the same thing: one names a last-order date and a replacement, the other names neither.

So the list labels each by the notice's own number and the day it arrived, and the two read
`AMS-PCN-2026-118` and `AMS-PCN-2026-114`. A list labelled by part number alone would show two
identical rows for two different documents, which is the state this was in until 11 September.

Worth saying out loud only if a judge asks how the tool handles a part retiring twice. It is a
small beat and it is honest: the number is read from the document under the same rule as every
other field, so it has a line to point at.

### Step 5b · The review is still there tomorrow

Worth knowing rather than saying, unless a judge asks what happens when you close the tab.

Leave `/changes` mid-review and come back: the lanes, their traces and their questions are
all still on the page, with nothing re-run. The same is true of a notice reviewed yesterday —
which matters for the demo's own premise, because a change that takes four signatures is not
something anybody watches from start to finish in one sitting. The desks who have not signed
will open it later, and what they see is the run that produced the question they are answering.

### Step 5c · The appendix behind the answer

If a judge asks *how do you know the losing candidates were really checked*, the answer is in the
change request itself. Under **CONSIDERED AND REJECTED**, every alternative that was tried gets
its own block: the one sentence that killed it, and **the failing check printed underneath in
full**, with the desk that owns it. The checks it passed are counted and folded away behind
*the other N checks it passed*, because twenty-two satisfied verdicts is a wall of agreement
that buries the one line worth reading.

That is the shape every convention for rejected alternatives converges on, from NEPA's
*alternatives considered but eliminated* to MADR's *considered options*: **one line in the body,
the working in the appendix.** NEPA's own standard is that a rejected alternative is *discussed
briefly* rather than analysed in full, and the appendix is what makes brief honest. It is also
why the grid the document used to be cut from stopped needing a screen of its own.

### Step 9b · The layout consequence, on the board itself

The strongest artefact in the product sits on the product line's own **BOARD** pane: the real
board, before and after, cropped to the regulator, with the footprint and both part numbers
named underneath. It used to be on the change request, and it was moved because the question it
answers is about *this* board — and because a card that repeats the same picture on three
requests is a picture nobody looks at.

**What it is worth saying.** Same package is a substitution; a different one is a board
revision, and that inverts which part is cheap. This is the check that a parametric search
cannot do and a component-intelligence tool cannot do either, because it runs on *this*
board's file rather than on a part's datasheet.

**Say where it comes from.** KiCad places the part, carries its nets pad by pad by function,
and runs its own design rule check before and after. It is the same deterministic engine the
rest of the checks use, and it is the reason the phrase *we do not let a model decide what is
electrically sound* holds all the way to the artwork.

**And the pane says what it did to *this* board**, which it never used to. Not a sentence about
every board in the demonstration: the pads the substitute's functions were carried onto —
`pad 1 → GND, pad 2 → /+3.3vSB, pad 3 → /+5vSB` on the Gateway — then what two DRC runs found
before and after, and then **WHAT RAN**: five operations with the seconds each took. Those
numbers are taken with a clock inside the container, so *the check ran* is a figure rather than
an assurance.

### Step 9a · What each desk owes

Switch desk from the rail and stay on **Changes**. This is the other half of removing the round
trips: procurement does not have to be told which product line to open, or read a design trace
to sign for procurement. The strip at the top of the page carries their own reason to care, and
the four ticks say who else has already signed.

### Step 9b · The shortfall procurement accepted

Worth showing if the Gateway has been signed, because it answers the question the gate raises
and nothing else in the demo answers: *what happens to a failure somebody accepted?*

The Gateway ships at Rev D with a part that failed procurement's own rule. U1 is amber rather
than green or red, and the pane says **failed and accepted** with the arithmetic still under
it — 1,133 in stock against a 5,000 build. Nothing was repainted and nothing was deleted. The
engine still reports the shortfall every time it checks that board; what the signature changed
is whose problem it is.

**This is the difference between a waiver and a pass**, and it is the reason the same
shortfall is not put to procurement a second time when the next change touches that board.

### Step 10 · Memory, which is the company's record

**Before searching anything**, the retired part is already visible: a duller fill, a heavier
ring, the word NRND under its number, and three warm dashed edges to the boards that still
carry it. The colour is never the only carrier, which matters on a projector and for a reader
who does not separate those two hues at all.

Every line of **WHAT WAS DECIDED** comes from a different table. Underneath it, the verified
datasheet readings each carry the line they were read from, and the ones with no line say so
plainly instead of pretending to a citation.

---

## Replay, and disclosing it

Say it rather than hiding it, in one sentence, when the lanes finish faster than anybody can
read them.

Every distributor call in this demo, and the reading of the notice itself, replays from
recordings made against the real services. The parts data is real, the engine, every rule,
KiCad and the model all still run, and a call with no recording is an error rather than a quiet
trip to the internet. The same review took over two minutes live and takes a quarter of a
second replayed, with identical verdicts and identical margins; reading the notice took
1903 ms live and takes 7 ms, with the same reading.

**The replay plays back at reading pace.** A recorded review fills the lanes over about
**eighty seconds** rather than in a quarter of a second, so three products are seen working
together rather than three verdicts appearing at once. Each line is given time in proportion to
how much there is to read, and the pace is staggered rather than metronomic, because a fixed
interval reads as a machine printing lines. **SKIP TO THE END** is offered throughout for
anybody who has seen enough, and it is there the whole time rather than only at the start.

**The pace is one constant, and it is the only thing to tune for the recording.** `FRAME_FLOOR_MS`
and `FRAME_CEILING_MS` in `frontend/src/app/review/laneState.ts` set how long the shortest and
longest line stay on screen. Nothing else anywhere in the product delays anything.

**One thing to say if you are asked, and it is the honest half of the paragraph above.** The run
is a **recording of a real run, played back.** The engine, every rule, KiCad and the model all
still execute; what is replayed is 622 recorded distributor calls, which is what makes the
demonstration immune to the venue's network. Say that plainly rather than claiming a live run.
The recordings are committed, `./demo.sh --check` says *replaying, not calling out* on every
start, and the repository is public — so the answer is a strength rather than an apology, and
claiming otherwise is the one thing that turns it into a problem.

---

## The design flow, if you show it

Inside Northwind the AML is live, so a new design run stops on the first part that is not on
it, and the question carries the roles that may answer it. A brand-new signup gets its own
company with no lists kept, and there the same flow runs with no qualification gate at all.
**`None` for a list that is not kept and an empty list that approves nothing are different
things**, and that is the difference those two accounts show.

---

## What a judge asks

**Where is the model, and where is it not?** The model reads documents: the change notice, a
datasheet, a brief. It also proposes which repair to try. It never executes a compatibility
check. Every verdict on every screen came out of `rules.evaluate`, which is deterministic and
tested, and the engine re-checks the whole board after every change the model suggests.

**How do you know the substitute actually fits?** Two answers, and they are different. The
electrical answer is the engine against this line's own ambient, rail and load. The physical
answer is KiCad against the real project: the part is placed, the zones are refilled, DRC runs,
and the result is the before-and-after picture in step 8.

**What if the datasheet and the distributor disagree?** The datasheet wins. A verified reading
outranks a listing, and the reading carries the line it came from.

**Why did the manufacturer's own recommendation lose on the Gateway?** Because at 45 °C ambient
with 420 mA through a 5 V rail, NCP1117 reaches 159 °C against a 150 °C limit. That is the
number on screen, and it is the one that makes the case.

**Can it check a part it could not source?** No, and it says so rather than guessing. The four
coverage labels are on every check of every change request, and nothing is left admitting a gap: `emc`,
`output_capacitor_stability` and `signal_integrity` were three standing admissions until
11 September and are now three real checks with published arithmetic behind them. The last of
the three needed four datasheet figures that had been researched and then dropped on the way
to the engine, which is worth saying plainly if a judge asks how you know the checks run: the
empty statement is the answer, and it was not empty twenty-four hours earlier.

**How do the three departments actually interact?** Every rule each of them owns is checked on
every candidate simultaneously, before the first person is asked. Then each department signs
for itself: the bill does not move until all of them have, no desk can sign for another, and
each has a queue of what it owes. Show the Gateway, which stops at procurement while the other
two clear, and the four blocks on any change request.

**Did you not just move the meetings into an app?** No. The round trips are the cost, and they
are gone: nobody proposes a part and waits two days to learn procurement cannot buy it, because
procurement's rule ran on every candidate before anybody proposed anything. What is left for
the humans is four signatures on evidence already gathered, and the change request says exactly
how much was checked to produce it.

**Where does the saving come from?** Two published constants applied to counts this run holds,
and it is worth saying them rather than a total. One engineering-change iteration is about five
hours of desk time (Loch & Terwiesch, 1999), and a handoff between people stalls about 0.9 days
(Herbsleb et al., 2001); four desks means three handoffs, which is where *about 5.2 hours and
about 2.7 days* comes from. **It is an estimate and the document says so in the same sentence** —
nobody instrumented the old process, so there is no measured figure to quote and **no 48 hours to
claim**: that clock belongs to the problem statement, not to us.

**What is not built?** Answer plainly from DEFERRED, which is written down rather than
discovered. The one that is still red: a mailed notice raises no notification, so `/changes`
is the only screen that reacts to one on its own.

**Why does quality never refuse anything?** Because in this world nothing needs qualifying:
every candidate that wins is already on the approved manufacturer list. The gate is real and
enforced — `LD1117-3.3` is refused by name on all three boards for exactly that reason, and it
is in the trace — it just never becomes the winning answer. Show the rejection rather than
claiming the beat.

**Nothing in this document is a substitute for building something.** If a question here can
only be answered by explaining why a thing is missing, that is a defect with a talking point
in front of it, and the talking point is not the fix. Take it to DEFERRED and build it.
