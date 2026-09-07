"""A change notice arrives, and Continuity says which products it reaches.

The opening beat of the enterprise flow, and the one place the two halves built so far meet:
`notices.read` turns a document into a part number backed by the line it was read from, and
`store.lines_exposed_to` turns that part number into the products carrying it — a b-tree
probe against every BOM the company owns, which is why item 10b made the bill of materials a
table rather than a column.

## Why a POST and not only a mailbox

A demo that depends on mail delivery depends on somebody else's queue. This endpoint takes
the identical document and produces the identical result, so the mailbox is a convenience
rather than a single point of failure on stage. It is also how the notice gets *in* during
development, where nobody is sending PCNs to a test account.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import current_user, store_of
# Through the module, not `from ... import resolve`: a direct import binds a second
# reference, so anything that swaps the real one — a test, or a future cache in front
# of it — silently would not reach this caller.
from . import matrix as matrix_api
from .store import User
from .. import change, notices as reader
from ..engine import situation
from ..engine.models import PartSpec
from ..parts import categories
from ..matrix import evaluate_matrix
from ..parts import normalize
from ..profile import OperatingProfile, board_from

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notices", tags=["notices"])

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


class NoticeRequest(BaseModel):
    document: str = Field(max_length=((MAX_DOCUMENT_BYTES + 2) // 3) * 4)
    """The notice itself, base64. A PDF or plain text — mail carries both, and refusing the
    second would fail on a real message for a reason unrelated to the notice."""


@router.post("", status_code=201)
async def receive(
    body: NoticeRequest, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    store = store_of(request)

    try:
        document = base64.b64decode(body.document, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "the document is not valid base64") from None
    if not document:
        raise HTTPException(422, "the document is empty")

    notice = await reader.read(document)
    if notice is None:
        # A refusal rather than a guess. Everything downstream keys off the part number, so
        # a notice whose MPN could not be sourced from its own text would start a review of
        # whatever the model happened to say.
        raise HTTPException(
            422,
            "Nothing in this document could be read as a change notice — no part number "
            "backed by a line of the document itself.",
        )

    notice_id = await store.save_notice(user.org_id, user.id, notice, source="api")
    exposed = await store.lines_exposed_to(user.org_id, notice.mpn)

    return {
        "id": notice_id,
        "notice": notice.to_json(),
        # The lines this actually reaches, which is the question a notice raises and never
        # answers. Empty is a real and useful result: the part is not in anything we ship.
        "affected": [
            {
                "line_id": row["line_id"],
                "name": row["name"],
                "revision": row["revision"],
                "refdes": list(row["refdes"]),
            }
            for row in exposed
        ],
    }


@router.get("")
async def list_notices(
    request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    rows = await store_of(request).notices_for_org(user.org_id)
    return [
        {
            **{k: v for k, v in row.items() if k not in {"created_at", "effective_date"}},
            "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


class ReviewRequest(BaseModel):
    candidates: list[str] = Field(min_length=1, max_length=10)
    """The substitutes to try. The notice's own recommendation belongs in here — it is a
    candidate like any other, and the demo's whole point is that it does not survive
    everywhere."""

    slot: str | None = Field(default=None, max_length=100)
    """Which position on the board. Defaults to wherever each line carries the retired part,
    which is what a notice actually means."""

    annual_volume: int | None = Field(default=None, ge=0)


@router.post("/{notice_id}/review", status_code=201)
async def review(
    notice_id: str,
    body: ReviewRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Turn a notice into one change request per affected product line.

    The whole flow in one call, because every step is already built and none of it needs a
    person in the middle: exposure finds the lines, the matrix checks every candidate
    against each line's own stored conditions, and the request is that work written down —
    including, per line, what was *not* assessed.
    """
    store = store_of(request)

    notice = await store.notice_for_org(notice_id, user.org_id)
    if notice is None:
        raise HTTPException(404, "no such notice")

    exposed = await store.lines_exposed_to(user.org_id, notice["mpn"])
    if not exposed:
        raise HTTPException(
            409,
            f"{notice['mpn']} is not on any product line you ship, so there is nothing to "
            "review.",
        )

    approved = await store.approved_lists(user.org_id)
    lookup_token = normalize.set_dossier_lookup(
        lambda mpn: _facts_for(store, mpn)
    )
    try:
        return await _review(
            store, user, notice, exposed, body, approved
        )
    finally:
        normalize.reset_dossier_lookup(lookup_token)


