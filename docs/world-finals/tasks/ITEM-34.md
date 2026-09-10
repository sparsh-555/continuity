# Task · BUILD item 34 — a substitution on a shipping product needs every affected department to sign

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** items 31, 32, 33.

`review.choose` (`review.py:152-162`) hardcodes `roles=("engineering",)` for any candidate that
clears every rule, and `change._approvals_for` (`change.py:293-309`) falls back to engineering
when nothing failed. **A department is therefore consulted only when the answer is a
compromise, and never when it is good.**

The standard this is held to is already quoted in [SCENARIO-B.md](../SCENARIO-B.md), from the
field's own audit findings:

> *"Any change to a released design must be approved before implementation — no exceptions.
> Emergency changes should follow an expedited approval process, not bypass approval
> entirely."*

That is why this is not gaming the demo. A part substitution on a released design affects
design electrically, procurement commercially, production on the line and quality on the
approved list, and a real change board is signed by all of them whether or not anything failed.

## 1 · Who has to sign

One rule, in `continuity/roles.py` beside `by_department`:

```python
def desks_that_must_sign(verdicts) -> tuple[str, ...]:
    """Every department that actually looked at this change.

    A desk is on the hook when at least one of its rules returned `satisfied`, `failed` or
    `evidence_missing` — it examined the change and has standing. `not_assessed` and
    `not_applicable` do not count: a rule the engine declines to run on any board is not a
    department's involvement in this one.
    """
```

On the Gateway that is all four. On a board with no buses, `interface_role_match` is
`not_applicable` and design still signs, because eight other design rules ran.

## 2 · `continuity/review.py`

`choose`'s first pass stops naming engineering:

```python
            return Proposal(
                mpn=candidate.mpn,
                roles=desks_that_must_sign(candidate.verdicts),
                detail=f"Clears every check on this board{margin}.",
            )
```

`gate_rule` stays `None` for a clear candidate, so `conditional` keeps meaning *a rule failed
and a desk has to accept it* rather than *somebody has to sign*. Those are different sentences
and the change request prints both.

The second pass keeps `decision_roles(gate)` as the desk that owns the **failure**, and adds
the rest of `desks_that_must_sign` — the failing desk has something to accept, the others still
have something to approve. Record which is which; item 35 needs it.

## 3 · `continuity/change.py`

`_approvals_for` becomes the same function. Delete the `DEFAULT_DECISION_ROLES` fallback: it
exists only to answer *"who signs when nothing failed"*, which now has a real answer.

Keep the other half of its docstring — *"a request with no proposal asks for nothing and needs
nobody: it is a finding, not a change"* — and keep returning an empty tuple when there is no
proposal.

## 4 · The screens

`RequestCard.tsx`'s `APPROVALS` block already renders `approvals_required.join(' and ')` and
will show four desks with no change. Two things to add:

- Mark the desk that owns a **failure** differently from a desk that is merely required, since
  one is being asked to accept something and the other to approve. Words, not colour alone.
- `ReviewLanes.tsx`'s question block reads `{roles.join(' or ')} decides`. With several desks
  required it is **and**, not **or**, and item 35 makes that literal. Change the word now and
  leave the button behaviour to item 35.

## 5 · Tests

- A clear candidate on the Gateway proposes with all four desks and `gate_rule is None`.
- A candidate whose only failure is `availability` proposes with procurement marked as the
  owner of the failure and the other three still required.
- A board where a desk's rules all return `not_assessed` does not put that desk on the hook.
- The change request for a clear proposal names four desks; for no proposal, none.

Expect breakage in the four `approvals_required` assertions and in
`test_review.py::test_a_gated_candidate_says_it_works_before_it_says_who_must_sign`.

## Done when

Every change request on `/changes` names every department that looked at the change, and the
demo can no longer be walked with one account. That is item 35's problem and it is the point.
