# Preliminary idea for the final challenge

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
  numbers rest on a thermal resistance we cannot yet source, and the 150 is an operating
  temperature range rather than a junction limit. The claim is now qualitative — clears one
  board, overheats another — until the datasheet extraction makes it quotable.
- **The cost spread** ($1,281 against $955K). The sources disagree between consecutive slides
  and the figures describe defence obsolescence resolutions, not commercial PCB respins.
- **40 weeks versus 48 hours.** Strong, but it compares software runtime against a
  qualification programme, which is not the same clock.
- **WorkBuddy.** The deck does not require it and we have not built an integration.

## Provenance

The submission now carries no numeric claim that needs a citation, which was the point of
rewriting it. The 120 mA and 350 mA figures are our own stated demo operating profile, not
measurements of a shipping product, and should be described that way if asked.

The qualitative claim — one substitute, opposite verdicts on two boards — is reproduced by
`backend/tools/eol_differential.py`. The thermal resistances behind it are currently from the
engine's package table and are **not yet defensible**; see the θJA work at the top of the
build order in [FLOW.md](FLOW.md).