async def _review(store, user, notice, exposed, body, approved) -> dict[str, Any]:
    from dataclasses import replace as _replace

    lines = {}
    boms = {}
    for row in exposed:
        line = await store.line_for_user(row["line_id"], user.org_id)
        if line is None or not line.profile:
            continue
        lines[line.id] = line
        boms[line.id] = await store.bom_for_line(line.id, user.org_id)

    if not lines:
        raise HTTPException(
            409,
            "None of the affected product lines has an operating profile, so there are no "
            "conditions to check a substitution against.",
        )

    wanted = {r["mpn"] for bom in boms.values() for r in bom if r.get("populated", True)}
    wanted |= set(body.candidates) | {notice["mpn"]}

    ordered = sorted(wanted)
    outcomes = await asyncio.gather(
        *(matrix_api.resolve(mpn) for mpn in ordered), return_exceptions=True
    )
    specs: dict[str, PartSpec] = {}
    ambiguous: dict[str, str] = {}
    for mpn, outcome in zip(ordered, outcomes):
        if isinstance(outcome, matrix_api.Ambiguous):
            ambiguous[mpn] = str(outcome)
        elif isinstance(outcome, BaseException):
            raise outcome
        elif outcome is not None:
            specs[mpn] = outcome

    # The retired part is a column too: the row that says what each board does today is the
    # baseline every other cell is measured against, and a matrix without it can report a
    # difference without saying what from.
    candidates = [specs[mpn] for mpn in [notice["mpn"], *body.candidates] if mpn in specs]
    if not candidates:
        raise HTTPException(422, "none of those candidates could be sourced")

    boards, per_line = [], {}
    for line_id, line in lines.items():
        slot = body.slot or next(
            (r["refdes"] for r in boms[line_id] if r["mpn"] == notice["mpn"]), None
        )
        if slot is None:
            continue
        profile = OperatingProfile.from_json(line.profile)
        board = _replace(board_from(profile, boms[line_id], specs), approved=approved)
        if slot not in board.slots:
            continue
        boards.append((line.id, line.name, board))
        per_line[line.id] = {"revision": line.revision, "slot": slot}

    if not boards:
        raise HTTPException(409, "no affected line could be assembled into a board")

    slots = {entry["slot"] for entry in per_line.values()}
    if len(slots) > 1:
        raise HTTPException(
            409,
            f"the retired part sits at different positions across these lines ({', '.join(sorted(slots))}); "
            "name one with `slot`",
        )

    slot_id = slots.pop()
    matrix = evaluate_matrix(boards, candidates, slot_id)

    # What this company already knows, before proposing anything. A rejection is scoped to
    # the board it happened on: a part that cooked the gateway says nothing about the
    # sensor node, and a rejection that spread everywhere would remove candidates nobody
    # had ever checked there.
    ruled_out = {
        line_id: await store.rejected_on(user.org_id, line_id) for line_id in per_line
    }
    await _remember(store, user.org_id, matrix, slot_id, ruled_out)
    requests = change.for_every_line(
        matrix,
        notice_mpn=notice["mpn"],
        notice_id=notice["id"],
        lines={k: {"revision": v["revision"]} for k, v in per_line.items()},
        annual_volume=body.annual_volume,
        approved_mpns=sorted(approved.parts or ()),
        # The manufacturer's own recommendation is tried first, so a request that departs
        # from it has visibly departed from it rather than never considered it.
        prefer=[notice["replacement_mpn"]] if notice["replacement_mpn"] else [],
        # Never re-propose what this board already ruled out. The candidate still appears
        # among the alternatives carrying the reason it was rejected, because a document
        # that silently dropped it would look like it had never been considered.
        excluded={line_id: dict(entries) for line_id, entries in ruled_out.items()},
    )

    ids = await store.save_change_requests(user.org_id, user.id, notice["id"], requests)
    return {
        "notice_id": notice["id"],
        "unresolved": sorted(m for m in body.candidates if m not in specs and m not in ambiguous),
        "ambiguous": ambiguous,
        "requests": [
            {"id": request_id, **request.to_json()}
            for request_id, request in zip(ids, requests)
        ],
    }


@router.get("/{notice_id}/review")
async def list_requests(
    notice_id: str, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    rows = await store_of(request).change_requests_for_org(user.org_id, notice_id=notice_id)
    return [
        {"id": row["id"], "created_at": row["created_at"].isoformat(), **row["document"]}
        for row in rows
    ]


async def _facts_for(store: Any, mpn: str) -> list[dict[str, Any]]:
    return (await store.part_facts([mpn])).get(mpn, [])


def _signature_for(cell, slot_id: str) -> str | None:
    """The shape of what went wrong in this cell, for a precedent to be keyed on."""
    failures = cell.failures
    if not failures:
        return None
    part = cell.candidate
    return situation.signature(
        failures[0],
        _board_of(cell, slot_id),
        category=categories.canonical(part.category),
    )


def _board_of(cell, slot_id: str):
    """`situation.signature` reads the conflicting slot's part off a board."""
    from ..engine.models import Board, Slot

    return Board(
        requirements=None,
        slots={slot_id: Slot(slot_id, slot_id, "power", part=cell.candidate)},
        rails={},
    )


async def _remember(store, org_id: str, matrix, slot_id: str, ruled_out) -> None:
    """Record what this review learned, both ways.

    Rejections matter as much as successes and are the half that was missing: without them
    a candidate ruled out on Monday is proposed again on Tuesday, and the person reading
    the second request has to remember the first.
    """
    for line_id in matrix.lines:
        entries = []
        for cell in matrix.cells:
            if cell.line_id != line_id or cell.is_incumbent:
                continue
            signature = _signature_for(cell, slot_id)
            if cell.ok:
                # A success is keyed on the shape of the problem it solved, which a passing
                # cell does not have — so it is recorded against the incumbent's conflict
                # only when the review actually chose it. Nothing to key on, nothing stored.
                continue
            if signature is None:
                continue
            entries.append(
                {
                    "signature": signature,
                    "mpn": cell.candidate.mpn,
                    "outcome": "rejected",
                    "detail": cell.failures[0].detail,
                }
            )
        try:
            await store.record_precedents(org_id, line_id, entries)
        except Exception:
            # Memory is a convenience. Losing it must never cost the review that produced it.
            log.warning("could not record precedents for %s", line_id, exc_info=True)
