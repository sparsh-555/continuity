"""Product-line exposure lookup, kept separate from `/lines` to avoid path collisions."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from .auth import current_user, store_of
from .store import User

router = APIRouter(prefix="/exposure", tags=["exposure"])


@router.get("")
async def exposure(
    request: Request, mpn: str = Query(min_length=1), user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    return await store_of(request).lines_exposed_to(user.org_id, mpn)
