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
from pydantic import BaseModel, ConfigDict, Field

from .auth import current_user, store_of
# Through the module, not `from ... import resolve`: a direct import binds a second
# reference, so anything that swaps the real one — a test, or a future cache in front
# of it — silently would not reach this caller.
from . import matrix as matrix_api
from . import replay
from .review import decision_text
from .store import User
from .. import change, mail, notices as reader
from ..engine import situation
from ..engine.models import PartSpec
from ..parts import categories
from ..matrix import evaluate_matrix
from ..parts import normalize
from ..profile import OperatingProfile, board_from
# By name, not `review.Proposal`: this module defines a route handler called `review`, and
# that rebinds the module-level name at import time — the same shadowing that silently broke
# every change request when `change.py` gained a second `_headline`.
from ..review import Proposal

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notices", tags=["notices"])

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


class NoticeRequest(BaseModel):
    document: str = Field(max_length=((MAX_DOCUMENT_BYTES + 2) // 3) * 4)
    """The notice itself, base64. A PDF or plain text — mail carries both, and refusing the
    second would fail on a real message for a reason unrelated to the notice."""

    filename: str | None = Field(default=None, max_length=200)
    """What the document was called, when the sender knows.

    Recorded as the notice's source so that "where did this come from" has an answer a
    person recognises. It used to be stored as the literal string `api`, which is true and
    tells a reader nothing: memory showed a retired part cited to `api`.
    """


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

    notice_id = await store.save_notice(
        user.org_id, user.id, notice, source=body.filename or "uploaded"
    )
    exposed = await store.lines_exposed_to(user.org_id, notice.mpn, user.id)

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
    # **Somebody has the application open, and that is the whole signal.** The browser asks
    # this from every authenticated screen, not only the one a review runs on, so this is
    # what lets the mailbox be polled every fifteen seconds for the minutes somebody is
    # waiting on a notice and at Google's documented ten minutes the rest of the day. See
    # `mail.POLL_IDLE_SECONDS` — polling at the fast rate around the clock is what closed
    # the account twice on 11 September.
    mail.note_someone_is_watching()
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
    model_config = ConfigDict(extra="forbid")

    candidates: list[str] = Field(min_length=1, max_length=10)
    """The substitutes to try. The notice's own recommendation belongs in here — it is a
    candidate like any other, and the demo's whole point is that it does not survive
    everywhere."""

    slot: str | None = Field(default=None, max_length=100)
    """Which position on the board. Defaults to wherever each line carries the retired part,
    which is what a notice actually means."""

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

    exposed = await store.lines_exposed_to(user.org_id, notice["mpn"], user.id)
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
        line = await store.line_for_user(row["line_id"], user.org_id, user.id)
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

    # A part on a bill of materials carries the manufacturer it was bought as, so an MPN
    # several vendors publish is not ambiguous *here* — the board already chose. A candidate
    # somebody names has the same answer wherever this company has already recorded one: the
    # approved manufacturer list says whose part quality qualified, which is why
    # `TLV1117LV33DCYR` used to come back as *two companies list this* and be skipped rather
    # than checked. These boards' own bills go on top, because they are the most specific
    # record there is.
    fitted: dict[str, str | None] = dict(await store.recorded_manufacturers(user.org_id))
    for bom in boms.values():
        for row in bom:
            if row.get("populated", True) and row.get("manufacturer"):
                fitted[row["mpn"].upper()] = row["manufacturer"]
    wanted = {row["mpn"] for bom in boms.values() for row in bom if row.get("populated", True)}
    wanted |= set(body.candidates) | {notice["mpn"]}

    ordered = sorted(wanted)
    outcomes = await asyncio.gather(
        *(matrix_api.resolve(mpn, fitted.get(mpn.upper())) for mpn in ordered),
        return_exceptions=True,
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
        per_line[line.id] = {
            "revision": line.revision,
            "slot": slot,
            "annual_volume": profile.annual_volume,
        }

    if not boards:
        raise HTTPException(409, "no affected line could be assembled into a board")

    # **Every board keeps its own position.** The slot was already looked up per line from
    # that line's own bill; what refused was the grid, which could only name one. Real
    # boards disagree far more often than they agree — U3, U1 and U2 on the demo's own
    # three — and a caller who names one explicitly still gets it applied to all of them,
    # because then they have said which they mean.
    slots = {line_id: entry["slot"] for line_id, entry in per_line.items()}
    matrix = evaluate_matrix(
        boards, candidates, body.slot if body.slot else slots
    )

    # What this company already knows, before proposing anything. A rejection is scoped to
    # the board it happened on: a part that cooked the gateway says nothing about the
    # sensor node, and a rejection that spread everywhere would remove candidates nobody
    # had ever checked there.
    ruled_out = {
        line_id: await store.rejected_on(user.org_id, line_id) for line_id in per_line
    }
    await _remember(store, user.org_id, matrix, ruled_out)
    requests = change.for_every_line(
        matrix,
        notice_mpn=notice["mpn"],
        notice_id=notice["id"],
        lines={
            key: {"revision": value["revision"], "annual_volume": value["annual_volume"]}
            for key, value in per_line.items()
        },
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


@router.get("/{notice_id}/reviews")
async def reviews(
    notice_id: str, request: Request, user: User = Depends(current_user)
) -> list[dict[str, Any]]:
    """Every decision this notice produced, with the trace that reached it.

    **A review used to be lost the moment you left the page.** Lane state was component
    state, so navigating away abandoned the stream and coming back showed the stored change
    requests where the run had been.

    **A run now replays in the order it spoke.** The frames are the ones the run streamed,
    recorded as it streamed them, so three boards arrive advancing together rather than one
    after another. The read-back used to rebuild each lane from its own decision — which is
    per product line — and that is why a replay of a company-wide review played like three
    separate reviews. A notice that ran before the trace was recorded has no stored order and
    falls back to that reconstruction, one lane at a time, which is what it had.

    **A pending decision carries its question.** The run asked it with `_decision_text`, and
    the recorded trace holds the very frame it asked with. For a stored trace that has none —
    a run abandoned before it got there — it is rebuilt by that same function from the stored
    proposal, detail and gate rule, so a replay re-raises the identical sentence rather than a
    second phrasing of it. A decision that is no longer pending has its question dropped: the
    question is live only while the answer is.

    **Who has signed so far travels with it.** A decision three desks have signed and one has
    not is not the same screen as one nobody has looked at, and the replay has to say so.
    """
    store = store_of(request)
    notice = await store.notice_for_org(notice_id, user.org_id)
    if notice is None:
        raise HTTPException(404, "no such notice")

    recorded: list[dict[str, Any]] = notice.get("review_trace") or []
    out: list[dict[str, Any]] = []
    for position, decision in enumerate(
        await store.decisions_for_notice(notice_id, user.org_id)
    ):
        # **The run's own order, where it was recorded.** The lines that open the run name no
        # board — what is retiring, what the notice recommends — and they are carried on the
        # first row, which is where the client reads them from. Every other frame goes to the
        # board it is about, keeping its `seq`, so a client that sorts by `seq` restores the
        # interleaving exactly as it happened.
        frames = (
            [
                frame
                for frame in recorded
                if frame.get("line_id") == decision["line_id"]
                or (position == 0 and not frame.get("line_id"))
            ]
            if recorded
            else replay.frames_from(notice, decision)
        )
        required = list(decision.get("roles") or ())
        # A signature records the roles the signer held, which can be more than one, and
        # only the ones this decision actually needs count towards it.
        signed = sorted(
            {
                role
                for approval in await store.approvals_for_decision(decision["id"], user.org_id)
                for role in (approval["roles"] or ())
                if role in required
            }
        )
        pending = decision["state"] == "pending"
        # **A question that has been answered is not re-asked.** The recorded trace carries
        # the frame the run asked with, and it stays in the trace after somebody signs — so a
        # replay would offer a signature for a change that is already settled. The question is
        # live only while the answer is, which is the rule the whole screen follows.
        frames = [
            frame
            for frame in frames
            if frame.get("type") != "question" or pending
        ]
        if pending and not any(frame.get("type") == "question" for frame in frames):
            # No recorded question — a run abandoned before it asked, or a decision written
            # before the trace was recorded. Built by the same function the run used, from
            # the same three stored fields.
            question = decision_text(
                decision.get("line_name") or "this product line",
                Proposal(
                    mpn=decision["proposal"] or "",
                    roles=tuple(required),
                    detail=decision.get("detail") or "",
                    gate_rule=decision.get("gate_rule"),
                ),
            )
            asked = {
                "type": "question",
                # A question is addressed to a board's change, so it belongs to that lane.
                "line_id": decision["line_id"],
                "question_id": f"decision:{decision['id']}",
                "text": question,
                "suggestions": ["Approve and apply", "Leave it"],
                "roles": required,
            }
            # **Before the ending, because that is the order the run spoke them in.**
            # `_run_line` asks the question and then closes the line, and a replay that put
            # them the other way round would be a trace nobody ever saw.
            end = len(frames) - 1 if frames and frames[-1]["type"] == "line_done" else len(frames)
            frames = [*frames[:end], asked, *frames[end:]]
        out.append(
            {
                "decision_id": decision["id"],
                "line_id": decision["line_id"],
                "line_name": decision.get("line_name"),
                "state": decision["state"],
                "proposal": decision["proposal"],
                "gate_rule": decision.get("gate_rule"),
                "roles": required,
                "signed": signed,
                "outstanding": [role for role in required if role not in signed] if pending else [],
                "frames": frames,
            }
        )
    return out


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


def _signature_for(cell) -> str | None:
    """The shape of what went wrong in this cell, for a precedent to be keyed on.

    The cell's own position, not one passed in: a grid spanning boards that carry the part
    at different designators has no single one, and each cell already knows its own.
    """
    failures = cell.failures
    if not failures:
        return None
    part = cell.candidate
    return situation.signature(
        failures[0],
        _board_of(cell),
        category=categories.canonical(part.category),
    )


def _board_of(cell):
    """`situation.signature` reads the conflicting slot's part off a board."""
    from ..engine.models import Board, Slot

    return Board(
        requirements=None,
        slots={cell.slot: Slot(cell.slot, cell.slot, "power", part=cell.candidate)},
        rails={},
    )


async def _remember(store, org_id: str, matrix, ruled_out) -> None:
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
            signature = _signature_for(cell)
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
