# Task · BUILD item 3a — the five coverage labels, in the engine

**Repository** `~/Documents/GitHub/continuity`, work in `backend/`.
**Baseline** 742 passed, 5 skipped. **Do not commit or push.**

This is the **engine half only**. The wire format (`api/events.py`) and the frontend are item
3b and are explicitly out of scope — see "Do not".

---

## Why

`CheckStatus` is `pass | warn | fail`, and `warn` is doing two unrelated jobs. Sometimes it
means *we checked this and it holds, narrowly* — a regulator at 124 °C against a 125 °C limit.
Sometimes it means *we could not check this at all* — a part that states no θJA. On screen they
are the same amber, so a board with three unmeasurable constraints looks exactly like a board
with three tight ones. The first is a coverage gap and the second is a design margin, and
conflating them is how "nine of ten rules passed" gets said about a board where four rules
never ran.

Five labels replace three:

| Label | Meaning |
|---|---|
| `satisfied` | Checked against stated inputs, and it holds |
| `failed` | Checked, and it does not hold |
| `not_applicable` | This check has no subject on this board |
| `not_assessed` | We do not perform this check at all |
| `evidence_missing` | We would check it, but an input is absent or unsourced |

**Margin is an attribute of `satisfied`, not a sixth label.** 124 °C against 125 °C *is*
satisfied. It holds, and it holds by one degree, and both facts must survive.

---

## 1 · `engine/models.py`

```python
CheckStatus = Literal["satisfied", "failed", "not_applicable", "not_assessed", "evidence_missing"]
```

`Verdict` gains:

```python
margin: str | None = None
"""How narrowly a satisfied check holds, in the rule's own units.

Only meaningful on `satisfied`. A check that holds by one degree and one that holds by
eighty are both satisfied, and an approver needs to tell them apart — that is the whole
reason this is an attribute rather than a fourth colour.
"""
```

`Verdict.failed` becomes `self.status == "failed"`.

Add a module constant declaring what Continuity does not check at all, so `not_assessed` is a
stated list rather than a shrug:

```python
NOT_ASSESSED = (
    ("output_capacitor_stability", "Proving a regulator is stable with a given output "
     "capacitor needs simulation. Explicit violations of a published requirement are "
     "checkable and are a separate rule; stability itself is not."),
    ("emc", "Radiated and conducted emissions are a measurement, not a datasheet field."),
    ("signal_integrity", "Needs board geometry and a stackup, which a BOM does not carry."),
)
```

Keep the wording honest and short — these strings are read by a person deciding whether to
trust the board, and each must say *why* it is not assessed rather than merely that it isn't.

## 2 · `engine/rules.py` — the mapping, decided

`pass` → `satisfied`. `fail` → `failed`. Every `warn` is listed below with its label. **This
table is the decision; do not re-derive it.** Line numbers are from the current file and will
drift as you edit — match on the rule and the detail text.

| Line | Rule | What it says | Label |
|---|---|---|---|
| 311 | interface_role_match | filed as no role, so not checked against a controller | `evidence_missing` |
| 371 | interface_role_match | states no interface — bus could not be checked | `evidence_missing` |
| 382 | interface_role_match | needs a bus, no controller **chosen yet** (`incomplete`) | `evidence_missing` |
| 446 | interface_role_match | N SPI peripherals need a chip select each, only M GPIO remain | **`failed`** — see below |
| 531 | pin_budget | states no GPIO count — unchecked | `evidence_missing` |
| 567 | pin_budget | at least N used, some parts state no pin count | `evidence_missing` |
| 637 | current_budget | supply states no current rating — unchecked | `evidence_missing` |
| 674 | current_budget | at least N of M, some parts state no draw | `evidence_missing` |
| 705 | current_budget | inside the derating band | `satisfied` + margin |
| 828 | thermal_dissipation | dissipation could not be computed | `evidence_missing` |
| 840 | thermal_dissipation | no θJA known for the package | `evidence_missing` |
| 897 | thermal_dissipation | states no maximum temperature | `evidence_missing` |
| 928 | thermal_dissipation | runs hot even though it clears the limit | `satisfied` + margin |
| 943 | thermal_dissipation | `"warn" if partial else "pass"` | `evidence_missing` if partial, else `satisfied` |
| 980 | thermal_dissipation | spans; passes above ~X% efficiency | `evidence_missing` |
| 1047 | availability | no stock figure reported | `evidence_missing` |
| 1082 | availability | in stock, but long lead time or lifecycle concern | `satisfied` + margin |
| 1150 | temperature_rating | states no temperature — grade could not be checked | `evidence_missing` |
| 1197 | footprint | over the size target | `satisfied` + margin |
| 1237 | rail_coverage | on no modelled rail, so other rules could not run | `evidence_missing` |
| 1290 | energy_budget | supply states no capacity | `evidence_missing` |
| 1316 | energy_budget | some parts state no draw | `evidence_missing` |

