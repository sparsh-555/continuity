# Task · BUILD item 11b — a decision names who may answer it

**Repository** `~/Documents/GitHub/continuity`. Backend in `backend/`, frontend in `frontend/`.
**Depends on item 11a** — organisations, `users.roles`, org-scoped ownership. Do not start
until that is in the working tree.
**Do not commit or push. Do not deploy.**

An open decision carries the roles permitted to answer it, `/resume` enforces that, and a
waiver stops applying when the thing it was granted for changes. Gates, AML/AVL and the change
request are items 13 and 15 and are **not** in this task.

---

## Why a decision, and not a user, holds the permission

`/resume` authorises with `thread_for_user`: you may answer a question if you own the run. Item
11a widened that to the organisation, which is necessary and not sufficient — it now lets
*anyone* in the company answer *any* question, and "procurement signed off the junction
temperature" is a worse failure than the 404 it replaced.

The permission belongs to the **question**, because that is where the expertise is. Whether an
LDO's 159 °C junction is acceptable is an engineering judgement; whether a distributor is an
approved source is not, and no property of the user can tell those apart.

## The LangGraph constraint that decides the design

The repo pins `langgraph 1.2.11`. Two documented behaviours govern this task:

1. **Resuming re-executes the interrupting node from the top.** `interrupt()` returns the
   answer on the second pass; everything above it in the node runs again.
2. **Resume values are matched to `interrupt()` calls by index**, so the calls must not be
   reordered, conditionally skipped, or looped non-deterministically.

Both say the same thing here: **the authorisation check happens at the HTTP boundary, before
the graph is invoked at all.** A refusal inside the node would have already re-run that node's
work, and would consume or misalign the pending interrupt. `nodes.py`'s module docstring
already warns about this under "The interrupt gotcha" — read it before you touch a node.

## 1 · The roles ride on the interrupt payload

Both interrupts — `clarify`'s `question_id: "supply"` and `escalate`'s `"escalation"` — emit a
dict. Add `roles` to it, a list from the `ROLES` vocabulary item 11a defined.

The payload is the right carrier because LangGraph retains it on the pending task, so
`api/app.py::_pending_question` can already read it out of a checkpoint written by a different
process — which is exactly the situation `/resume` has to authorise in.

`clarify` asks what the board is powered from: **engineering**.

`escalate` depends on the conflict. Add a mapping beside `REQUIREMENT_FIELD_BY_RULE`:

```python
ROLES_BY_RULE = {
    "availability":        ("procurement",),
    "lifecycle":           ("procurement",),
    "thermal_dissipation": ("engineering",),
    "current_budget":      ("engineering",),
    "voltage_overlap":     ("engineering",),
    "pin_budget":          ("engineering",),
    "interface_role_match":("engineering",),
    "footprint_compatibility": ("engineering",),
    "capacitor_requirements":  ("engineering",),
}
```

A rule that is not in the map falls back to **engineering**, and the fallback is deliberate
rather than incidental: an unmapped electrical rule reaching procurement would be the failure
this task exists to prevent, and engineering is the safe direction to be wrong in. A rule
missing from a map is not an error the user should discover on stage, so add a test that every
rule in `rules.RULES` has an entry — a rule added later that silently inherits a default is how
this rots.

`_pending_question` carries `roles` through to the client, and the `question` event gains it in
the wire contract.

## 2 · `/resume` enforces it — `backend/continuity/api/app.py`

Before constructing the `Command`:

1. Resolve the thread through the organisation-scoped lookup. Still **404** on a miss: an
   organisation the caller is not in must not learn the thread exists.
2. Read the pending interrupt's payload from the checkpoint.
3. If it names roles and the caller holds none of them, **403** — with a message naming the
   roles required. This is the one place a 403 is right: the caller can already see this run,
   so the refusal reveals nothing they did not know, and "you are not the right person for this
   question" is information they need in order to fetch the person who is.
4. A pending interrupt with no `roles` — a run paused before this task existed — is answerable
   by anyone in the organisation. Old runs must not become unanswerable.

Do the same for `/threads/{id}/continue`? **No.** Continuing a stopped run is not answering a
question; it needs organisation membership and nothing more. Say so in a comment so the
asymmetry reads as a decision.

## 3 · A waiver is scoped to what it was granted for

`state["accepted"]` holds `(rule, subject)` pairs, and `_apply_waivers` marks any matching
failure as accepted. That is too wide in the way that matters: accept a thermal failure on one
regulator, and the waiver silently covers the *next* regulator a repair puts in that slot —
a part nobody looked at, carrying a temperature nobody approved.

Scope each entry to `(rule, subject, mpn, revision)`:

- **mpn** — the part in the slot when the waiver was granted. A repair changes it and the
  waiver evaporates, which is the behaviour BUILD asks for: *an approval granted for one
  candidate does not carry to the next.*
- **revision** — the product line's revision, which item 10b stores. A profile change means new
  operating conditions, so an approval given under the old ones has to be asked again.

`revision` reaches the graph the way `profile` already does: `/design` loads the line, so add it
to `DesignState` beside `profile` and read it in `escalate`. A run with no revision — a scratch
line — uses `None`, and `None` matches `None`, so scratch runs behave exactly as they do now.

**Existing entries in a live checkpoint are 2-tuples.** A run paused before this change resumes
into code that will unpack four. Handle the short form as "matches any mpn and any revision"
rather than crashing, and say in a comment that this is a compatibility path with a date on it.

## Tests

The two from BUILD, and they are the point of the task:

1. A procurement user resumes an engineer's run at a **procurement** gate and succeeds; the
   same user is refused **403** at an engineering gate. Assert the message names the role.
2. An approval granted for one candidate does not carry to the next: waive a thermal failure,
   let a repair swap the part, assert the new part's failure is **not** accepted.

And:

3. A waiver survives a re-validation that does *not* change the part.
4. A change of revision drops the waiver.
5. Every rule in `rules.RULES` has an entry in `ROLES_BY_RULE`.
6. A pending interrupt with no `roles` is answerable by any member of the organisation.
7. A thread in another organisation is **404**, not 403, at `/resume`.

## Environment

**Use the project virtualenv**, `/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`.

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

Do not pass `-q`. **The store tests need that database and skip silently without it. Say
plainly whether PostgreSQL was reachable rather than reporting a pass.**

Frontend: `bun` is the runtime, not node. Typecheck with `bunx tsc -b --noEmit`.

`timeout` does not exist on this machine.

## Do not

- **Do not deploy, commit, push, or branch.**
- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.**
- **Do not edit anything under `docs/`.**
- **Do not put the authorisation check inside a graph node.** Read "The interrupt gotcha".
- **Do not reorder or conditionally skip any `interrupt()` call.** Resume values match by index.
- **Do not build gates, AML/AVL, or the change request.** Items 13 and 15.
- **Do not add a roles UI.** Item 13 builds the screen a role is visible on.
- **Do not make a 404 into a 403 for a thread outside the caller's organisation.**

## Report

1. Exact pytest counts before and after, **and whether PostgreSQL was actually available.**
2. Frontend typecheck result.
3. Every file changed.
4. **What happens to a run that was paused before this change and resumes after it** — the
   2-tuple waiver and the payload with no `roles`. Show the code path for each.
5. Anything in this brief that did not reconcile with the code.
