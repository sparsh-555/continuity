# Task · BUILD item 32 — a department's own rule is a decision, not a wall

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** item 31.

`review.py:37` reads:

```python
GATE_RULES = ("part_qualification", "source_approval")
"""Rules a department owns rather than physics. A failure here is a decision, not a wall."""
```

Everything else is `physical` — *"failures no signature can clear"* (`review.py:62-64`). So a
candidate that fails `availability` is **discarded rather than routed**, and procurement is
never asked about a stock problem, which is the whole of procurement's job in this scenario.
The same for `footprint` and production.

**Item 38 cannot work until this does.** It was planned on the assumption that raising a
product line's stock minimum routes a decision to procurement. It does not; it deletes the
candidate.

## The distinction to keep

The two-way split is right and the list is two rules too short. The test is not *who owns the
rule* — every rule has an owner — it is **whether a signature can change the outcome**.

| | Rule | Why |
|---|---|---|
| decision | `part_qualification` | quality can qualify the part |
| decision | `source_approval` | procurement can approve the vendor |
| decision | `availability` | procurement can bridge-buy, accept a lead time, or say no |
| decision | `footprint` | production can accept a board revision |
| decision | `footprint_compatibility` | same, and it is the same desk |
| wall | `thermal_dissipation` | no signature lowers a junction temperature |
| wall | `voltage_overlap`, `current_budget`, `pin_budget`, `interface_role_match`, `temperature_rating`, `energy_budget`, `rail_coverage`, `capacitor_requirements` | physics or a published limit, same reasoning |

`capacitor_requirements` is deliberately a wall: it fires on an **explicit published**
requirement being violated, which is the manufacturer's statement rather than a company policy.
Say so in the comment so the next reader does not have to re-derive it.

## 1 · Move the list to `continuity/roles.py`

`GATE_RULES` answers *"can a desk answer this?"* and `ROLES_BY_RULE` answers *"which desk?"*.
They are one concern and they drift apart in two files. Move it next to the routing table:

```python
ANSWERABLE_RULES: frozenset[str] = frozenset({
    "part_qualification",
    "source_approval",
    "availability",
    "footprint",
    "footprint_compatibility",
})
"""Failures a department can answer, as opposed to failures that are physics.

...the table above, in prose...
"""
```

Keep the name `GATE_RULES` re-exported from `review.py` if that keeps the diff small, but the
definition lives in `roles.py`. `review.py` already imports from `roles.py`, so there is no
new dependency and no cycle.

## 2 · `continuity/review.py`

Import it and delete the local definition. `Attempt.gates`, `Attempt.physical`,
`Attempt.gated` and `choose` need no other change: widening the set is enough for a candidate
whose only failure is `availability` to become `gated`, and for `choose`'s second pass to
address it to procurement through `decision_roles`.

## 3 · Check every other reader of the split

Before finishing, grep for `gates`, `physical`, `gated` and `GATE_RULES` across `backend/`.
`narrate()` in `review.py` and `change.py` both read verdicts and may phrase a gated failure as
a rejection. A candidate that is *gated* must not be narrated as *rejected because*: it was not
rejected, it is waiting on a desk. Fix the wording where it is wrong and leave it where it is
already right.

## 4 · Tests — `backend/tests/test_review.py`

1. A candidate whose only failure is `availability` is `gated`, not `physical`, and
   `choose` proposes it with `roles == ("procurement",)` and `gate_rule == "availability"`.
2. A candidate whose only failure is `footprint` proposes with `roles == ("production",)`.
3. A candidate failing `thermal_dissipation` is `physical`, `gated` is false, and `choose`
   returns `None` when it is the only option. **This is the test that stops the widening from
   turning physics into a signature.**
4. Every rule in `ANSWERABLE_RULES` appears in `ROLES_BY_RULE`, so an answerable rule always
   has somebody to answer it.

Existing tests to expect breakage in: `test_review.py::test_the_decision_leaves_engineering_when_only_a_department_rule_stands`
and anything in `test_gates.py` that asserts the old two-rule set.

## Done when

Both suites green, and a hand-built board whose only failure is a stock shortfall produces a
proposal addressed to procurement rather than no proposal at all. Still nothing visible on
screen.
