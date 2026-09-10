# Task · BUILD item 31 — the four desks exist

**Repository** `~/Documents/GitHub/continuity`. Backend in `backend/`, frontend in `frontend/`.
**Baseline** 1115 passed, 20 skipped with a database. **Do not commit or push without being asked.**

The assigned scenario names design, procurement and production. `api/store.py:71` reads
`ROLES = ("engineering", "procurement", "quality")`, so **the third department cannot be
granted, assigned or signed as**, and `roles.py:30-31` routes the two rules that are
production's to engineering. This item makes the product able to express the departments
before anything else in Phase 8 tries to route to them.

Nothing here changes what is on screen. That starts at item 33.

## Why four and not three

A change control board's composition *"should mirror the change's blast radius: engineering,
quality, manufacturing and procurement at minimum"* — [SCENARIO-B.md](../SCENARIO-B.md).
Manufacturing is the topic's production. Quality is the fourth because the approved
manufacturer list has to have an owner and `part_qualification` is already addressed to it.

## 1 · The role list — `continuity/api/store.py`

```python
ROLES = ("engineering", "procurement", "production", "quality")
```

Ordered as the topic orders them, with quality last. **There is no migration.** The column is
`roles text[] NOT NULL DEFAULT '{engineering}'` (`api/schema.sql:210`) with no CHECK
constraint, and the only enforcement is `store.py:242`, which raises `UnknownRole` against this
tuple. Confirm that by reading both before changing either.

## 2 · The routing table — `continuity/roles.py`

Move production's two rules off engineering:

```python
    # Whether the substitute can be assembled onto the board this company already builds.
    # SCENARIO-B maps "production confirms assembly compatibility" onto exactly these.
    "footprint": ("production",),
    "footprint_compatibility": ("production",),
```

Leave every other entry alone. `availability` and `source_approval` are already procurement's,
`part_qualification` is already engineering and quality, and the rest are design's.

Update the docstring under `ROLES_BY_RULE` so it names four desks rather than describing
"everything else" as a circuit question.

## 3 · Four accounts — `backend/tools/seed_world.py`

Replace the `ENGINEER` / `APPROVER` pair with four, one desk each:

| Account | Role |
|---|---|
| `engineer@northwind.example` | engineering |
| `procurement@northwind.example` | procurement |
| `production@northwind.example` | production |
| `quality@northwind.example` | quality |

Same password, `continuity-demo-2026`. The first account still creates the organisation and
the other three join it through `add_user_to_organisation`, exactly as the approver does now.

**One desk each, deliberately.** A person holding two desks can sign for both, which makes
item 35's separation of duties untestable and makes *this is not your decision* a claim about
navigation rather than about authority.

`CONTINUITY_MAIL_ORG=engineer@northwind.example` is unchanged: it resolves an organisation
from an address, and the engineer still owns the organisation.

Update the block that prints the accounts at the end of `main()` to print all four.

## 4 · The places that name the accounts

- `demo.sh` — the two lines printed after the URL become four.
- `docs/world-finals/RUNNER.md` — the account table under **Start**.
- `docs/world-finals/OPERATING.md` — §2's login probe stays the engineer; no other change.
- `backend/tests/test_seed.py` — expectations about how many users the seed creates.

## 5 · Tests

**The new one, and it is the point of this item.** `backend/tests/test_roles.py` already asserts
every rule in `rules.py` appears in `ROLES_BY_RULE`. Add the other direction:

```python
def test_every_desk_the_routing_table_names_is_a_role_the_product_has():
    """The reverse of the completeness test above.

    `ROLES_BY_RULE` named a department for six days that `store.ROLES` did not have, so a
    rule could route to a desk nobody could hold. The two directions catch different
    mistakes and both are cheap.
    """
    named = {role for roles in ROLES_BY_RULE.values() for role in roles}
    assert named <= set(store.ROLES)
```

Then: `footprint` routes to production; a user may be created holding `production`; and
`UnknownRole` still fires for a role outside the four.

**Remove the guard and confirm the test fails** before moving on.

## Done when

`../.venv/bin/python -m pytest` is green offline, the database suite is green, `./demo.sh`
prints four accounts, and signing in as `production@northwind.example` works. Nothing on any
screen has changed, which is expected.
