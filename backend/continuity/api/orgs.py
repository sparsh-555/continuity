"""The company: who is in it, and which projects each of them was brought in on.

Scenario B is a cross-team response, and every screen in this product has shown the *work*
while saying nothing about the *team*. A judge watching four people sign one change has to
take the sharing on faith, because no surface states who is in the company or what each of
them can reach.

## The sharing boundary moved, and it moved here

Everything else authorises on `org_id`, which answers *is this your company's work*. That was
enough while a company was the unit of sharing and stopped being enough the moment somebody
could be brought in on three projects rather than on everything: an unticked project would
have been visible anyway, and a checkbox that does nothing is worse than no checkbox. Since 11
September a product line is visible because there is a `line_access` row for it, so an invite
to two projects means two projects.

## An invitation is a union, never a replacement

Inviting somebody adds desks and adds projects. There is no call here that takes a desk away
or removes a project, deliberately: *bring this person in on this* and *take this away from
this person* are different acts, they want different confirmations, and only the first one is
a thing this product claims to do. Somebody who already holds a desk keeps it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .auth import current_user, store_of
from .store import UnknownRole, User

router = APIRouter(prefix="/orgs", tags=["orgs"])


class Invite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    """Who to bring in. **An account has to exist already**, and that is a real limit rather
    than an oversight: an invitation with no account behind it needs a token, an expiry and
    a way to accept, and this product would rather say it cannot than pretend to send one."""

    roles: list[str] = Field(min_length=1, max_length=4)
    """The desks they will hold, added to whatever they already hold."""

    line_ids: list[str] = Field(default_factory=list, max_length=200)
    """The projects they are being brought in on. Empty is allowed and means the company
    only — somebody who can be asked about a change without being able to browse the work is
    a real state, and refusing it would be inventing a rule."""


def _member(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "roles": list(row["roles"] or ()),
        "line_ids": list(row["line_ids"] or ()),
        "joined_at": row["created_at"].isoformat(),
    }


@router.get("/members")
async def members(request: Request, user: User = Depends(current_user)) -> list[dict[str, Any]]:
    """Who is in this company, what they hold, and which projects they can open."""
    rows = await store_of(request).members_for_org(user.org_id)
    return [_member(row) for row in rows]


@router.post("/invites", status_code=201)
async def invite(
    body: Invite, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Bring a teammate in on some projects.

    Three things happen and the order matters: the account is found, the desks are added, and
    the projects are granted. A grant to somebody who is not in the company yet would be
    invisible rather than wrong, so the join comes first — and `add_user_to_organisation`
    moves everything they created with them, which is why a person who signed up on their own
    and is then invited does not leave a stranded company behind.
    """
    store = store_of(request)

    invited = await store.user_by_email(body.email)
    if invited is None:
        raise HTTPException(
            404,
            f"no account uses {body.email}. Create it from the sign-up screen first, then "
            "invite it here.",
        )

    # Union, not replacement. See the module docstring: an invitation adds.
    roles = sorted(set(invited.roles or ()) | set(body.roles))
    try:
        await store.add_user_to_organisation(invited.id, user.org_id, roles)
    except UnknownRole as error:
        raise HTTPException(422, str(error)) from error

    granted = await store.grant_lines(body.line_ids, invited.id, user.org_id)
    row = next(
        (
            member
            for member in await store.members_for_org(user.org_id)
            if member["id"] == invited.id
        ),
        None,
    )
    return {"granted": granted, "member": _member(row) if row else None}
