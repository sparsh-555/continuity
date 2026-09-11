"""The company's standing lists, where the company states them.

The **AML** says which parts engineering and quality have qualified for use. The **AVL** says
which sources procurement will buy from. Both gates have been enforced since they were built,
and until 11 September neither had a writer outside `tools/seed_world.py` and the tests — so a
company could not state its own policy without a Python shell.

**The other half of that was worse than missing a screen.** Turning an AML on reports every
fitted part that is not on it, which is correct and, for a company that ships anything, means
every part on every board fails until somebody qualifies the lot. The seed does that by
deriving the list from the bills; a real company had no such step. `POST /policy/parts/from-bill`
is that step, and it is the one that makes declaring a policy possible at all.
"""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .auth import current_user, store_of
from .store import User

router = APIRouter(prefix="/policy", tags=["policy"])

AML_DESKS = ("engineering", "quality")
"""Who may qualify a part.

`roles.py` addresses `part_qualification` to these two, in the words *engineering says the
part is right, quality says it is allowed*, and the decision is satisfied when either has
signed. Keeping the list is the same decision, made in advance and for every board at once.
"""

AVL_DESKS = ("procurement",)
"""Who may approve a source. `source_approval` is procurement's alone."""


def _require(user: User, desks: Sequence[str], what: str) -> None:
    """Refuse with the desk that owns it named, the way `answer_decision` refuses.

    A 403 that says which desk keeps the list is the difference between a person knowing who
    to ask and a person concluding the button is broken.
    """
    if not set(user.roles) & set(desks):
        raise HTTPException(
            403,
            f"{what} is kept by {' and '.join(desks)}, and you hold "
            f"{', '.join(user.roles) if user.roles else 'no desk'}. Ask one of them to sign "
            f"it in, or switch desk.",
        )


class ListToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: bool | None = None
    vendors: bool | None = None


class PartEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mpn: str = Field(min_length=1, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class VendorEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distributor: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


@router.get("")
async def read_policy(request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    """Both lists, who keeps them, and what an AML would fail today if it were switched on."""
    store = store_of(request)
    lists = await store.approved_lists(user.org_id)
    entries = await store.list_entries(user.org_id)

    qualified = {mpn.upper() for mpn in (lists.parts or frozenset())}
    shipped = await store.shipped_parts(user.org_id)
    missing = [
        {"mpn": row["mpn"], "manufacturer": row["manufacturer"]}
        for row in shipped
        if (row["mpn"] or "").upper() not in qualified
    ]

    return {
        "parts": {
            "kept": lists.parts is not None,
            "entries": entries["parts"],
            # Only meaningful while the list is kept, and empty when it is not: a company
            # that has never set an AML is failing nothing, and saying it is short of 6
            # parts would be the gate reporting a policy nobody declared.
            "missing": missing if lists.parts is not None else [],
            "shipping": len(shipped),
        },
        "vendors": {"kept": lists.vendors is not None, "entries": entries["vendors"]},
        "desks": {"parts": list(AML_DESKS), "vendors": list(AVL_DESKS)},
    }


@router.put("/lists")
async def keep_lists(
    request: Request, body: ListToggle, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Declare that the company keeps a list, which is what turns its gate on."""
    if body.parts is not None:
        _require(user, AML_DESKS, "the approved manufacturer list")
    if body.vendors is not None:
        _require(user, AVL_DESKS, "the approved vendor list")
    if body.parts is None and body.vendors is None:
        raise HTTPException(400, "nothing to change: name parts and/or vendors")

    await store_of(request).keep_lists(user.org_id, aml=body.parts, avl=body.vendors)
    return {"parts": body.parts, "vendors": body.vendors}


@router.post("/parts", status_code=201)
async def qualify_part(
    request: Request, body: PartEntry, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Qualify one part, with the manufacturer the bill or the datasheet names."""
    _require(user, AML_DESKS, "the approved manufacturer list")
    await store_of(request).qualify_part(
        user.org_id, body.mpn.strip(), manufacturer=body.manufacturer, by=user.id, note=body.note
    )
    return {"mpn": body.mpn.strip()}


@router.delete("/parts/{mpn}", status_code=204)
async def release_part(
    mpn: str, request: Request, user: User = Depends(current_user)
) -> None:
    _require(user, AML_DESKS, "the approved manufacturer list")
    if not await store_of(request).release_part(user.org_id, mpn):
        raise HTTPException(404, f"{mpn} is not on the approved manufacturer list")


@router.post("/vendors", status_code=201)
async def approve_vendor(
    request: Request, body: VendorEntry, user: User = Depends(current_user)
) -> dict[str, Any]:
    _require(user, AVL_DESKS, "the approved vendor list")
    await store_of(request).approve_vendor(
        user.org_id, body.distributor.strip(), by=user.id, note=body.note
    )
    return {"distributor": body.distributor.strip()}


@router.delete("/vendors/{distributor}", status_code=204)
async def release_vendor(
    distributor: str, request: Request, user: User = Depends(current_user)
) -> None:
    _require(user, AVL_DESKS, "the approved vendor list")
    if not await store_of(request).release_vendor(user.org_id, distributor):
        raise HTTPException(404, f"{distributor} is not on the approved vendor list")


@router.post("/parts/from-bill")
async def qualify_what_we_ship(
    request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Qualify everything this company already ships, and keep the list.

    **The step the seed does by hand and a company had no way to do.** Declaring an AML is
    only possible if the company's existing boards survive it, and the honest reading of
    *these are the parts we have qualified* is the bill of materials already in front of us.
    Each entry records the manufacturer the bill carries, so the list says whose part it is
    rather than only its number.

    It keeps the list as well, because this is the action that makes keeping one possible.
    """
    _require(user, AML_DESKS, "the approved manufacturer list")
    store = store_of(request)
    shipped = await store.shipped_parts(user.org_id)
    if not shipped:
        raise HTTPException(409, "no product line has a bill of materials to qualify from")

    for row in shipped:
        await store.qualify_part(
            user.org_id,
            row["mpn"],
            manufacturer=row["manufacturer"],
            by=user.id,
            note="qualified from the bill of materials this company already ships",
        )
    await store.keep_lists(user.org_id, aml=True)
    return {"qualified": len(shipped)}
