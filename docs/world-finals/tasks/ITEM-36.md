# Task · BUILD item 36 — everyone can see what is waiting for them

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** item 35.

Once a change needs four signatures, three of those people have no way to find the thing they
have to sign. There is no endpoint: `_pending_roles` and `_pending_question` in `api/app.py`
belong to the design graph and are scoped to a thread. DEFERRED has carried *"nothing tells the
desk that a decision is waiting for it"* since 8 September.

The approver inbox is a named pattern, not an invention: *"a `/approvals` page listing all
pending tasks for current user"*, each task carrying full context, the prior approvals in the
workflow, and the decision controls.

## 1 · The store — `continuity/api/store.py`

```python
async def decisions_for_roles(self, org_id: str, roles: Sequence[str]) -> list[dict]:
    """Every pending decision any of these desks may answer, newest first."""
```

`decisions.roles` is `text[]`, so the filter is `roles && %s::text[]` with `state = 'pending'`.
Join the product line for its name and revision and the notice for the retiring MPN, so the
caller does not need a second round trip per row. Add `decisions_pending_idx (org_id, state)`
in `schema.sql`, additively.

## 2 · The endpoint — `continuity/api/decisions.py` (new)

```
GET /decisions          every pending decision addressed to a desk the caller holds
```

Each row carries: the decision id, the product line and its revision, the notice's retiring
part, the proposal, the rule that raised it when there is one, `detail`, the desks required,
the desks that have signed, and what is outstanding. Enough to answer without navigating.

**Ownership is by role, not by organisation.** A member of the organisation who holds none of
the desks sees an empty list rather than a 403 — there is nothing waiting for them, which is
not an error.

Answering reuses `POST /decisions/{id}/answer`. Do not build a second answer path.

## 3 · The screen

A route at `/approvals` and a rail entry between **Changes** and **Substitution matrix**.
`shell/SideRail.tsx` — the glyph is `how_to_reg` or `approval`; check what the icon font has
before choosing, the way the `hub` choice was made for `/memory`.

The row shows the product line, what is being substituted for what, the desk's own reason to
care — its department block from item 33 — and the two buttons. The whole point is that
procurement can answer procurement's question without reading a design trace.

**The badge.** The rail entry carries a count of what is waiting for the signed-in user. It
polls on the same tick as item 28's provider once that exists; until then a ten-second poll of
its own, matching `ARRIVALS_MS` in `routes/changes.tsx`.

## 4 · The frontend knows who you are and does not use it

`PublicUser` already carries `roles: string[]` (`lib/api.ts:26`) and **no route reads it**. Fix
that here, because this screen is meaningless without it:

- The rail, or the header, names the signed-in desk. A person on `/approvals` has to know which
  desk they are looking as.
- A question addressed elsewhere renders its buttons disabled with the desk named, rather than
  live buttons that will 403. **Do not draw an affordance that cannot be used.**

## 5 · Tests

- A decision addressed to production appears for the production account and not for the
  engineer.
- A settled decision appears for nobody.
- The engineer answering production's decision is still a 403 with the desk named.
- A user holding no desks gets an empty list and a 200.

## Done when

Signing in as any of the four accounts shows exactly what that desk owes, across every product
line, and it can be answered from there.
