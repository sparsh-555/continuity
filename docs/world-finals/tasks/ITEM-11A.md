# Task · BUILD item 11a — a product line belongs to a company, not to a person

**Repository** `~/Documents/GitHub/continuity`. Backend in `backend/`, frontend in `frontend/`.
**Baseline** 796 passed, 5 skipped. **Do not commit or push. Do not deploy.**

Ownership moves from the person who typed the brief to the organisation they work for, and a
user gains the roles they hold. Decision authorisation, gates and waiver scoping are item 11b
and are **not** in this task.

---

## Why this, and why now

Continuity has one owner per thing. `product_lines.user_id`, `threads.user_id`,
`findings.user_id`, `line_parts.user_id` — fifteen `WHERE` clauses, and each of them says the
same thing: *you may see what you personally created*.

Scenario B cannot be told inside that model. An end-of-life notice affects three product lines
across three departments; engineering decides whether a substitute is electrically sound,
procurement decides whether the source is approved, quality decides whether it is qualified.
Those are three people looking at **one** run. Under per-user ownership the second of them gets
a 404, and the deliberate reason for that 404 — `thread_for_user` is the authorisation boundary
— is exactly right and exactly the thing that has to change.

A product line is a thing a **company** ships. That is the concept the product is short of, and
adding a sharing flag or a second lookup path beside the existing one would be the parallel
concept this project has already rejected once. Migrate.

## The one thing to be careful about

**A user's own data must still be reachable, and nobody else's must become reachable.** Every
existing account becomes an organisation of one, so behaviour for them is unchanged. Prove it:
a test that a second organisation sees nothing of the first is worth more than any other test
in this task.

## 1 · Schema — `backend/continuity/api/schema.sql`

Read the file's header and the 7 Sep migration already in it. Statements run at startup on
every boot and must be no-ops the second time.

```sql
CREATE TABLE IF NOT EXISTS organisations (
    id         text PRIMARY KEY,
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id text REFERENCES organisations(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS roles text[] NOT NULL DEFAULT '{engineering}';
```

Then `org_id` on `product_lines`, `threads`, `findings` and `line_parts`, each with an index
that mirrors the `user_id` one it replaces.

**Back-fill before you enforce anything.** Every existing user gets an organisation of their
own — id derived from the user id, the way `_derived_id` already derives the scratch line, so
re-running cannot make a second one — and every row they own gets that `org_id`. Only once the
back-fill has run can `org_id` be read as authoritative. Write the back-fill so that running it
twice changes nothing.

`user_id` **stays on every table.** It stops being the authorisation boundary and becomes what
it always honestly was: who created this. Do not drop it; a change request that cannot say who
raised it is worse than one nobody can share.

## 2 · Roles

`roles` is a set, not a single value, and the vocabulary is exactly:

```python
ROLES = ("engineering", "procurement", "quality")
```

A set rather than one value because a person wears more than one hat, and because the demo
needs one account that can walk all three gates on stage while separate single-role accounts
prove the refusal. Reject an unknown role at the boundary where it is set — a role nobody
checks for is a permission that silently never applies.

Default `{engineering}`: today's only interruption is an engineering trade-off — *accept the
temperature*, *relax the requirement* — so every existing account keeps working unchanged.

## 3 · Store — `backend/continuity/api/store.py`

Read that module's header, especially the paragraph on why lookups take a `user_id` rather than
filtering afterwards. **The argument is unchanged; only the column moves.** Ownership stays a
`WHERE` clause and there is still no unscoped read to reach for by accident.

Every method that takes `user_id` for *authorisation* now takes `org_id` and filters on it.
Methods that record **who acted** keep `user_id` as well and write both. Read each call site
and decide which of the two it is — this is the part of the task where a mechanical
find-and-replace produces something that passes its tests and is wrong.

`memory_for_user` becomes organisation memory. That is the intended meaning, not a side effect:
"where else did we use this part" is a better question at company scale than at desk scale, and
it is the question the memory graph was built to answer.

Add `create_organisation`, and `add_user_to_organisation(user_id, org_id, roles)`. There is no
UI for either — item 16 seeds the demo world and item 11b's tests build the situation directly.
Do not add an invite screen, and do not add a button that does nothing.

## 4 · API and frontend

`current_user` returns the user with `org_id` and `roles`; routes pass `user.org_id` where they
pass `user.id` today. `/auth/me` should report the roles, because the client will need them at
item 13 and a field that appears later is a second migration.

Frontend changes are whatever the typechecker demands and nothing more. **No roles UI.** Item
13 builds the gates that make a role visible; a role chip on a screen that gates nothing is a
label over something we have not built.

## Tests

1. **Two organisations are invisible to each other.** Create two, each with a line, a thread, a
   BOM row and a finding. Every listing method, from both sides. This is the test that matters.
2. Two users in **one** organisation see the same lines and the same threads.
3. The migration back-fills: create the pre-migration shape with a user, a line and a thread,
   apply `schema.sql`, assert the user has an organisation, the rows carry its id, and nothing
   is orphaned. Then apply it **again** and assert nothing changed — the second application is
   the one that matters, because this file runs on every boot.
4. An unknown role is refused.
5. `roles` defaults to `{engineering}` for an account created before the column existed.

## Environment

**Use the project virtualenv**, `/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`.
The anaconda Python on the PATH has no `langgraph` and gives 12 collection errors.

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

Do not pass `-q`. **The store tests need that database and skip silently without it. If
PostgreSQL is unreachable in your sandbox then the migration and every ownership test — which
is nearly all of this task — are not being tested at all. Say so plainly rather than reporting
a pass.**

Frontend: `bun` is the runtime, not node. Typecheck with `bunx tsc -b --noEmit`.

`timeout` does not exist on this machine.

## Do not

- **Do not deploy, commit, push, or branch.**
- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not edit anything under `docs/`.**
- **Do not drop `user_id` from any table.**
- **Do not build gates, decision routing, or waiver scoping.** Item 11b.
- **Do not add an invite flow, a roles screen, or a role chip.**
- **Do not leave a lookup that authorises on `user_id` where it should authorise on `org_id`,
  or the reverse.** Both directions are a security bug: one leaks, the other locks a user out
  of their own board.

## Report

1. Exact pytest counts before and after, **and whether PostgreSQL was actually available.**
2. Frontend typecheck result.
3. Every file changed.
4. **Every store method, listed, with which of `org_id` / `user_id` / both you gave it and why.**
5. Anything in this brief that did not reconcile with the code.
