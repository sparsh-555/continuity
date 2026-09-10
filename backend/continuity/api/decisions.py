"""What each desk owes, across every product line.

## Why this exists

A substitution on a released design is signed by every department that examined it. Three of
those four people had no way to find the thing they had to sign: the decision lived on a
product line's page and on the notice that raised it, and a person at the procurement desk
would have had to know which product line it was on and navigate there. DEFERRED carried
*"nothing tells the desk that a decision is waiting for it"* from 8 September.

## Ownership is by role, not by organisation

A colleague who holds none of the desks a decision names sees an empty list rather than a
403. There is nothing waiting for them, which is not an error and does not need explaining.

## It does not answer anything

Answering is `POST /decisions/{id}`, which already exists and already enforces who may sign.
A second answer path would be a second place for the authorisation to be right.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from .auth import User, current_user, store_of

router = APIRouter(tags=["decisions"])


@router.get("/decisions")
async def waiting_on_me(
    request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    """Every pending decision one of this person's desks may answer.

    Carries enough to answer without navigating: the product line and its revision, what is
    being replaced with what, the rule that raised it when one did, the desks required, and
    which of them have already signed.
    """
    rows = await store_of(request).decisions_waiting_on(user.org_id, list(user.roles))
    return [
        {
            "id": row["id"],
            "line_id": row["line_id"],
            "line_name": row["line_name"],
            "revision": row["revision"],
            "notice_id": row["notice_id"],
            "notice_mpn": row["notice_mpn"],
            "refdes": row["slot_id"],
            "retiring": row["retiring"],
            "proposal": row["proposal"],
            "gate_rule": row["gate_rule"],
            "detail": row["detail"],
            "roles": list(row["roles"] or ()),
            "signed": sorted(row["signed"] or ()),
            # What this particular reader still owes, which is the only part of the list
            # that is about them rather than about the change.
            "mine": sorted(set(row["roles"] or ()) & set(user.roles) - set(row["signed"] or ())),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
