# What we tell the organisers about the project

Two asks, two texts. Both within 200 words, and the second supersedes the first wherever they
disagree.

---

# Finals concept, 8 Sep 2026

Asked for "a brief introduction or concept" so the organisers can understand the project and
offer help where it is needed. Same 200-word limit. **195 words.**

## Submission text

> We are taking topic B. A component goes end of life across three product lines and the
> engineering team has 48 hours to find approved substitutes.
>
> The notice arrives as an unstructured PDF that joins to a bill of materials on part number
> alone, and the manufacturer's recommended replacement is not guaranteed to be pin-compatible
> or parametrically equivalent. Whether it works depends on the board it sits in.
>
> Resolving an end-of-life part with an already approved substitute costs about $1,300.
> Redesigning the board costs upwards of $950,000. What separates them is whether anyone can
> prove the cheaper option works, and that proof averages 40 weeks. Topic B allows 48 hours.
>
> Continuity finds every product carrying the retired part and re-checks them all at once
> against each board's supply, load and thermal environment. A language model reads the notice
> and the datasheets, because neither has a schema. A deterministic engine holds every
> department's rules and computes the verdicts, re-checking the whole board after each change.
> Where a failing rule belongs to quality or procurement rather than engineering, Continuity
> asks that desk. On approval it writes the change into the bill of materials and the KiCad
> design.

## The shape: problem, scale, help

The preliminary text argued a position, because the organisers were choosing between 42
proposals and had to be given a reason to pick one. This ask is different. They want to
understand the project well enough to help with it, so the text states the problem, says how
large it is, and then says what Continuity does about it.

**The reveal stays in the demo.** An earlier draft of this quoted 159 °C against a 150 °C
junction limit, which is the moment the demo turns on and the only thing in it that a
paragraph cannot re-create. Spending it here would buy one sentence and cost the room's
reaction on the day. The text now says that the answer depends on the board, which a reader
can hold in their head and still be surprised by.

## Both halves of the machine, stated as work

The language model and the engine each do a job the other cannot, and the submission says so
in the positive.

A change notice is an unstructured PDF and a datasheet is a 40-page document with the thermal
table in a different place for every vendor. Neither has a schema, and no parser reaches them.
That reading is the model's work, and it is what puts a real θJA and a real junction limit
into the engine's hands.

The engine holds every department's rules, computes the verdicts, and re-checks the whole
board after each change. That is work no model should be doing, because the answer has to be
the same every time it is asked and has to carry its arithmetic.

Earlier drafts wrote this as *"no compatibility verdict is produced by a model"*, which reads
as though the model were being kept away from the important part. Both systems are load-bearing
and the text should read that way.

## The figures, and how far they can be defended

The preliminary submission cut the cost spread on the grounds that the sources disagreed
between consecutive slides. That was half right. Reading [EOL-RESEARCH.md](EOL-RESEARCH.md)
again, the disagreement sits on the *complex substitute* cell, which is $423,000 in the FY2011
DoD metric and $25,410 in the 2015 BIS survey, a sixteen-fold spread the research file
explicitly says not to reconcile.

The two figures used here do not touch that cell. Approved item $1,281 and design refreshment
$955,369 both come from IIOM 2025, inflation-adjusted from the DoD metrics, and the research
file calls that pair "the defensible headline". They are rounded to $1,300 and $950,000 in the
submission because they are defence obsolescence programmes rather than commercial PCB respins,
and quoting them to the dollar would claim a precision that does not transfer.

**40 weeks** is the FY2011 metric's average for a complex substitute, defined there as
*"seeking, selecting, and validating a new part from several potential candidates"*, which is
what Continuity does. The preliminary text cut it for comparing our runtime against a
qualification programme. Here it is set against topic B's own 48 hours, which is the
organisers' number rather than ours, and it makes no claim about how fast we are.

If asked, the answer is that these are DMSMS programme figures and the commercial equivalents
in the same file are softer: $150,000 to $500,000 for a single emergency redesign, from
iLenSys, on automation-equipment OEMs.

---

# Preliminary idea, 7 Sep 2026

Due **7 Sep 2026**, all tracks, within 200 words. This is the organisers' first look at what
we intend to build, and it is read alongside 41 others, so it is written to be concrete
rather than impressive.

---

## Submission text

