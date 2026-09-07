"""Lines — the thing a dashboard lists and a run belongs to.

Every route here takes the signed-in user from `current_user` and passes it into the
query. There is deliberately no "fetch by id, then check the owner" path: ownership is a
`WHERE` clause, so there is no unscoped read available to reach for by mistake.

A miss is 404, never 403. 403 would confirm that a line exists and belongs to somebody
else, which is a fact the caller has no business learning.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from .auth import current_user, store_of
from .store import Line, Thread, User
from ..profile import OperatingProfile

router = APIRouter(prefix="/lines", tags=["lines"])


class NewLine(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class LineView(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    revision: str | None = None
    profile: dict[str, Any] | None = None
    part_count: int = 0


class BomRow(BaseModel):
    refdes: str = Field(min_length=1, max_length=100)
    mpn: str = Field(min_length=1, max_length=300)
    manufacturer: str | None = Field(default=None, max_length=300)
    footprint: str | None = Field(default=None, max_length=300)
    populated: bool = True


class BomPayload(BaseModel):
    rows: list[BomRow] = Field(max_length=10000)

    @model_validator(mode="before")
    @classmethod
    def accept_a_whole_list(cls, value: Any) -> Any:
        return {"rows": value} if isinstance(value, list) else value

    @model_validator(mode="after")
    def unique_refdes(self) -> "BomPayload":
        """A board has one C14. Two rows claiming it is a 422, not a last-write-wins.

        `(line_id, refdes)` is the table's primary key, so a duplicate would otherwise
        reach the insert and fail there — a 500 on a payload the caller could have been
        told about precisely.
        """
        refs = [row.refdes for row in self.rows]
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate refdes in BOM")
        return self


class ProfilePayload(BaseModel):
    profile: dict[str, Any]
    revision: str = Field(min_length=1, max_length=100)


class ThreadView(BaseModel):
    id: str
    prompt: str
    status: str
    summary: dict[str, Any] | None = None
    """`done.summary` as the engine emitted it, or null for a run that never finished.

    Passed through untouched. A dashboard that recomputed any of this from the BOM would
    be offering a second opinion the engine never gave."""


def _view(line: Line) -> LineView:
    return LineView(
        id=line.id,
        name=line.name,
        created_at=line.created_at.isoformat(),
        updated_at=line.updated_at.isoformat(),
        revision=line.revision,
        profile=line.profile,
        part_count=line.part_count,
    )


def _thread_view(thread: Thread) -> ThreadView:
    return ThreadView(
        id=thread.id, prompt=thread.prompt, status=thread.status, summary=thread.summary
    )


@router.get("")
async def list_lines(
    request: Request, user: User = Depends(current_user)
) -> list[LineView]:
    return [_view(p) for p in await store_of(request).lines_for_user(user.id)]


@router.post("", status_code=201)
async def create_line(
    body: NewLine, request: Request, user: User = Depends(current_user)
) -> LineView:
    return _view(await store_of(request).create_line(user.id, body.name))


@router.get("/{line_id}")
async def get_line(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> LineView:
    line = await store_of(request).line_for_user(line_id, user.id)
    if line is None:
        raise HTTPException(404, "no such line")
    return _view(line)


@router.get("/{line_id}/threads")
async def list_threads(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> list[ThreadView]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.id) is None:
        raise HTTPException(404, "no such line")
    return [_thread_view(t) for t in await store.threads_for_line(line_id, user.id)]


@router.get("/{line_id}/bom")
async def get_bom(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    return await _owned_bom(request, line_id, user.id)


@router.put("/{line_id}/bom")
async def put_bom(
    line_id: str, body: BomPayload, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.id) is None:
        raise HTTPException(404, "no such line")
    await store.save_bom_rows(line_id, user.id, [row.model_dump() for row in body.rows])
    return await store.bom_for_line(line_id, user.id)


async def _owned_bom(request: Request, line_id: str, user_id: str) -> list[dict[str, Any]]:
    store = store_of(request)
    if await store.line_for_user(line_id, user_id) is None:
        raise HTTPException(404, "no such line")
    return await store.bom_for_line(line_id, user_id)


@router.get("/{line_id}/profile")
async def get_profile(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    line = await store_of(request).line_for_user(line_id, user.id)
    if line is None:
        raise HTTPException(404, "no such line")
    return {"profile": line.profile, "revision": line.revision}


@router.put("/{line_id}/profile")
async def put_profile(
    line_id: str, body: ProfilePayload, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.id) is None:
        raise HTTPException(404, "no such line")
    try:
        profile = OperatingProfile.from_json(body.profile)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    await store.save_profile(line_id, user.id, profile, body.revision)
    return {"profile": profile.to_json(), "revision": body.revision}


@router.patch("/{line_id}")
async def rename_line(
    line_id: str, body: NewLine, request: Request, user: User = Depends(current_user)
) -> LineView:
    store = store_of(request)
    if not await store.rename_line(line_id, user.id, body.name):
        raise HTTPException(404, "no such line")
    return _view(await store.line_for_user(line_id, user.id))


@router.delete("/{line_id}", status_code=204)
async def delete_line(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> None:
    if not await store_of(request).delete_line(line_id, user.id):
        raise HTTPException(404, "no such line")
