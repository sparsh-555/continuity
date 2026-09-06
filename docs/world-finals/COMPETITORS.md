# The competitive landscape

From two adversarial research passes. This exists because the first version of our pitch
claimed something false, and because *"why can't my component-intelligence tool plus my EDA
suite already do this?"* is a question the panel may well ask.

Everything here is **documentary** — publicly stated capability, not hands-on evaluation.
Absence from a vendor's documentation is not proof they cannot do something.

## What we conceded, and must keep conceding

Matching a change notice to a bill of materials and routing it to an owner is **commodity**.
Our first submission claimed otherwise and it was wrong.

| Vendor | Documented capability |
|---|---|
| **SiliconExpert** | BOM Manager: upload BOMs, identify lifecycle and sourcing risk, review alternates, receive change alerts |
| **Z2Data** | PCN Manager: collect and deduplicate notices, match affected parts to BOMs, route ownership, track disposition, connect to PLM/ERP |
| **Accuris** | BOM AI: BOM monitoring, alternate recommendation, substitution scenario modelling, revision audit trails |
| **PCNshark** | PDF and email intake, BOM matching, engineering impact assessment, replacement suggestions, decision records |
| **Octopart / Altium** | BOM matching, pricing, availability, lifecycle, alternate sourcing |
| **Cofactr, Luminovo** | BOM and revision management, approved-alternative sourcing workflows |

Their alternates come from **parametric or form-fit-function attribute matching**. Same
voltage, same package, same pinout. A table comparison.

## Zuken — the one that looked like it killed our claim

The second research pass flagged Zuken as a counterexample, because their published
obsolescence workflow ends in *"CR-8000's simulation tools verify that the replacement meets
performance requirements."* That reads like "tells you whether it works on your board."

Checking the actual mechanism showed otherwise:

- **Detection** is a SiliconExpert data feed into the component master.
- **Candidate search is parametric** — *"DS-CR's parametric search capability lets users scan
  the entire component master by part category, operating characteristics, compliance
  factors."*
- **Qualification is a form** — *"Download a datasheet, attach it to the part and submit it
  for processing using the New Part Request form."*
- **Simulation is a separate step an engineer chooses to run.** Their own worked example is
  replacing a **resistor**, R99 to MCR 11 22 4. Resistors do not need thermal analysis.

And the line that matters most:

> *"Updates can be applied across all affected designs in a **single step** by assigning the
> new component from the DS-CR library."*

Their AVL model states the assumption outright: alternates must have *"the same physical
dimensions and equivalent operational characteristics"* — decided once, by a person, for every
board that contains the part.

**So Zuken automates the propagation of a replacement. It does not compute whether the
replacement is right for each board.** Their working assumption is one replacement applied
globally, and that assumption is exactly what our demo is a counterexample to.

## Physics tools exist, but not in this path

**Ansys Sherlock** does physics-based reliability analysis of electronic assemblies.
**Siemens HyperLynx** does electrical analysis. Both are real, both are used at design time by
a specialist who chooses to run them, and neither sits inside a change-notice response.

## The claim, stated so it survives

Not *"nobody can do this"* — that is unarguable, unsizeable, and false.

> Today a change notice is matched to a BOM, candidates are proposed on matching attributes,
> and **the same replacement is applied to every affected design in one step**, because
> checking each board by hand is too slow. Whether a substitute works depends on the board it
> sits in. The right answer differs from board to board.

The demo is the counterexample: one substitute, opposite verdicts on two boards, for two
different reasons.

## Questions this prepares for

**"Why can't SiliconExpert plus my EDA suite do this?"**
They can, with an engineer connecting them by hand for each board. What is missing is the
join: a notice becoming a per-board result with evidence attached and the decision routed.

**"Zuken already does obsolescence."**
Zuken propagates a replacement across affected designs in one step. That is a different job
from deciding whether it is correct on each of them, and their AVL model assumes it is.

**"Isn't this just a parametric cross-reference with extra steps?"**
A parametric cross-reference holds one row per part. It has no board in it, so it cannot
produce an answer that differs per board.

**"So what is genuinely new?"**
The packaged workflow: explicit application conditions, deterministic checks against them,
visible evidence gaps, and a reviewable decision with an owner. Not any single capability —
the join between three things that exist separately.

## What honesty requires

We have not tested these products. We are describing their documentation. If a judge works
for one of them and says their tool does more, the correct answer is that we read the public
material and would want to see it — not to argue.
