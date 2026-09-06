# Research brief — Continuity 2.0, for a fresh agent

Copy everything below the line into a new session. It is self-contained.

---

You are researching to strengthen a product before a competition demo. **Do not write
code, do not redesign the architecture, and do not propose anything that cannot be built
by one person in five days.** Your job is to find what we have wrong, what we are missing,
and what a hardware engineer on the judging panel would attack.

## The product

**Continuity** designs and validates printed-circuit-board bills of materials. Repo:
`~/Documents/GitHub/continuity`. Python backend, React frontend, Postgres, LangGraph.

Its architecture claim, and the reason it won its regional round:

> A deterministic engine owns *what is electrically broken*. A language model owns *which
> repair to try*. The engine re-checks the whole board after every change. **No
> compatibility verdict is ever produced by a model.**

Frame the two halves as equal partners. The model is the intelligence layer, not a
constrained afterthought.

Read these first, in order:

| Path | Why |
|---|---|
| `backend/continuity/engine/rules.py` | The ten rules. `RULES` is at the bottom. |
| `backend/continuity/reviewer.py` | What the model may propose. `ACTIONS`, `CONSTRAINT_FIELDS`. |
| `backend/continuity/engine/policy.py` | The guard layer that validates every model proposal. |
| `backend/continuity/graph/build.py` | The LangGraph state machine, ten nodes. |
| `backend/continuity/graph/nodes.py` | What each node does. |
| `backend/continuity/api/app.py` | HTTP surface. `/bom/validate`, `/design`, `/resume`, `/datasheet`. |
| `backend/tools/eol_differential.py` | The demo's core case, on real parts. Run it. |
| `docs/world-finals/*.md` | The finals brief, the scenario, sourced research, the flow. |

The ten rules: `voltage_overlap`, `interface_role_match`, `pin_budget`, `current_budget`,
`thermal_dissipation`, `availability`, `footprint`, `temperature_rating`, `energy_budget`,
`rail_coverage`. Repair actions: `swap`, `change_rail`, `change_topology`, `add_part`,
`escalate`, capped at three per slot. Escalation is a LangGraph `interrupt()`.

## The competition

Tencent Cloud Hackathon 2026 Global Finals, Shenzhen, **13 September 2026**. Agent track,
42 finalist teams, 22 of them Agent, described as *mainly enterprise developers*.

Scored out of 100: **Scenario & Business Value 25** (pain points 15, scalability 10),
**Efficiency Gains 20** (quantified benefits 10, before/after 5), **Functional Completeness
20** (live demo runnability 10, materials 10), **Innovation & Depth 20** (technical
innovation 10, deep use of product features 10), **Live Demo & Presentation 20**.

Note the weighting: business value and quantified efficiency are 45 points; technical
innovation is 10. The pitch is five minutes.

## The assigned scenario

> *A critical component just went end-of-life, affecting 3 product lines. The engineering
> team needs approved substitutes within 48 hours. How does your tool coordinate the
> cross-team response — design validates alternatives, procurement checks availability, and
> production confirms assembly compatibility?*

## What we intend to build, and the flow

Our framing, which we arrived at after realising a tool that clears a substitution alone is
replacing a team rather than coordinating one: **Continuity performs the impact analysis and
drafts the Engineering Change Request. Humans still approve it.**

1. **Product lines already in Continuity.** Each added by uploading its KiCad project, which
   yields both the BOM the rules need and the board the footprint view draws.
2. **A PCN arrives** as an unstructured PDF or email. Parsed into `{MPN, notice type,
   effective date, last-time-buy, recommended replacement}`.
3. **Exposure.** Match the MPN across every line. *"AMS1117-3.3 appears in 3 of your 5
   product lines."*
4. **Evaluate the manufacturer's own recommendation first**, then model-proposed alternates.
5. **Fan out**: every candidate against every affected board, all ten rules on the whole
   board each time. Result is a matrix, candidates down, lines across, each cell tagged with
   the department that owns any failure.
