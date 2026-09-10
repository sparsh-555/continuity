# Task · BUILD item 33 — every check carries its department, and every screen renders it that way

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** items 31 and 32.

**This is the item that makes the claim visible.** Every figure it puts on screen is already
computed today; none of it is new engine work.

The design was settled on 4 September and never built. [SCENARIO-B.md](../SCENARIO-B.md)'s gap
analysis lists *"role-specific rendering of a shared finding"* and states the shape:

> **Each role sees the same verdict in its own terms. One finding, three renderings — a view
> layer over one shared result, never three engines.**

So: one result, grouped by the desk that owns each part of it, rendered wherever that result
already appears. Not four computations, not four pages.

## 1 · One grouping function — `continuity/roles.py`

Two helpers, because `decision_roles` takes a verdict object and the client needs a rule name:

```python
def roles_for_rule(rule: str) -> tuple[str, ...]:
    return ROLES_BY_RULE.get(rule, DEFAULT_DECISION_ROLES)


DEPARTMENT_ORDER = ("engineering", "procurement", "production", "quality")


def by_department(verdicts) -> list[tuple[str, list]]:
    """Every verdict under each desk that owns it, in a fixed order.

    A rule with two owners appears under both, which is correct rather than a tagging
    mistake to fix: `part_qualification` is engineering's judgement and quality's record,
    and a reader at either desk needs to see it. RESEARCH-BRIEF-2 asked whether one finding
    can legitimately have several owners; it can, and this is where that shows.

    `not_assessed` and `not_applicable` are excluded. A desk that looked at nothing did not
    look, and listing it with an empty result is the coverage prose BUILD's second rule
    keeps off these surfaces.
    """
```

Order is fixed and shared so the four blocks never reorder between two screens.

## 2 · The stream — `continuity/api/review.py`

`stream.check(verdict)` gains `departments`. Find the frame builder in `continuity/api/events.py`
and add the field there rather than at the call site, so the replay path gets it too.

`api/replay.py::_check` builds the same frame shape from `decisions.document`. Add
`departments` there, derived from the stored `rule` — it is a lookup, not a stored field, so
nothing new has to be persisted and old decisions replay correctly.

## 3 · The document — `continuity/change.py`

The change request gains a per-department summary beside the evidence it already carries:

```json
"departments": [
  {"role": "engineering", "satisfied": 8, "failed": 0, "headline": "35 °C thermal margin"},
  {"role": "procurement", "satisfied": 1, "failed": 0, "headline": "1,020,639 in stock at JLCPCB"},
  {"role": "production",  "satisfied": 2, "failed": 0, "headline": "SOT-223 → SOT-223, a drop-in"},
  {"role": "quality",     "satisfied": 1, "failed": 0, "headline": "on the approved manufacturer list"}
]
```

The headline is the `detail` or `margin` of the most important verdict that desk produced:
a failure if there is one, otherwise the one carrying a margin, otherwise the first. Do not
compose new prose — every string here is already written by the rule that produced it.

## 4 · The screens

**`review/ReviewTrace.tsx`.** The narration stays chronological; only the check burst groups.
The run emits every `check` frame in one burst after the candidate loop (`api/review.py:372-376`),
so grouping them loses no ordering that a reader could perceive. Four labelled blocks, in
`DEPARTMENT_ORDER`, each with its verdicts underneath in the existing tick / cross / dash
rendering.

**`review/ReviewLanes.tsx`.** Consumes `check` frames for the first time (see item 3 of the
third-pass findings — the lanes currently drop them). Collapsed, a lane shows four small
department markers with their state. Expanded, it shows the same grouped blocks the trace does.

**`review/RequestCard.tsx`.** The four blocks replace the flat `EVIDENCE` list, with the
evidence lines nested under their desk.

**`routes/matrix.tsx`.** Already prints `cell.departments` for failing cells. Extend it to
print the passing desks too, so a green cell says *four desks, nothing outstanding* rather
than saying nothing.

## 5 · Do not

- Do not add a fifth block for `not_assessed`. That is the coverage prose BUILD's second rule
  keeps off a demo surface, and it has its own DEFERRED row.
- Do not colour a department block by department. Colour is already carrying verdict state;
  the desk is a label.
- Do not compute a department's result anywhere but `roles.by_department`. Two copies of this
  is how a rule ends up under procurement on one screen and engineering on another, which is
  the exact failure `roles.py`'s own docstring was written to prevent.

## 6 · Tests

- `by_department` puts a two-owner rule under both, excludes `not_assessed`, and returns the
  fixed order with empty desks dropped.
- A review of the Gateway emits `departments` on every `check` frame, and no rule with a
  verdict is unattributed.
- A replayed review carries the same departments as the live one for the same decision.
- The change request document contains four department entries for a clear candidate.

## Done when

Running the Gateway's review shows four labelled blocks in the trace, the lanes show the same
grouped verdicts when expanded, and every change request on `/changes` names the four desks
with their own result. **This is the first item in Phase 8 that changes what he sees.**
