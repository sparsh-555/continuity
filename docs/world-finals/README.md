# World finals — Shenzhen, 13 Sep 2026

Tencent Cloud Hackathon 2026 Global Finals, **Agent track**. Continuity qualified by
winning the AI Tinkerers × Tencent Cloud hackathon in Singapore on 22 Aug 2026.

Source for everything here: the pre-event briefing deck circulated 3 Sep
(`~/Desktop/Tencent World Finals x China visa/online briefing session.pdf`), plus the
organiser confirming the track on 4 Sep. **Track is Agent and switching is not allowed.**

## The documents

Read in this order.

| File | What it is |
|---|---|
| **[FLOW.md](FLOW.md)** | **Start here.** Part one is the machine: every stage of a review, who decides it, the file that does it, and where a model is and is not. Part two is the demo beat. Written to be checked against the code. |
| **[SPEC.md](SPEC.md)** | The contract. Flow diagram, data model, rules, coverage semantics, the demo case with its arithmetic, how the handoff is shown. |
| **[BUILD.md](BUILD.md)** | Thirty ordered work items across six phases, each with its files, its done-condition and its own acceptance test. **Items 1 to 30 are built except 28**, the notice announcing itself. **Phase 8, items 31 to 39, is the cross-team response** and is the open work: the assigned topic asks how three departments coordinate and the build answers with one desk. Phase 6, the presentation, is not written. **Start here for what to do next.** |
| **[RUNNER.md](RUNNER.md)** | The run-through, and nothing else. Ten steps in the order that tells the story, each with the boxes a correct screen ticks. Walk it before every rehearsal; anything that does not match is a bug. |
| **[DEMO-DAY.md](DEMO-DAY.md)** | What to say while each of those screens is up, and the answers to what a judge asks. The spoken layer over RUNNER's ten steps. |
| **[OPERATING.md](OPERATING.md)** | The machine around the run-through: what the start script checks, running the pieces by hand, every route and variable, what would be a bug at each step, what breaks and why, and what is known and not worth reporting. |
| **[PARTS.md](PARTS.md)** | Every listing and datasheet value the demo rests on, with its quote and its provenance. Read before changing any number in SPEC.md's matrix. |
| [SCENARIO-B.md](SCENARIO-B.md) | The assigned scenario, and the ECR/ECO framing that replaced our first answer |

| [EOL-RESEARCH.md](EOL-RESEARCH.md) | Sourced research on how EOL response actually works, with every figure's provenance |
| [PRELIM-IDEA.md](PRELIM-IDEA.md) | The 200-word submission, and why each line is worded as it is |
| [COMPETITORS.md](COMPETITORS.md) | What each vendor documents, why Zuken is not the counterexample it looked like, and the questions this prepares for |
| [WORKBUDDY.md](WORKBUDDY.md) | What WorkBuddy is, and why we are not building on it |
| **[DEFERRED.md](DEFERRED.md)** | Everything found and not fixed, with a severity against each. Read before the demo, and before claiming anything is complete. |
| **[RESEARCH-3rd-Passthrough.md](RESEARCH-3rd-Passthrough.md)** | The third walk through the built product, 10 Sep. What the code actually does behind each finding, the options, and the published work on the same problem. DEFERRED's newest rows point into it. |
| [tasks/](tasks/) | Implementation briefs, one per BUILD item, written to be handed to a coding agent whole. Each is self-contained. |
| RESEARCH-BRIEF.md, RESEARCH-BRIEF-2.md | The two adversarial passes. Kept for provenance — their findings are already folded into the documents above. |

## The challenge

> **From a personal tool to an enterprise-level AI agent.**
> Let AI help more than one person — turn your entire company into a super team.
> Make your Skill/Agent go from "great for one user" to "indispensable to the whole team."

Three sanctioned upgrade paths, pick one and push it one step further:

| Path | Meaning | Their example |
|---|---|---|
| Horizontal Expansion | One skill, more roles | Weekly reports for 1 person → Sales / R&D / Finance |
| Vertical Deepening | "Just a look" → decision-grade | Analysis report → feeds a management decision flow |
| **Chained Collaboration** | Your skill + other skills = a business chain | Contract review → risk alerts → approval workflow |

