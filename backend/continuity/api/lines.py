"""Lines — the thing a dashboard lists and a run belongs to.

Every route here takes the signed-in user from `current_user` and passes it into the
query. There is deliberately no "fetch by id, then check the owner" path: ownership is a
`WHERE` clause, so there is no unscoped read available to reach for by mistake.

A miss is 404, never 403. 403 would confirm that a line exists and belongs to somebody
else, which is a fact the caller has no business learning.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from . import replay
from . import review as review_api
from .auth import current_user, store_of
from .store import Line, Thread, User
from ..engine import rules
from ..linegraph import graph_from
from ..parts import normalize
from ..profile import OperatingProfile
from .. import review as review_service

log = logging.getLogger(__name__)

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
    return [_view(p) for p in await store_of(request).lines_for_user(user.org_id, user.id)]


@router.post("", status_code=201)
async def create_line(
    body: NewLine, request: Request, user: User = Depends(current_user)
) -> LineView:
    return _view(await store_of(request).create_line(user.id, user.org_id, body.name))


@router.get("/{line_id}")
async def get_line(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> LineView:
    line = await store_of(request).line_for_user(line_id, user.org_id, user.id)
    if line is None:
        raise HTTPException(404, "no such line")
    return _view(line)


_CHECKED: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_CHECKED_LIMIT = 40
"""Lines already checked, by the content of what was checked.

Four to seven seconds a visit, every visit, because resolving three parts against a
distributor is three network calls and the answer was thrown away each time. The inputs are
the stored bill, the stored profile and the recorded part facts, so the key is a digest of
them: apply a substitution and the bill changes, the digest changes, and the check runs
again.

**One input can change without the key changing**, and it is worth naming: a distributor's
stock. `availability` reads it live, so a cached verdict is as fresh as the moment it was
computed rather than as fresh as the request. For a product line page that paints a part
green or red, minutes-old stock is the right trade against four seconds of waiting on every
click; a change request, which is the document somebody signs, resolves parts again when it
is written and does not read this.
"""


def forget_checks() -> None:
    """Empty the cache. For tests, which must never be served another test's answer.

    Process-global state that survives a request is exactly the kind a suite ends up
    sharing by accident: the first version of this cache made a test that spies on the
    engine being invoked pass on its own and fail after any test that had checked the same
    line, because the second one never reached the engine at all.
    """
    _CHECKED.clear()


def _checked(key: str) -> dict[str, Any] | None:
    found = _CHECKED.get(key)
    if found is not None:
        _CHECKED.move_to_end(key)
    return found


def _remember_check(key: str, result: dict[str, Any]) -> dict[str, Any]:
    _CHECKED[key] = result
    while len(_CHECKED) > _CHECKED_LIMIT:
        _CHECKED.popitem(last=False)
    return result


def _fingerprint(line: Line, rows: Sequence[Mapping[str, Any]]) -> str:
    """What was checked, as one string. Anything that changes a verdict changes this."""
    material = json.dumps(
        {
            "revision": line.revision,
            "profile": line.profile,
            "rows": [
                {k: row.get(k) for k in ("refdes", "mpn", "manufacturer", "populated")}
                for row in rows
            ],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode()).hexdigest()


async def warm_checks(store: Any) -> None:
    """Check every product line once, at startup, so the first visit is not the slow one.

    The graph is green before this finishes — green is the resting state and the page does
    not wait for a verdict to paint it — but the line under it that says how many rules ran
    did wait, and arriving four seconds after the picture reads as the page still thinking.

    Best effort in every direction: one line failing does not stop the others, and the whole
    thing failing does not stop the app. Nothing here is required for correctness; it moves
    work that was going to happen anyway to a moment when nobody is looking at it.
    """
    try:
        organisations = await store.every_organisation()
    except Exception:  # noqa: BLE001
        log.info("could not list organisations to warm checks", exc_info=True)
        return

    async def one(line_id: str, org_id: str) -> None:
        try:
            await _check_line(store, line_id, org_id)
        except Exception:  # noqa: BLE001
            log.info("could not warm the check for %s", line_id, exc_info=True)

    work = []
    for org_id in organisations:
        for line in await store.lines_in_org(org_id):
            work.append(one(line.id, org_id))
    if work:
        await asyncio.gather(*work)
        log.info("warmed %d product line checks", len(work))


async def _check_line(store: Any, line_id: str, org_id: str) -> dict[str, Any]:
    """The engine over one product line, cached on what it looked at."""
    line = await store.line_in_org(line_id, org_id)
    if line is None:
        raise HTTPException(404, "no such line")

    rows = await store.bom_for_line(line_id, org_id)
    key = _fingerprint(line, rows)
    already = _checked(key)
    if already is not None:
        return already

    # The company's own verified readings, in the engine's hands before anything resolves.
    # Without this every SOT-223 part falls back to the package table's single figure and to
    # whatever the distributor's parametric blob says, and the green this endpoint paints
    # would be graded against a listing rather than against the datasheets somebody read.
    # The same omission in the review made NCP1117 clear the Gateway.
    async def facts_for(mpn: str) -> list[dict[str, Any]]:
        return (await store.part_facts([mpn])).get(mpn, [])

    token = normalize.set_dossier_lookup(facts_for)
    try:
        board, why_not, unresolved = await review_api.board_for_line(store, line_id, org_id)
    finally:
        normalize.reset_dossier_lookup(token)
    if board is None:
        raise HTTPException(409, why_not or "this product line cannot be checked")

    waivers = await store.accepted_waivers_for_line(line_id, org_id)
    verdicts = review_service.accepted_verdicts(
        rules.evaluate(board),
        waivers=waivers,
        parts={
            slot_id: slot.part.mpn if slot.part is not None else None
            for slot_id, slot in board.slots.items()
        },
        revision=line.revision,
    )
    per_slot: dict[str, dict[str, Any]] = {}
    for slot_id in board.slots:
        mine = [v for v in verdicts if v.subject == slot_id]
        failed = [v for v in rules.blocking(mine)]
        accepted = [v for v in mine if v.status == "failed" and v.accepted]
        per_slot[slot_id] = {
            "status": "conflict" if failed else "accepted" if accepted else "pass",
            "checked": len(mine),
            "detail": (failed or accepted)[0].detail if failed or accepted else None,
            "accepted": sorted({v.rule for v in accepted}),
        }

    return _remember_check(
        key,
        {
            "slots": per_slot,
            "checked": len(verdicts),
            # Named rather than left grey. A part the distributor could not give us has no
            # verdict, and a slot with no verdict looks exactly like one nobody got to.
            "unresolved": unresolved,
            # Green means nothing failed, not that everything was checkable. Naming the two
            # separately is the whole reason there are five coverage labels rather than three.
            "evidence_missing": sorted(
                {v.rule for v in verdicts if v.status == "evidence_missing"}
            ),
        },
    )


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
    overview promises to render offline and instantly.

    Nothing here is a substitution. It places nothing and proposes nothing: it checks the
    parts the line already has, which is the question "is this product, as it ships, sound
    under the conditions its own profile states".

    The work is in `_check_line`, which the startup warm calls too, so a page and a warm
    cannot come to disagree about what checking a line means.
    """
    return await _check_line(store_of(request), line_id, user.org_id)


