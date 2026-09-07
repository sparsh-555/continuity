# Task · BUILD item 4 — three bugs, all verified present

**Repository** `~/Documents/GitHub/continuity`, work in `backend/`.
**Baseline** 750 passed, 5 skipped. **Do not commit or push.**

Three unrelated defects, each already located and each with its fix decided. Nothing here
needs designing — read the reasoning so you write the right thing, then write it.

---

## 1 · The repair cap is off by one, in both directions

`engine/policy.py`, `MAX_REPAIRS = 3`, *"repairs a single slot may absorb before the conflict
goes to the user instead."*

```python
line 128:  ... and board.slots[slot_id].repair_count <= MAX_REPAIRS      # repairable
line 161:  ... and board.slots[slot_id].repair_count >  MAX_REPAIRS      # exhausted
line 307:  return slot is not None and slot.repair_count > MAX_REPAIRS
```

`repair_count` starts at 0 and increments after each repair (`policy.py:301`). So a slot that
has already been repaired three times has `repair_count == 3`, passes `<= 3`, and is handed a
fourth. `exhausted` agrees with it — it only fires at 4. **The effective cap is four repairs
against a constant that says three.**

**Fix:** repairable is `< MAX_REPAIRS`; exhausted is `>= MAX_REPAIRS`. Both sites, and check
whether any other comparison against `MAX_REPAIRS` exists before you finish.

**Test:** a slot at `repair_count == 3` is not offered a fourth repair and reports exhausted.
A slot at 2 still is. Assert the count of repairs a run can absorb, not just the boundary
predicate, so the test would fail if the constant and the comparison drift apart again.

## 2 · The reviewer's prompt tells the model something false

`reviewer.py:127`, in the `SYSTEM` prompt:

> *"A linear regulator that overheats dissipates (Vin - Vout) x I as heat, so a larger linear
> regulator dissipates exactly the same and fails identically — that is a change_topology, not
> a swap."*

The first half is right and the conclusion does not follow. Power is the same; **temperature is
not**. Junction temperature is `T_A + P × θJA`, and θJA is a property of the package and its
mounting — the same part family measures **62.9 °C/W in SOT-223 and 250 °C/W in SOT-23-5**, and
onsemi publishes 160 °C/W for SOT-223 at a minimum pad against 66 °C/W with a square inch of
copper. A bigger package with the same dissipation runs cooler, often by enough.

This is not academic. The finals demo turns entirely on package and mounting deciding whether a
substitute survives, and the prompt currently tells the model that consideration does not exist.
It would refuse a swap that works.

**Fix:** rewrite that passage so it says what is true — the same power in a larger package
means a lower θJA and a lower junction temperature, so a swap to a better-cooling package is a
legitimate repair for a thermal failure. `change_topology` is for when no package in the family
sheds enough heat, or when the drop itself is the problem — a linear regulator burning 8 V of
difference wants a switcher, not a bigger tab.

Keep the surrounding prompt's voice: it is terse, second-person, and explains *why* so the model
can generalise. Do not lengthen it much; a prompt is not documentation.

## 3 · Repair constraints do not accumulate

`graph/nodes.py:876`:

```python
full = sourcing.merge_constraints(slots[slot_id].constraint, constraint)
```

`full` merges the slot's original planner constraint with the current repair's demand, and is
used for the search — **and is never written back to the slot.** So repair two starts from the
planner's constraint again and has forgotten what repair one demanded. On a temperature range
this oscillates: repair one asks for `rated_to: 70` and gets a part failing the cold end, repair
two asks for `rated_from: -40` and gets back something failing the hot end. Scenario B is
temperature ranges across three boards, so it will bite.

**The fix is not "accumulate everything", and it is not "accumulate on swap only".** Both are
wrong, in opposite directions:

- Accumulating everything carries `package: SOT-223` from repair one into a repair two that
  deliberately changes topology, and the search for a buck converter in SOT-223 returns nothing.
- Accumulating on `swap` alone loses `rated_to: 70` the moment repair two is a
  `change_topology`, and the oscillation returns one step later.

**Split `CONSTRAINT_FIELDS` by what the constraint is about.** A requirement the *board* imposes
stays true no matter what kind of part satisfies it. A field describing the part's *identity*
must be replaced when a repair deliberately changes the kind of part.

| Accumulates across repairs | Replaced by each repair |
|---|---|
| `vout`, `i_out_min`, `vin_min`, `rated_to`, `rated_from`, `efficiency_min` | `mpn`, `topology`, `package`, `category`, `rail` |

Put that split in `reviewer.py` beside `CONSTRAINT_FIELDS`, as a named constant with a docstring
giving the reasoning above — `merge_constraints` in `graph/sourcing.py` is where it gets used,
and the two must not drift apart.

**Then write the merged result back to the slot**, so repair three sees repairs one and two.
`merge_constraints`' existing rule stands: the newer repair wins on a conflicting key.

**Test:** a slot repaired for `rated_to` and then for `rated_from` reaches the second search
carrying both. A slot repaired for `package` and then given a `change_topology` reaches the
second search with the new topology and **without** the old package. A third repair sees the
first two.

---

## Environment

**Use the project virtualenv, not the system Python.**
`/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`. The anaconda Python on the
PATH has no `langgraph` and produces 12 collection errors unrelated to your work.

Run the suite from `backend/`, and do **not** pass `-q` — it swallows the summary line here:

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

**If PostgreSQL is unreachable in your sandbox, say so plainly** rather than reporting a partial
count as the whole suite. That has happened on three previous tasks and each time the full run
found failures the partial did not.

`timeout` does not exist on this machine.

## Do not

- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not commit, push, or branch.**
- **Do not edit anything under `docs/`.** If the brief is wrong, say so and stop.
- **Do not change `MAX_REPAIRS` itself.** Three is the intended cap; the comparisons are wrong,
  not the constant.
- **Do not widen `CONSTRAINT_FIELDS`.** The split is over the keys that already exist.
- **Do not update an existing test's expectation to make it pass.** Fix 1 changes behaviour by
  design and a cap test may legitimately move — say so. Anything else moving is a finding.

## Report

1. Exact pytest counts before and after, with the command. Say explicitly if the full suite
   could not run.
2. Every file changed and what changed in it.
3. Any other comparison against `MAX_REPAIRS` you found.
4. Any existing test whose expectation moved, and why.
