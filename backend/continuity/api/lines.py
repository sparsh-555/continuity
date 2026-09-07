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
from pydantic import BaseModel, Field

from .auth import current_user, store_of
from .store import Line, Thread, User

router = APIRouter(prefix="/lines", tags=["lines"])


class NewLine(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class LineView(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str


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