We are taking **Chained Collaboration**. See [SCENARIO-B.md](SCENARIO-B.md).

Topics were issued per-team by WorkBuddy, two per team, choose one. Ours arrived 4 Sep.

## Judging — 100 points

| Dimension | Pts | Breakdown |
|---|---|---|
| Scenario & Business Value | 25 | Scenario & pain points 15 · Scalability potential 10 |
| Efficiency Gains | 20 | Quantified benefits 10 · Before/after comparison 5 |
| Functional Completeness | 20 | Live demo runnability 10 · Completeness of materials 10 |
| Innovation & Depth | 20 | Technical innovation 10 · **Deep use of product features 10** |
| Live Demo & Presentation | 20 | Clarity 7 · Demo quality 7 · Q&A 6 |

Plus a bonus "Key Highlight" for leveraging WorkBuddy's connectors, experts, expert
groups, projects, assistants and skills.

**This is a different rubric from Singapore.** There, AI Innovation was 30%. Here,
technical innovation alone is 10 of 100, while business value and quantified efficiency
together are 45. The architecture claim that won the prelim is now the evidence that makes
the numbers credible, not the headline.

**The dimensions as printed sum to 105, not 100.** Reconcile against the official scoring
sheet before quoting any weighting in finals materials — the business emphasis holds either
way, but a number that does not add up is the kind of thing a judge notices.

Two notes on the deck itself: Efficiency Gains is boxed at 20 but its sub-scores sum to
15, and the Agent-track pitch length is never stated (the Game track's is 5 minutes
on-site). Both were raised with the organiser.

## Field

42 finalist teams from 10,122 participants and 1,414 preliminary works — **22 Agent**
(described as *mainly enterprise developers*), 16 Game (university), 4 Animation.

The Agent prize table has 22 slots for 22 Agent teams: 1st ×2 at ¥50K, 2nd ×4 at ¥25K,
3rd ×6 at ¥15K, Excellence ×10 at ¥10K, from a ¥390K pool. That reads as placement rather
than selection, though the deck never says so outright.

## Dates, all GMT+8

| When | What |
|---|---|
| 4 Sep | Preliminary project info form · travel info by 15:00 — **done** |
| 5 Sep | Team photo, 3:4 vertical half-body portrait |
| **7 Sep** | **200-word preliminary idea for the final challenge** |
| 11–14 Sep | Shenzhen. Vienna Hotel (Qianhai Happy Harbour), twin shared |
| 12 Sep 19:00 | Presentation order drawn on site |
| 13 Sep | D-Day at Penguin Island — booth, live pitch, judge feedback |

No submission deadline for the finals work itself appears anywhere in the deck; only the
Game track's is stated. Raised with the organiser, answer pending.

## On the ground

42 booths along the third-floor walkway, colour-coded by track. **The booths showcase the
preliminary project, not the finals project** — the Sep 4 form was emphatic about this. So
two artifacts are in play on the 13th: the deployed app as it was submitted in August,
visible to the public all day, and whatever we pitch on stage.

Shuttle from the hotel on the 12th and 13th. Meals provided on the 13th only.

## Open questions with the organiser

1. Submission deadline for the finals work.
2. Does criterion 4.2, "Deep Use of Product Features", mean any Tencent Cloud product or
   WorkBuddy specifically? Continuity was built with CodeBuddy and runs GLM 5.2.
   (Whether WorkBuddy is *required* is answered by the deck: it is not. It appears in the
   Agent track only as the question-setter, and its one scoring mention is a permissive
   bonus box.)
3. Pitch and Q&A length for the Agent track; English or Chinese; interpretation.
4. Booth requirements and what is provided — screen, power, network.
5. **What is reachable from the venue network.** `llm.py` defaults to `api.z.ai`, the
   international endpoint, and its own docstring warns that keys do not work across
   regions. The frontend is on Render. Both need answering before the 12th.
