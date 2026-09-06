# Task · BUILD item 2 — the ambient is an input, not a default

A self-contained brief. **Repository** `~/Documents/GitHub/continuity`, work in `backend/`.
**Baseline** 735 passed, 5 skipped. **Do not commit or push.**

---

## The defect

Every junction temperature the engine computes is `T_A + P × θJA`. `T_A` comes from
`Requirements.ambient_c`, which is `int = 25` — a plain default with no record of whether
anyone actually said 25.

Both places that fill it push the model toward emitting it unconditionally:

- `planner/plan.py:159` — *"ambient_c: expected ambient temperature, 25 unless stated."*
- `api/bom.py:118` — *"ambient_c: expected ambient temperature; 25 unless the brief states it."*

So a board whose brief never mentioned temperature is judged at 25 °C, and nothing on screen
says so. Asked *"where did that 25 come from?"* there is no answer, and `rules.py`'s own
module docstring says a rule *"never skips quietly and it never substitutes a default."* This
is a default being substituted silently, in the operand that decides every thermal verdict.

## What this is NOT

**Do not make `ambient_c` nullable, and do not make a missing ambient refuse the thermal
check.** Most briefs never state an ambient, so that would turn thermal into "unchecked" on
almost every board Continuity designs — a large regression dressed as rigour.

Assuming a bench ambient is fine. Assuming it *silently* is the defect. This codebase has
settled that question twice already and both precedents are in files you will have open:

- `models.py` — `ASSUMED_EFFICIENCY = 0.80` ships beside
  `ASSUMED_EFFICIENCY_SOURCE = "Continuity assumption — no efficiency published"`, and R5
  cites it.
- `packages.py` — the θJA table cites `THETA_JA_SOURCE` rather than a datasheet URL,
  *"so the screen never implies a datasheet said something it did not."*

Ambient gets the same treatment. Keep the number, carry its provenance, show it.

**Do not add coverage labels.** Whether an assumed ambient makes a check *satisfied* or
something weaker is BUILD item 3's decision. Your job is to make the distinction visible and
queryable; item 3 decides what it means.

**Do not touch product lines or the store.** BUILD item 2 originally also called for the
profile to be persisted on a product line. Product lines do not exist until item 10, so that
half has moved there. `api/store.py` is out of scope for this task.

---

## 1 · `engine/models.py`

Two module constants, beside `ASSUMED_EFFICIENCY` and its source string:

```python
AMBIENT_DEFAULT_C = 25
AMBIENT_DEFAULT_SOURCE = "Continuity assumption — the brief stated no ambient"
```

`Requirements.ambient_c` keeps its value and its type, now defaulting to
`AMBIENT_DEFAULT_C` rather than a bare literal. Add beside it:

```python
ambient_source: str | None = None
"""Where `ambient_c` came from. None means nobody stated one and the default stands."""
```

Give it a docstring in the house style saying why the field exists — that a thermal verdict
is only as good as the ambient under it, and an assumed ambient and a stated one must not
look alike on screen.

**Also fix `temp_range`'s docstring**, which is the conflation the item is named for. It
currently reads `""industrial" → (-40, 85)."` and nothing says what the field *means*. It is
the **component grade**: the ambient range a part must be rated to tolerate, checked by R9
against each part's `temp_min`/`temp_max`. It is not the board's local ambient — that is
`ambient_c` — and it is not a junction temperature, which is `PartSpec.t_j_max`. Those three
have been mistaken for one another twice in this project; say so in the docstring.

## 2 · `planner/plan.py`

**Prompt.** Change the `ambient_c` line so the model omits the field rather than inventing a
figure. The `lifetime_hours` line four lines below is the pattern to copy — it already says
*"Omit it entirely when no lifetime is stated"* and explains why. Something like:

> `ambient_c`: the ambient temperature the board operates in, in Celsius, ONLY when the brief
> states or directly implies it — "in a car engine bay", "outdoors in Singapore", "inside a
> sealed enclosure". Omit it entirely when the brief does not say. Do not default to 25.

