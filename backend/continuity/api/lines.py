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

from . import review as review_api
from .auth import current_user, store_of
from .store import Line, Thread, User
from ..engine import rules
from ..linegraph import graph_from
from ..parts import normalize
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
    exposed_count: int = 0


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
        exposed_count=line.exposed_count,
    )


def _thread_view(thread: Thread) -> ThreadView:
    return ThreadView(
        id=thread.id, prompt=thread.prompt, status=thread.status, summary=thread.summary
    )


@router.get("")
async def list_lines(
    request: Request, user: User = Depends(current_user)
) -> list[LineView]:
    return [_view(p) for p in await store_of(request).lines_for_user(user.org_id)]


@router.post("", status_code=201)
async def create_line(
    body: NewLine, request: Request, user: User = Depends(current_user)
) -> LineView:
    return _view(await store_of(request).create_line(user.id, user.org_id, body.name))


@router.get("/{line_id}")
async def get_line(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> LineView:
    line = await store_of(request).line_for_user(line_id, user.org_id)
    if line is None:
        raise HTTPException(404, "no such line")
    return _view(line)


@router.post("/{line_id}/check")
async def check(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Run the engine over a product line as it stands, under its own stored conditions.

    **Why this is its own call.** The graph on a product line used to be entirely grey,
    because every slot came back `unchecked` and that was the truthful answer: no rule had
    looked at the board. The result was a screen saying nothing works about products that
    ship today. Painting it green without running anything would be worse, since an
    unearned verdict is the one thing this system must not produce. So it runs the engine,
    and green means green because it was computed.

    Separate from `/overview` because resolving parts reaches a distributor and the
    overview promises to render offline and instantly. The page loads grey and settles.

    Nothing here is a substitution. It places nothing and proposes nothing: it checks the
    parts the line already has, which is the question "is this product, as it ships, sound
    under the conditions its own profile states".
    """
    store = store_of(request)
    line = await store.line_for_user(line_id, user.org_id)
    if line is None:
        raise HTTPException(404, "no such line")

    # The company's own verified readings, in the engine's hands before anything resolves.
    # Without this every SOT-223 part falls back to the package table's single figure and to
    # whatever the distributor's parametric blob says, and the green this endpoint paints
    # would be graded against a listing rather than against the datasheets somebody read.
    # The same omission in the review made NCP1117 clear the Gateway.
    async def facts_for(mpn: str) -> list[dict[str, Any]]:
        return (await store.part_facts([mpn])).get(mpn, [])

    token = normalize.set_dossier_lookup(facts_for)
    try:
        board, why_not, unresolved = await review_api.board_for_line(store, line_id, user.org_id)
    finally:
        normalize.reset_dossier_lookup(token)
    if board is None:
        raise HTTPException(409, why_not or "this product line cannot be checked")

    verdicts = rules.evaluate(board)
    per_slot: dict[str, dict[str, Any]] = {}
    for slot_id in board.slots:
        mine = [v for v in verdicts if v.subject == slot_id]
        failed = [v for v in rules.blocking(mine)]
        per_slot[slot_id] = {
            "status": "conflict" if failed else "pass",
            "checked": len(mine),
            "detail": failed[0].detail if failed else None,
        }

    return {
        "slots": per_slot,
        "checked": len(verdicts),
        # Named rather than left grey. A part the distributor could not give us has no
        # verdict, and a slot with no verdict looks exactly like one nobody got to.
        "unresolved": unresolved,
        # Green means nothing failed, not that everything was checkable. Naming the two
        # separately is the whole reason there are five coverage labels rather than three.
        "not_assessed": sorted({v.rule for v in verdicts if v.status == "not_assessed"}),
        "evidence_missing": sorted({v.rule for v in verdicts if v.status == "evidence_missing"}),
    }


@router.get("/{line_id}/overview")
async def overview(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Everything a product line is, in one call.

    One request rather than five because this is one page with one loading state, and
    because the five would otherwise be issued from a component each and arrive in an
    order nothing controls. Nothing here reaches a distributor: every field is stored, so
    the page renders offline and instantly.
    """
    store = store_of(request)
    line = await store.line_for_user(line_id, user.org_id)
    if line is None:
        raise HTTPException(404, "no such line")

    parts = await store.bom_for_line(line_id, user.org_id)
    board = await store.board_for(line_id, user.org_id)
    notices = await store.notices_reaching_line(line_id, user.org_id)
    requests = await store.change_requests_for_line(line_id, user.org_id)

    # Every designator a notice has named on this line. The graph paints those in
    # conflict, which is the manufacturer's statement rather than a verdict of ours, and is
    # the only colour that can be painted before a rule has run.
    retired = {designator for notice in notices for designator in notice["refdes"]}

    return {
        "line": _view(line).model_dump(),
        "parts": parts,
        "graph": graph_from(line.profile, parts, retired=retired).to_json(),
        "board": (
            {
                "filename": board["filename"],
                "project": board["project"],
                "bytes": board["bytes"],
                "uploaded_at": board["uploaded_at"].isoformat(),
            }
            if board
            else None
        ),
        "notices": [
            {
                "id": notice["id"],
                "mpn": notice["mpn"],
                "manufacturer": notice["manufacturer"],
                "effective_date": (
                    notice["effective_date"].isoformat() if notice["effective_date"] else None
                ),
                "replacement_mpn": notice["replacement_mpn"],
                "reason": notice["reason"],
                "source": notice["source"],
                "created_at": notice["created_at"].isoformat(),
                "refdes": list(notice["refdes"]),
            }
            for notice in notices
        ],
        "requests": [
            {
                "id": row["id"],
                "notice_id": row["notice_id"],
                "proposal": row["proposal"],
                "created_at": row["created_at"].isoformat(),
                "document": row["document"],
            }
            for row in requests
        ],
    }


@router.get("/{line_id}/threads")
async def list_threads(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> list[ThreadView]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.org_id) is None:
        raise HTTPException(404, "no such line")
    return [_thread_view(t) for t in await store.threads_for_line(line_id, user.org_id)]


@router.get("/{line_id}/bom")
async def get_bom(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    return await _owned_bom(request, line_id, user.org_id)


@router.put("/{line_id}/bom")
async def put_bom(
    line_id: str, body: BomPayload, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.org_id) is None:
        raise HTTPException(404, "no such line")
    await store.save_bom_rows(line_id, user.id, user.org_id, [row.model_dump() for row in body.rows])
    return await store.bom_for_line(line_id, user.org_id)


async def _owned_bom(request: Request, line_id: str, org_id: str) -> list[dict[str, Any]]:
    store = store_of(request)
    if await store.line_for_user(line_id, org_id) is None:
        raise HTTPException(404, "no such line")
    return await store.bom_for_line(line_id, org_id)


@router.get("/{line_id}/profile")
async def get_profile(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    line = await store_of(request).line_for_user(line_id, user.org_id)
    if line is None:
        raise HTTPException(404, "no such line")
    return {"profile": line.profile, "revision": line.revision}


@router.put("/{line_id}/profile")
async def put_profile(
    line_id: str, body: ProfilePayload, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.org_id) is None:
        raise HTTPException(404, "no such line")
    try:
        profile = OperatingProfile.from_json(body.profile)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    await store.save_profile(line_id, user.org_id, profile, body.revision)
    return {"profile": profile.to_json(), "revision": body.revision}


@router.patch("/{line_id}")
async def rename_line(
    line_id: str, body: NewLine, request: Request, user: User = Depends(current_user)
) -> LineView:
    store = store_of(request)
    if not await store.rename_line(line_id, user.org_id, body.name):
        raise HTTPException(404, "no such line")
    return _view(await store.line_for_user(line_id, user.org_id))


@router.delete("/{line_id}", status_code=204)
async def delete_line(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> None:
    if not await store_of(request).delete_line(line_id, user.org_id):
        raise HTTPException(404, "no such line")
