# Task · BUILD item 10b — a product line holds a BOM, a profile and a revision

**Repository** `~/Documents/GitHub/continuity`. Backend in `backend/`, frontend in `frontend/`.
**Baseline** 781 passed, 5 skipped. **Do not commit or push. Do not deploy.**

Item 10a renamed the container. This one gives it contents: the bill of materials it ships,
the conditions it operates under, and the query that answers *"which of my products contain
this part"*. Roles, gates, fan-out and the matrix are items 11–13 and are **not** in this task.

---

## Why this shape

Continuity has only ever worked in one direction: read a brief, choose parts, check the board
it just built. Every input arrived in the request and nothing about a board outlived the run.

Scenario B runs the other direction. A manufacturer retires a part; the question is which of
the products *already shipping* contain it, and whether a proposed substitute survives each
one's own conditions. Those conditions — the ambient inside a sealed enclosure, the copper the
regulator is mounted on, the rail load somebody measured and signed — belong to the product,
not to a sentence a user types today. They have to be stored.

Two storage choices carry the weight, and they go opposite ways.

**The BOM is a table.** Exposure matching asks "which rows, across every line I own, name this
MPN". As `line_parts(user_id, mpn)` that is one index probe. As a jsonb array on the line it is
a scan of every BOM the account owns, deserialised, to answer the single most-run query in the
enterprise flow.

**The profile is a jsonb column.** It is read whole, applied whole, and never filtered on. Six
typed columns would buy nothing and cost a migration every time a new operating condition
becomes checkable.

## 1 · Schema — `backend/continuity/api/schema.sql`

Read the file's header and the item 10a migration already in it before adding anything. Growth
arrives as its own idempotent statement; this file runs at startup on every boot.

```sql
ALTER TABLE product_lines ADD COLUMN IF NOT EXISTS revision text;
ALTER TABLE product_lines ADD COLUMN IF NOT EXISTS profile jsonb;

CREATE TABLE IF NOT EXISTS line_parts (
    line_id      text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    user_id      text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refdes       text NOT NULL,
    mpn          text NOT NULL,
    manufacturer text,
    footprint    text,
    populated    boolean NOT NULL DEFAULT true,
    PRIMARY KEY (line_id, refdes)
);

CREATE INDEX IF NOT EXISTS line_parts_mpn_idx ON line_parts(user_id, mpn);
```

`user_id` is denormalised off `product_lines` deliberately, for the same reason `threads.user_id`
already is: exposure matching is an authorisation boundary, and an ownership check should not
depend on a join. Write a comment saying so, in the voice of the ones around it.

`(line_id, refdes)` as the primary key states the real constraint — a board has one C14 — and
makes a re-uploaded BOM an upsert rather than a duplicate.

`populated` matters: a do-not-populate row is on the BOM and is not on the board. A DNP part
must **not** appear in exposure results; the whole point of exposure is what is actually
shipping.

## 2 · The operating profile — new module `backend/continuity/profile.py`

Top level, beside `interpret.py`, because both the API and `tools/` need it and it is not an
engine rule.

```python
@dataclass(frozen=True)
class OperatingProfile:
    ambient_c: int
    ambient_source: str
    mounting: str | None = None
    rails: Mapping[str, RailProfile] = ...
```

`RailProfile` carries `voltage`, `i_limit`, `basis`, `i_load`, `i_load_basis` — every field of
`engine.models.Rail` a product line states about itself, and none of the ones a *design*
derives (`source` and `members` describe the topology, which comes from the BOM).

Two functions, both pure, both returning new objects:

- `profile.to_requirements(base: Requirements) -> Requirements` — `replace()` on the fields the
  profile states, leaving the rest alone. A profile that does not state `mounting` must not
  erase one.
- `profile.applied_to(board: Board) -> Board` — a new `Board` whose requirements and rails carry
  the profile's numbers. A rail named in the profile that does not exist on the board is an
  **error**, not a silent skip: a stored 45 °C condition that reaches no verdict is exactly the
  failure mode the five coverage labels exist to prevent, and it would be invisible.

`from_json` / `to_json` round-trip it. **Both directions are strict about unknown keys.** A key
written by a newer version and ignored by an older one is a stored operating condition that
never reached a check, and the board still goes green. Raise.

**The thing that must be proved:** a profile carrying LINE_B's stored values, applied to a board,
produces exactly the `Requirements` and `Rail` objects that
`tools/eol_differential.make_board(LINE_B, …)` builds by hand today. Write that test. Two
constructions of the same product line that disagree is the defect this task can most easily
introduce, and it would show up as a demo whose stored data quietly checks something else.