@router.get("/{line_id}/reviews")
async def reviews(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    """Every review this product line has been through, with its trace.

    **Reopening a product line shows the working, not just the answer.** A design run is
    replayable because every frame it emitted is stored; a review kept only its conclusions,
    so a line that had been reviewed showed a part number and a date. `api/replay` rebuilds
    the trace out of `decisions.document`, which the run already wrote — nothing new is
    stored and nothing is invented. See that module for the one line it cannot reproduce.

    Separate from `/overview` for the reason `/check` is: the overview promises to render
    instantly, and this is a join and an assembly per decision.
    """
    store = store_of(request)
    line = await store.line_for_user(line_id, user.org_id, user.id)
    if line is None:
        raise HTTPException(404, "no such line")

    decisions = await store.decisions_for_line(line_id, user.org_id)
    notices = {
        notice["id"]: notice
        for notice in await store.notices_for_org(user.org_id)
    }
    out: list[dict[str, Any]] = []
    for decision in decisions:
        notice = notices.get(decision["notice_id"])
        if notice is None:
            # A decision whose notice has been deleted has no trace to tell: the frames
            # open with what is retiring and why, and both come from the notice.
            continue
        out.append(
            {
                "decision_id": decision["id"],
                "notice_id": decision["notice_id"],
                "state": decision["state"],
                "proposal": decision["proposal"],
                "retiring": decision["retiring"],
                "created_at": decision["created_at"].isoformat(),
                "frames": replay.frames_from(notice, decision),
            }
        )
    return out


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
    line = await store.line_for_user(line_id, user.org_id, user.id)
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
    if await store.line_for_user(line_id, user.org_id, user.id) is None:
        raise HTTPException(404, "no such line")
    return [_thread_view(t) for t in await store.threads_for_line(line_id, user.org_id)]


@router.get("/{line_id}/bom")
async def get_bom(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    return await _owned_bom(request, line_id, user)


@router.put("/{line_id}/bom")
async def put_bom(
    line_id: str, body: BomPayload, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.org_id, user.id) is None:
        raise HTTPException(404, "no such line")
    await store.save_bom_rows(line_id, user.id, user.org_id, [row.model_dump() for row in body.rows])
    return await store.bom_for_line(line_id, user.org_id)


async def _owned_bom(request: Request, line_id: str, user: User) -> list[dict[str, Any]]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.org_id, user.id) is None:
        raise HTTPException(404, "no such line")
    return await store.bom_for_line(line_id, user.org_id)


@router.get("/{line_id}/profile")
async def get_profile(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    line = await store_of(request).line_for_user(line_id, user.org_id, user.id)
    if line is None:
        raise HTTPException(404, "no such line")
    return {"profile": line.profile, "revision": line.revision}


@router.put("/{line_id}/profile")
async def put_profile(
    line_id: str, body: ProfilePayload, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    store = store_of(request)
    if await store.line_for_user(line_id, user.org_id, user.id) is None:
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
    # **The access check comes first, because this one writes.** `rename_line` is scoped to
    # the company and would have renamed a project the caller was never brought in on; the
    # check it used to do afterwards only decided whether the *response* was a 404.
    if await store.line_for_user(line_id, user.org_id, user.id) is None:
        raise HTTPException(404, "no such line")
    if not await store.rename_line(line_id, user.org_id, body.name):
        raise HTTPException(404, "no such line")
    return _view(await store.line_for_user(line_id, user.org_id, user.id))


@router.delete("/{line_id}", status_code=204)
async def delete_line(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> None:
    if not await store_of(request).delete_line(line_id, user.org_id):
        raise HTTPException(404, "no such line")
