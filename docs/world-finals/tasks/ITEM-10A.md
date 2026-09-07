# Task · BUILD item 10a — a project becomes a product line, everywhere

**Repository** `~/Documents/GitHub/continuity`. Backend in `backend/`, frontend in `frontend/`.
**Baseline** 778 passed, 5 skipped. **Do not commit or push. Do not deploy.**

A rename, carried all the way through: schema, store, API, routes and every user-facing word.
The new capability — bills of materials, operating profiles, exposure matching — is item 10b
and is **not** in this task.

---

## Why a rename and not a second table

A **project** is what Continuity called a container while it designed one board from a brief.
A **product line** is what that container actually is in the enterprise story: a thing the
company ships, which a change notice can affect. It holds the same threads and the same
findings — an EOL run against a line is a thread on it exactly as a design run is.

Adding `product_lines` beside `projects` was considered and rejected. Two containers means two
list screens, two ownership checks, two sets of endpoints, and a demo where the navigation
reads **Projects** while the pitch says product lines. Coherence is the deliverable here.

`is_walkthrough` keeps its meaning: the walkthrough is a product line with one design thread.

## 1 · The migration — `continuity/api/schema.sql`

**Read the file's header first.** It says `CREATE TABLE IF NOT EXISTS` is enough *"while the
schema only grows"*, and that a real migration belongs there the moment a column has to change.
This is that moment, and this is the first change in the project that can leave the deployed
app **down** rather than merely wrong. Write it accordingly.

Every statement must be a no-op on a database that has already been migrated, because it runs
at startup on every boot:

```sql
ALTER TABLE IF EXISTS projects RENAME TO product_lines;
```

A column rename has no `IF EXISTS` form, so guard each one:

```sql
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'threads' AND column_name = 'project_id') THEN
        ALTER TABLE threads RENAME COLUMN project_id TO line_id;
    END IF;
END $$;
```

The same for `findings.project_id`. Rename the indexes too — `projects_user_idx` surviving on a
table called `product_lines` is exactly the drift this task exists to remove. Foreign keys
follow a table rename automatically; do not drop and recreate them.

Put the whole migration at the end of the file under a dated comment explaining what it does
and that it is idempotent, in the style of the comments already there. **Leave the original
`CREATE TABLE ... projects` statement where it is and rewrite it to create `product_lines`** —
a fresh database must end up in the same state as a migrated one, and that is the property to
verify.

## 2 · Backend

`store.py`, `app.py`, `projects.py` (rename the module to `lines.py`), `bom.py`. The names
change with the concept: `create_project` → `create_line`, `projects_for_user` →
`lines_for_user`, `project_id` → `line_id`, and so on. Keep the scoping exactly as it is —
every query that filters on `user_id` today must still filter on it.

API paths become `/lines`. **This is a breaking change to the wire and that is intended**; the
frontend in this same task moves with it. Do not leave a `/projects` alias — a compatibility
shim is the parallel concept this task exists to avoid, in a different costume.

## 3 · Frontend

`routes/projects.tsx` becomes `routes/lines.tsx`, the route path with it, and every call in
`lib/api.ts` and `lib/sseClient.ts`. Then the words a person reads: the side rail, the empty
state, the page heading, button labels. "All projects" becomes "All product lines", "New
project" becomes "New product line", and so on — read each string and choose what is right in
context rather than substituting mechanically.

## 4 · The one thing that must be proved, not assumed

**A migrated database and a fresh one must end up identical.** Write a test that:

1. Creates the pre-migration schema — the `projects` table as it was, with a row in it and a
   thread referencing it.
2. Applies `schema.sql`.
3. Asserts the row survived, is reachable as a product line, and its thread still resolves.
4. Applies `schema.sql` **a second time** and asserts nothing breaks.

The second application is the one that matters. This file runs on every boot, and a migration
that works once and throws on the next start takes the deployed app down at the worst moment.

## Tests

The suite is full of `project` names and `/projects` paths and they all move. That is expected
churn, not a finding — but **read each assertion as you change it**. An assertion that stops
meaning what it meant is the risk in a rename this wide, and a mechanical find-and-replace
through a test file is how a test ends up passing while asserting nothing.

Report any test whose *meaning* you had to change, as opposed to its spelling.

## Environment

**Use the project virtualenv**, `/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`.
The anaconda Python on the PATH has no `langgraph` and gives 12 collection errors.

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

Do not pass `-q`. **The store tests need that database and skip silently without it, so if
PostgreSQL is unreachable in your sandbox then the migration — the whole point of this task —
is not being tested at all. Say so plainly rather than reporting a pass.**

Frontend: `bun` is the runtime, not node. Typecheck with `bunx tsc -b --noEmit`.

`timeout` does not exist on this machine.

## Do not

- **Do not deploy, commit, push, or branch.** The migration runs against production at startup
  and will be applied deliberately, against a restored copy first.
- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not edit anything under `docs/`.**
- **Do not add a `/projects` compatibility alias.**
- **Do not drop and recreate any table.** There is live data in it.
- **Do not build BOMs, profiles or exposure matching.** Item 10b.
- **Do not weaken any `user_id` filter while moving it.**

## Report

1. Exact pytest counts before and after, **and whether PostgreSQL was actually available.**
2. Frontend typecheck result.
3. Every file changed.
4. Any test whose meaning, not just spelling, had to change.
5. Anything in this brief that did not reconcile with the code.
