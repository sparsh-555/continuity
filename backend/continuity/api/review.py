"""Every affected product line, re-checked at once, on one stream.

A notice reaches three of the five products this company ships. A team answers that in
sequence — design proposes, procurement replies, production objects, repeat — and the 48
hours in Scenario B's prompt is where those round trips go. This runs the three boards
**concurrently**, each against every department's rules at the same time, and stops where a
person is genuinely needed.

## One stream, not one per line

Browsers cap around six HTTP/1.1 connections per origin and the client already streams over
`fetch`; three streams plus the page's ordinary calls sit on that limit. Worse, three
sequence spaces race, and the client drops anything at or below its high-water mark — so
three streams would silently discard each other's frames. There is one `EventStream` for the
whole review and every frame carries the line it belongs to.

## The run does not suspend

Nothing here is a checkpointed graph waiting to be resumed. By the time a person is asked,
the evidence is computed and the proposal is chosen; what remains is a signature. That is a
row in `decisions`, so the answer can arrive after a reload, from a different browser, from
somebody who was not watching — which is what a decision belonging to another department
actually looks like.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dataclasses import replace as replace_fields

from .. import review
from ..engine.models import ApprovedLists, PartSpec
from ..profile import OperatingProfile, board_from
from . import events
from .auth import current_user, store_of
from . import matrix as matrix_api
from .matrix import Ambiguous
from .store import User

log = logging.getLogger(__name__)

router = APIRouter(tags=["review"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # nginx and friends will otherwise buffer the whole stream
}


class ReviewRun(BaseModel):
    candidates: list[str] = Field(default_factory=list, max_length=20)
    """Extra parts to try, named by a person. The notice's own recommendation and the
    approved list are found without being asked for."""


def _decision_text(line_name: str, proposal: review.Proposal) -> str:
    """What the person being asked is actually deciding.

    A conditional proposal leads with the fact that the part works, because the desk being
    asked did not watch the run and the question in front of them is whether to qualify a
    part, not whether it fits."""
    if proposal.conditional:
        return (
            f"{proposal.mpn} clears every electrical check on the {line_name}. "
            f"{proposal.detail} Approve it for this product?"
        )
    return f"{proposal.mpn} on the {line_name}. {proposal.detail} Approve the change?"


async def _resolve_quietly(mpn: str, manufacturer: str | None = None) -> PartSpec | None:
    """A part, or nothing. An ambiguity is a reason to skip a candidate, not to fail a run."""
    try:
        # Through the module, never `from .matrix import resolve`: a direct import binds a
        # second reference that a test's monkeypatch cannot reach, and the run would
        # quietly go to the real distributor from an offline suite.
        return await matrix_api.resolve(mpn, manufacturer)
    except Ambiguous as ambiguous:
        log.info("skipping %s: %s", mpn, ambiguous)
        return None


async def _board_for(store: Any, line: dict[str, Any], org_id: str):
    """One product line's board, out of the database, or `None` with the reason logged."""
    stored = await store.line_for_user(line["line_id"], org_id)
    if stored is None or not stored.profile:
        return None, "no operating profile is stored for this product line"
    rows = await store.bom_for_line(line["line_id"], org_id)
    specs: dict[str, PartSpec] = {}
    for row in rows:
        if not row["populated"]:
            continue
        part = await _resolve_quietly(row["mpn"], row.get("manufacturer"))
        if part is not None:
            specs[row["mpn"]] = part
    try:
        profile = OperatingProfile.from_json(stored.profile)
        board = board_from(profile, rows, specs)
    except (KeyError, TypeError, ValueError) as error:
        return None, f"this product line's stored profile could not be read: {error}"
    return board, None


def _slot_of(board, mpn: str) -> str | None:
    for slot_id, slot in board.slots.items():
        if slot.part is not None and slot.part.mpn.casefold() == mpn.casefold():
            return slot_id
    return None