**Parse** (`plan.py:357` and the `Requirements(...)` call at 374). Today:

```python
ambient_c=int(ambient) if isinstance(ambient, (int, float)) else defaults.ambient_c,
```

The key being *absent* is already distinguishable from it being present — that is what makes
this cheap. When the model supplied a usable figure, pass it with
`ambient_source="stated in the brief"`; otherwise keep the default and leave `ambient_source`
as `None`.

Bound it the way `input_voltage` and `lifetime_hours` are bounded, and for the same reason
given in the comment there: it is an operand, and an absurd figure is likelier a misread than
a brief. Accept roughly −60 to 150 °C and fall back to the default outside that.

## 3 · `api/bom.py`

The same prompt change at line 118 — this path infers requirements for an uploaded BOM and
must not claim an ambient the user never gave either.

Check `_default_requirements_payload()` at line 124: it builds a payload from every name in
`REQUIREMENT_FIELDS`, so it currently emits `ambient_c: 25` as though the model had answered
it. It must not produce a payload that looks like a stated ambient.

## 4 · `engine/rules.py`

In `_check_rail_thermal`, where the evidence rows are assembled — you added θJA's mounting
condition and the declared rail load there in item 1, and this goes with them:

```python
Evidence(subject, "ambient", fmt.celsius(requirements.ambient_c),
         requirements.ambient_source or AMBIENT_DEFAULT_SOURCE)
```

And **the verdict's `detail` must name the ambient it used.** Today a reader sees
`"109 °C junction against a 125 °C limit"` with no way to know what ambient produced 109.
Work the ambient into the sentence for the pass, warn and fail paths — keep the existing
phrasing and add to it rather than rewriting these strings, they are read aloud on stage.

---

## Tests

Add to `tests/test_rules.py`, matching the style of the seven `declared rail load / junction
limit / mounting` tests already at the bottom of that file.

1. **The same board at two ambients gives two verdicts, and each names its own.** 25 °C and
   70 °C on identical hardware — different junction temperatures, and the number appears in
   both the evidence row and the detail.
2. **An assumed ambient says it is assumed.** A `Requirements()` with no `ambient_source`
   produces an evidence row sourced to `AMBIENT_DEFAULT_SOURCE`.
3. **A stated ambient says it is stated.** `ambient_source="stated in the brief"` reaches the
   evidence row instead.
4. **A board that is fine at 25 °C and fails at 70 °C.** The point of the whole item: pick a
   dissipation and θJA where the ambient alone decides it, so the test would fail if the
   ambient stopped being an operand.

Add to the planner's tests, wherever `parse_requirements` / the plan parsing is covered:

5. **A payload omitting `ambient_c` yields the default and a `None` source.**
6. **A payload stating one yields that value and a stated source.**
7. **An out-of-range figure falls back to the default rather than being used.**

---

## Environment — read this or you will chase a phantom failure

**Use the project virtualenv, not the system Python.**
`/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`

The anaconda Python on the PATH has no `langgraph` and produces 12 collection errors that
have nothing to do with your work.

Run the suite from `backend/`, and do **not** pass `-q` — it swallows the summary line here:

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

`timeout` does not exist on this machine.

## Do not

- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses. They show as modified in git and that is intentional; never `git checkout` or
  `git stash` them.
- **Do not commit, push, or branch.**
- **Do not edit anything under `docs/`.** If the brief is wrong, say so and stop.
- **Do not change `api/store.py`** — see "What this is NOT".
- **Do not change what a thermal verdict decides.** Only what it discloses. Every existing
  test must still pass on its existing assertions: if one moves, that is a finding to report,
  not an expectation to update.

## Report

1. Exact pytest counts before and after, with the command.
2. Every file changed and what changed in it.
3. Any existing test that moved, and why.
4. Anything in this brief that did not reconcile with the code.
