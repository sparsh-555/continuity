# Task · BUILD item 39 — the coordination that was removed, counted

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** item 34.

The topic hands us a clock — *"the engineering team needs approved substitutes within 48
hours"* — and SCENARIO-B's rubric note says Efficiency Gains wants a quantified before and
after. **No surface in the product carries a time figure of any kind.**

## What not to build

Not a saving. *"Continuity saved 46 hours"* is a number nobody measured, and inventing it would
fail the first rule this project holds. The 48 hours is the prompt's, and the round-trip
argument is reasoning rather than sourced data — SCENARIO-B says so itself under *Open, not yet
researched*.

## What to build

**The count of round trips that did not have to happen**, which is a fact about the run that
just executed and is derivable from what it already recorded:

> Four candidates, checked against four departments' rules on three product lines, before
> anybody was asked anything. Twelve board evaluations, 22 checks each. Every desk saw the same
> evidence at the same time.

Every number there comes from the review: `len(candidates)`, `len(exposed)`, the department
count from item 33's grouping, and the verdict count per attempt. Nothing is estimated.

## 1 · `continuity/change.py`

The change request document gains a `checked` block: candidates, product lines, departments,
checks per board, and whether anything had to be asked before the packet existed. It sits with
the cost block, because it is the same kind of claim — what this cost, and what it replaced.

## 2 · `review/RequestCard.tsx`, and once above the lanes

One line under the lanes on `/changes` when a run finishes, and one line in each change request.
Not a banner and not a headline: it is a footnote that answers a question a judge asks, and it
should read like one.

## 3 · The sentence for the pitch, in DEMO-DAY.md

The honest framing, which is stronger than a saving anyway: **the sequence is what costs the 48
hours, and there is no sequence here.** Design proposing, procurement replying on stock,
production objecting on footprint — each leg a day or two of email — is replaced by every
department's constraints being checked on every candidate before the first person is asked.
What is left for the humans is four signatures on evidence already gathered, which is
SCENARIO-B's own sentence: *"procurement's approval becomes one click on evidence already
gathered, instead of three days of investigation they run themselves."*

## 4 · Tests

- The `checked` block counts what the run actually did, on a review with two candidates and two
  lines as well as on the seeded three.
- No string in it is composed from a figure that was not computed.

## Done when

A change request says what was checked before anybody was asked, in numbers that came out of
the run, and DEMO-DAY has the sentence to say over it.