### The one that changes behaviour, deliberately

**Line 446 becomes `failed`, not `satisfied`.** *"3 SPI peripherals need a chip select each,
but only 1 GPIO remains"* is a checked constraint that does not hold. The board does not work.
It was a `warn` because the old vocabulary had nowhere else to put a checked shortfall that
the author did not want to be shouty about, and that is exactly the dishonesty this item
removes. An existing test almost certainly asserts `warn` there — **update it, and say so in
your report.** This is the only site where you are authorised to change what a rule decides.

Every other row changes the *label only*. If any other existing test's status expectation
moves in a way the table above does not predict, stop and report it.

### `margin` values

Fill `margin` on the four `satisfied` rows, in the rule's own units and short enough to sit in
a table cell — `"1 °C"`, `"11% of rating"`, `"45-day lead time"`, `"0.4 mm over target"`. The
`detail` sentence keeps its existing wording; `margin` is a separate short field, not a rewrite.

### `not_applicable`

Rules currently return `[]` when they have no subject, so a board where four rules had nothing
to check looks identical to one where four rules passed. Where a rule returns an empty list
because **this board has no subject for it** — no buses, no rails needing a budget, no
regulator — return one `not_applicable` verdict for the rule instead, with a detail saying what
is absent.

Do **not** emit `not_applicable` where a rule returns early for any other reason. If you cannot
tell the two apart at a given site, leave it returning `[]` and list the site in your report.

### `not_assessed`

Add a rule-shaped function that returns one `not_assessed` verdict per entry in `NOT_ASSESSED`,
and include it wherever `evaluate` assembles the rule list, so every board carries them. These
are constant per board; they exist so a coverage count has an honest denominator.

## 3 · `graph/nodes.py` and `api/bom.py`

Four sites construct verdicts outside `rules.py` (`nodes.py:461`, `nodes.py:582`,
`bom.py:280`, `bom.py:359`), all with `status="warn"`. Read each and give it the label the
table's logic implies — they are all "we could not check", but confirm rather than assume, and
name your choice for each in the report.

---

## Tests

`tests/test_rules.py` carries about eighty status assertions. **They should mostly change
mechanically** — `"pass"` → `"satisfied"`, `"fail"` → `"failed"` — and each `"warn"` becomes
whichever label the table gives that site. Work through them; do not bulk sed, because the
`warn` cases split three ways.

New tests, in the style of the recent additions at the bottom of that file:

1. **A board with no buses reports `interface_role_match` as `not_applicable`**, not as absent
   and not as passing.
2. **A regulator at 124 °C against a 125 °C limit is `satisfied` and carries a margin.** The
   status and the margin are both asserted — this is the distinction the whole item exists for.
3. **A part with no stated θJA whose package the table *does* know reports `evidence_missing`.**
   The demo's four regulators no longer supply this case, since all four publish a figure, so
   build it from a part that genuinely states none.
4. **`evidence_missing` and `satisfied` are distinguishable on one board** — construct a board
   carrying one of each and assert a coverage count that separates them.
5. **Every board reports the `NOT_ASSESSED` entries**, each with a reason string.
6. **The chip-select shortfall is `failed`.**

---

## Environment

**Use the project virtualenv, not the system Python.**
`/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`

The anaconda Python on the PATH has no `langgraph` and produces 12 collection errors unrelated
to your work.

Run the suite from `backend/`, and do **not** pass `-q` — it swallows the summary line here:

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

If PostgreSQL is unreachable in your sandbox the store tests will time out. Say so plainly in
your report rather than reporting a partial count as if it were the whole suite — the previous
task's report claimed one broken test when there were three, because the full suite never ran.

`timeout` does not exist on this machine.

## Do not

- **Do not touch `api/events.py` or anything in `frontend/`.** That is item 3b. The wire will
  break against the new labels and that is expected and handled separately.
- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not commit, push, or branch.**
- **Do not edit anything under `docs/`.**
- **Do not change what any rule decides, except line 446**, which is authorised above.
- **Do not invent a sixth label**, and do not add a `warn` alias for compatibility. The point
  is that the two meanings separate.

## Report

1. Exact pytest counts before and after, with the command. If the full suite could not run,
   say so explicitly.
2. Every file changed and what changed in it.
3. Your label choice for each of the four verdict sites outside `rules.py`.
4. Every site where you could not tell `not_applicable` from an ordinary early return.
5. Any existing test whose status moved in a way the mapping table did not predict.
