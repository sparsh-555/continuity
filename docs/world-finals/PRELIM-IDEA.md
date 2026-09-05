# Preliminary idea for the final challenge

Due **7 Sep 2026**, all tracks, within 200 words. This is the organisers' first look at what
we intend to build, and it is read alongside 41 others, so it is written to be concrete
rather than impressive.

---

## Submission text

> We are taking topic B. A component goes end-of-life across three product lines, and the
> engineering team has 48 hours to find approved substitutes.
>
> Continuity already divides that work. A deterministic engine proves what is electrically
> broken, a language model decides which repair to try, and the engine re-checks the whole
> board after every change. No compatibility verdict is ever produced by a model.
>
> Scenario B turns that division into an organisational one. Design owns the electrical
> rules, procurement owns availability and the approved-vendor list, production owns
> footprint. All three are evaluated on the same candidate at the same instant, so every
> substitute arrives pre-cleared by every department. Where the engine cannot decide, it
> escalates to the role that owns the answer.
>
> Our test case uses real parts. When AMS1117-3.3 goes end-of-life, the obvious cheaper
> replacement passes two lines and reaches 174 °C against a 150 °C limit on the third,
> because SOT-23-5 carries four times the thermal resistance of SOT-223. No single part is
> right for all three boards.
>
> Industry figures put a substitution like this at 40 weeks. The prompt allows 48 hours.

---

## Why it is shaped this way

**It names the topic in the first six words.** Someone reading 42 of these should not have
to infer which one we picked.

**The architecture claim is stated once and moved past.** It is what won the preliminary, and
the finals rubric weights technical innovation at 10 points against 45 for business value and
efficiency. Restating it at length would be answering last month's question.

**The middle paragraph is the actual answer to the brief.** The challenge asks for multi-role
collaboration, so the three departments and the routed escalation are the load-bearing part.

**The fourth paragraph is evidence, not illustration.** Real MPNs, a number the engine
derived, and a mechanism — four times the thermal resistance in a smaller package — that a
parametric search cannot see. It is checkable, which is the point.

**It closes on the gap.** 40 weeks against 48 hours is the whole business case in nine words,
and the 40 comes from the US DoD's DMSMS cost metrics rather than from us.

## Deliberately left out

- **The cost spread** ($1,281 for an approved part against $955K for a redesign). Strong, but
  it needs room to be credible, and the 40-weeks line already lands the gap.
- **WorkBuddy.** The deck does not require it, and claiming an integration we have not built
  would be the easiest thing in here to puncture.
- **The engineering plan** — fan-out, the decision matrix, the policy layer. This is a
  200-word statement of intent, not a design document.

## Sources for every figure

174 °C, 150 °C, 62 versus 250 °C/W: `backend/tools/eol_differential.py`, computed by the
engine from JLCPCB part data. 40 weeks: US BIS / DoD *DMSMS NRE Cost Metric Update*, the
"complex substitute" row — see [EOL-RESEARCH.md](EOL-RESEARCH.md).