async def _run_line(
    *,
    store: Any,
    user: User,
    notice: dict[str, Any],
    line: dict[str, Any],
    named: list[str],
    approved: ApprovedLists,
    stream: events.EventStream,
    emit,
) -> None:
    """One product line, start to finish, emitting as it goes."""
    line_id, line_name = line["line_id"], line["name"]

    def say(text: str, slot: str | None = None) -> None:
        emit(line_id, stream.reasoning(slot, text))

    board, refusal = await _board_for(store, line, user.org_id)
    if board is None:
        say(f"{line_name}: {refusal}.")
        emit(line_id, stream.line_done(line_name, proposal=None, decision_id=None,
                                       reason=refusal))
        return

    board = replace_fields(board, approved=approved)

    slot_id = _slot_of(board, notice["mpn"])
    if slot_id is None:
        reason = f"{notice['mpn']} is on the bill but could not be sourced, so it was not checked"
        say(f"{line_name}: {reason}.")
        emit(line_id, stream.line_done(line_name, proposal=None, decision_id=None,
                                       reason=reason))
        return

    say(f"{notice['mpn']} sits at {slot_id.upper()} on the {line_name}.", slot_id)

    retiring = board.slots[slot_id].part
    candidates = await review.candidates_for(
        retiring=retiring,
        resolve=_resolve_quietly,
        notice_replacement=notice.get("replacement_mpn"),
        approved=sorted(approved.parts or ()),
        named=named,
    )
    if not candidates:
        reason = "no candidate could be sourced to try"
        say(f"{line_name}: {reason}.", slot_id)
        emit(line_id, stream.line_done(line_name, proposal=None, decision_id=None,
                                       reason=reason))
        return

    rejected = await store.rejected_on(user.org_id, line_id)

    attempts = []
    for candidate in candidates:
        emit(line_id, stream.candidate(slot_id, candidate.part))
        say(f"Trying {candidate.part.mpn} — {candidate.origin}.", slot_id)
        made = review.attempt(board, slot_id, candidate.part)
        attempts.append(made)
        say(review.narrate(made), slot_id)
        # Let the other product lines have the loop between candidates. The engine is fast
        # enough that three boards would otherwise finish in the order they were started
        # rather than the order they actually completed.
        await asyncio.sleep(0)

    proposal = review.choose(attempts, excluded=rejected)
    for verdict in next(
        (a.verdicts for a in attempts if proposal and a.mpn == proposal.mpn), ()
    ):
        emit(line_id, stream.check(verdict))

    if proposal is None:
        reason = "no candidate clears this product line's own operating conditions"
        say(f"{line_name}: {reason}.", slot_id)
        emit(line_id, stream.line_done(line_name, proposal=None, decision_id=None,
                                       reason=reason))
        return

    decision_id = await store.save_decision(
        org_id=user.org_id,
        line_id=line_id,
        notice_id=notice["id"],
        user_id=user.id,
        slot_id=slot_id,
        retiring=notice["mpn"],
        proposal=proposal.mpn,
        gate_rule=proposal.gate_rule,
        roles=proposal.roles,
        detail=proposal.detail,
        document={
            "line_name": line_name,
            "attempts": [
                {
                    "mpn": made.mpn,
                    "manufacturer": made.candidate.manufacturer,
                    "clear": made.clear,
                    "gated": made.gated,
                    "narration": review.narrate(made),
                    "verdicts": [
                        {
                            "rule": verdict.rule,
                            "status": verdict.status,
                            "detail": verdict.detail,
                            "margin": verdict.margin,
                        }
                        for verdict in made.verdicts
                    ],
                }
                for made in attempts
            ],
        },
    )

    emit(
        line_id,
        stream.question(
            question_id=f"decision:{decision_id}",
            text=_decision_text(line_name, proposal),
            suggestions=("Approve and apply", "Leave it"),
            roles=proposal.roles,
        ),
    )
    emit(
        line_id,
        stream.line_done(
            line_name,
            proposal=proposal.mpn,
            decision_id=decision_id,
            reason=proposal.detail,
            conditional=proposal.conditional,
            roles=proposal.roles,
        ),
    )


@router.post("/notices/{notice_id}/review/run")
async def run_review(
    notice_id: str, body: ReviewRun, request: Request, user: User = Depends(current_user)
) -> StreamingResponse:
    """Re-check every product line this notice reaches, at the same time."""
    store = store_of(request)
    notice = await store.notice_for_org(notice_id, user.org_id)
    if notice is None:
        raise HTTPException(404, "no such notice")

    exposed = await store.lines_exposed_to(user.org_id, notice["mpn"])
    if not exposed:
        raise HTTPException(409, "that notice does not reach any product line you ship")

    approved = await store.approved_lists(user.org_id)
    stream = events.EventStream(f"review:{notice_id}")

    async def merged() -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def emit(line_id: str, event: dict[str, Any]) -> None:
            queue.put_nowait({**event, "line_id": line_id})

        async def worker(line: dict[str, Any]) -> None:
            try:
                await _run_line(
                    store=store, user=user, notice=notice, line=line,
                    named=list(body.candidates), approved=approved,
                    stream=stream, emit=emit,
                )
            except Exception as error:  # one line failing must not take the others
                log.exception("review failed for %s", line["line_id"])
                emit(line["line_id"], stream.error(f"{type(error).__name__}: {error}", recoverable=True))
                emit(line["line_id"], stream.line_done(
                    line["name"], proposal=None, decision_id=None,
                    reason="this product line could not be checked",
                ))
            finally:
                queue.put_nowait(None)

        tasks = [asyncio.create_task(worker(line)) for line in exposed]
        remaining = len(tasks)
        try:
            while remaining:
                event = await queue.get()
                if event is None:
                    remaining -= 1
                    continue
                yield event
        finally:
            for task in tasks:
                task.cancel()

    async def framed() -> AsyncIterator[str]:
        yield events.frame(
            stream.review_started(
                notice_id,
                notice["mpn"],
                [{"line_id": line["line_id"], "name": line["name"]} for line in exposed],
            )
        )
        # Heartbeats for the same reason every other stream here has them: sourcing a
        # candidate can hold the connection quiet past the client's thirty-second timer.
        async for event in events.with_heartbeats(merged()):
            if event is None:
                yield events.HEARTBEAT
                continue
            yield events.frame(event)

    return StreamingResponse(framed(), media_type="text/event-stream", headers=SSE_HEADERS)