## 3 · Store — `backend/continuity/api/store.py`

Read that module's header. **Every method takes `user_id` and filters on it in the `WHERE`
clause.** Not fetch-then-compare — the header explains why, and this table is reached by an
endpoint that takes an MPN from the caller.

- `save_bom_rows(line_id, user_id, rows)` — replaces the line's BOM as a unit, inside one
  transaction. A BOM is a document with a revision, not a set of independently editable rows;
  a partial replacement leaves a board that never existed.
- `bom_for_line(line_id, user_id)`
- `save_profile(line_id, user_id, profile, revision)`
- `lines_exposed_to(user_id, mpn)` → the lines that populate that MPN, each with the refdes list
  where it appears. One query, `JOIN product_lines` for the name and revision, `WHERE populated`.

Add `revision` and `profile` to the `Line` dataclass. `Line(**row)` is used in several places,
so every `SELECT` that builds one has to grow the columns — check each.

MPN matching is exact, on the string as stored. Manufacturer part numbers are not
case-normalised anywhere else in this codebase and inventing a fold here would put two
spellings of matching in the product. If a fold is wanted, it is its own decision with its own
test, not a detail of this task.

## 4 · API — `backend/continuity/api/lines.py`, new `backend/continuity/api/exposure.py`

On the lines router:

- `GET /lines/{id}/bom`, `PUT /lines/{id}/bom` — replace the whole list.
- `GET /lines/{id}/profile`, `PUT /lines/{id}/profile` — profile and revision together.

Exposure gets its own router and is registered in `app.py` beside the others:

- `GET /exposure?mpn=…` → `[{line_id, name, revision, refdes: [...]}]`

**Do not put `/exposure` on the lines router.** `/lines/exposure` and `/lines/{line_id}` are the
same shape to a path matcher, and it would work only for as long as nobody reorders the file.

Validate the BOM payload with pydantic at the boundary, as the other routes do: `refdes` and
`mpn` non-empty, a bounded row count, and a duplicate `refdes` in one payload is a 422 rather
than a silent last-write-wins.

## 5 · Frontend — a read-only strip on the line page

`frontend/src/app/routes/lines.tsx` and `src/app/lib/api.ts`.

The line detail shows its revision, its part count and its ambient — "Rev C · 187 parts · 45 °C
ambient (gateway operating profile Rev C)" — reading the source string beside the number, as
every other surface in this product does. A line with no profile stored says so plainly; it
does not render a default as though it were data.

No editor. Nothing on this screen writes. The matrix that consumes all of it is item 12 and the
seeded world that fills it is item 16; what this needs to prevent is a capability that exists
in the database and nowhere a person can see, which has already happened twice in this project
and both times was caught in a browser rather than by a green suite.

## Tests

The two from BUILD, plus the round-trip:

1. An MPN present in three of five lines returns exactly those three — and a fourth line
   carrying it as `populated = false` is **not** among them.
2. A board built from a stored line uses that line's ambient, copper and load with none of the
   three passed in.
3. A profile round-trips through JSON unchanged, and an unknown key raises.
4. Exposure never crosses accounts: two users own lines carrying the same MPN and each sees
   only their own. Assert this against the query, not against the route.
5. Re-uploading a BOM replaces it rather than accumulating.

## Environment

**Use the project virtualenv**, `/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`.
The anaconda Python on the PATH has no `langgraph` and gives 12 collection errors.

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

Do not pass `-q`. **The store tests need that database and skip silently without it. If
PostgreSQL is unreachable in your sandbox then `line_parts`, the exposure query and the
transaction — most of this task — are not being tested at all. Say so plainly rather than
reporting a pass.**

Frontend: `bun` is the runtime, not node. Typecheck with `bunx tsc -b --noEmit`.

`timeout` does not exist on this machine.

## Do not

- **Do not deploy, commit, push, or branch.**
- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not edit anything under `docs/`.**
- **Do not build roles, gates, fan-out, the matrix, or a BOM editor.** Items 11–13.
- **Do not weaken or drop a `user_id` filter.**
- **Do not change `tools/eol_differential.py`.** It is the reference the profile must agree
  with; if they disagree, the profile code is what is wrong.

## Report

1. Exact pytest counts before and after, **and whether PostgreSQL was actually available.**
2. Frontend typecheck result.
3. Every file changed.
4. Anything in this brief that did not reconcile with the code.