6. **The reveal.** With real parts: `AMS1117-3.3` (SOT-223) goes EOL. The manufacturer's
   cheap recommendation `ME6211C33M5G-N` (SOT-23-5) passes a 120 mA line, runs hot at 110 °C
   on a 200 mA line, and **fails a 350 mA line at 174 °C against a 150 °C limit** — because
   SOT-23-5 carries 250 °C/W against SOT-223's 62 °C/W. Invisible to a parametric search.
7. **An approval gate.** `TLV1117LV33DCYR` passes all three but is not on the approved-vendor
   list, so the run stops and addresses that decision **to procurement**, not to whoever is at
   the keyboard.
8. **A change request per line**, with evidence, cost delta and required approvals.
9. **The boards.** ME6211 is SOT-23-5 against the outgoing SOT-223 — pads move, connections
   break, two boards need layout work. TLV1117 is SOT-223, a true drop-in. So the cheap part
   is not cheap once you count respinning two boards. We show this in an actual KiCad board.

## What to research — our blind spots, in priority order

### 1 · KiCad as the ingestion path and the footprint view
This is now load-bearing and we have verified none of it.
- What file or files yield a reliable BOM from a KiCad project? Schematic, netlist, `kicad-cli`
  export? Which is stable across KiCad versions?
- Can the `pcbnew` Python API run **headless**, and is it installable without a full KiCad
  desktop install? Does it work on a Linux container?
- Can a footprint be **replaced programmatically**, and can the resulting broken connections
  be detected and reported? We explicitly do **not** intend to re-route.
- How is a KiCad board **rendered in a browser**? We have heard of `kicanvas` but not verified
  it. Is SVG export via `kicad-cli` a better path?
- Are there **real open-source KiCad projects** we could adopt as our three product lines —
  ideally sharing a 3.3 V linear regulator, with different load currents? Licence matters.

### 2 · Approved vendor lists
- AVL versus AML — are they the same thing? What is the real distinction?
- Is approval per manufacturer part number, per manufacturer, or graded (preferred /
  qualified / alternate)?
- Where does it actually live — PLM, ERP, a spreadsheet? Who maintains it?
- What would a credible AVL look like as data in a demo?

### 3 · Requalification — this is our business case
The cost spread we quote is roughly $1,281 for using an already-approved part against
$955K–$2.08M for a redesign (US DoD DMSMS metrics). **What determines which bucket you land
in?**
- When does a substitution require requalification and when does it not?
- What does **form, fit and function** mean precisely, and how does it map onto our rules?
- Does a footprint change alone trigger requalification? Does a package change?
- Are there more current or more commercial figures than the DoD ones?

### 4 · PCN structure
- Is there a **standard** for product change notifications? We believe JEDEC JESD46 may be
  relevant — verify.
- What fields are mandatory in practice? Are there public sample PCNs from TI, Infineon or
  Microchip we can parse against?
- How much do formats vary between manufacturers?

### 5 · What an ECR actually contains
- Standard fields and templates. Is there a governing standard (CMII, ISO 10007)?
- What would make a generated ECR look credible to someone who approves them weekly, rather
  than like a generated document?

### 6 · Competitive position — worth 10 points on scalability
- What do **SiliconExpert, Z2Data, Accuris, PCNshark and Octopart** actually do at the
  workflow level, as opposed to their marketing?
- Does anyone already validate substitutes against a whole board's physics rather than
  against a parametric table? If so, who, and how do we differ?
- Where is the genuine unmet gap?

### 7 · The attack surface — be adversarial
Assume a hardware engineer on the panel. What breaks first?
- Where is the θJA package-table approximation weakest? Is 62 °C/W for SOT-223 and 250 °C/W
  for SOT-23-5 defensible, and under what assumptions — copper area, airflow, board layers?
- What is wrong or naive about computing junction temperature as ambient + P × θJA?
- Known gaps we already concede: no schematics or layout generation, no passives, no EMI, no
  I²C address collision checking, and thermal uses a default 25 °C ambient while
  `temperature_rating` uses the product's rated range. Which of these would a judge hit first?
- What would you ask us that we could not answer?

## Constraints on your answer

- Cite sources. Distinguish what you verified from what you inferred.
- Where sources disagree, show the disagreement rather than averaging it.
- Say plainly when something is not findable.
- Rank findings by whether they change a decision we are about to make.
- **Do not propose scope.** Five days, one person, and a demo that must run live.