> We are taking topic B. A component goes end-of-life across three product lines, and the
> engineering team has 48 hours to find approved substitutes.
>
> Today that means matching the notice to a bill of materials, cross-referencing candidates
> on parametric attributes, and applying one replacement across every affected design in a
> single step. The last part is the mistake. Whether a substitute works depends on the board
> it sits in — its load, its supply, its thermal environment — so the right answer differs
> from board to board.
>
> Continuity computes that answer. A deterministic engine evaluates a whole board against
> every constraint, a language model reads the notice and proposes candidates, and the engine
> re-checks everything after each change. No compatibility verdict is produced by a model.
>
> The proof is that one substitute passes on one line and fails on another, on thermal
> resistance quoted from the manufacturer's datasheet rather than a lookup table.
>
> Design, procurement and production each own constraints, evaluated together on every
> candidate. Where the engine cannot decide, it routes to the role that owns the answer,
> producing an engineering change request a human approves.

## Why it is shaped this way

**Rewritten 6 Sep, after an adversarial research pass falsified the previous version.** The
old text claimed matching a notice to a bill of materials was something competitors could not
do. It is exactly what SiliconExpert, Z2Data and PCNshark already sell, and a judge who works
in this industry would have known within a sentence.

**The second paragraph now names them and concedes that ground deliberately.** Conceding the
commodity step is what makes the next claim land — and it demonstrates we know the market
rather than hoping nobody checks.

**The differentiator is structural, not a feature list.** A parametric cross-reference holds
one row per part, so it cannot produce an answer that differs per board. Ours differs per
board by construction. That is not a claim about effort; it is a claim about what their data
model can represent.

**The proof is a single sentence anyone can test.** One substitute, two boards, opposite
verdicts.

**"Quoted from its datasheet rather than a lookup table"** is doing real work. Our own package
table is an approximation whose provenance we could not defend — the research found the
manufacturer states a different figure, varying with copper area. Reading the number out of
the PDF, with the line quoted, is both the honest version and the stronger one. No competitor
opens the datasheet.

## Deliberately left out

- **Specific temperatures.** The earlier draft said "174 °C against a 150 °C limit." Both
  numbers rested on a thermal resistance we could not yet source, and the 150 was an operating
  temperature range rather than a junction limit. The claim was therefore left qualitative
  — clears one board, overheats another — until the datasheet extraction made it quotable.
  **Overtaken 8 Sep: it is quotable now.** 159 °C against onsemi's stated 150 °C maximum die
  junction temperature, on a 160 °C/W minimum-size-pad θJA the datasheet prints in its own
  thermal table. It stays out of the finals text for a different reason, which is that it is
  the demo's reveal and a paragraph cannot re-create it.
- **The cost spread** ($1,281 against $955K). The sources disagree between consecutive slides
  and the figures describe defence obsolescence resolutions, not commercial PCB respins.
  **Half overturned 8 Sep.** The disagreement sits on the *complex substitute* cell rather
  than on this pair, which comes from one source and which
  [EOL-RESEARCH.md](EOL-RESEARCH.md) calls the defensible headline. The finals text uses it,
  rounded, because the defence-programme caveat still stands.
- **40 weeks versus 48 hours.** Strong, but it compares software runtime against a
  qualification programme, which is not the same clock. **Reinstated 8 Sep** in a form that
  does not: 40 weeks is set against topic B's own 48 hours, so both numbers belong to the
  industry and the organisers and neither one claims anything about our runtime.
- **WorkBuddy.** The deck does not require it and we have not built an integration.

## Provenance

The submission now carries no numeric claim that needs a citation, which was the point of
rewriting it. The 120 mA and 350 mA figures are our own stated demo operating profile, not
measurements of a shipping product, and should be described that way if asked.

The qualitative claim — one substitute, opposite verdicts on two boards — is reproduced by
`backend/tools/eol_differential.py`.

**The caveat that stood here is withdrawn, 8 Sep.** It read that the thermal resistances came
from the engine's package table and were not yet defensible. They no longer do. Every figure
was read off the manufacturer's datasheet and is recorded with its source line in
[PARTS.md](PARTS.md); `tools/seed_world.py` writes them as *verified* facts, which is what
lets them outrank a distributor's parametric table. A verified reading and a package-table
guess are now different things to the engine, and only the first one produces a verdict with
a temperature in it.
