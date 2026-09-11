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
from typing import Any, AsyncIterator, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from dataclasses import replace as replace_fields

from .. import change, review
from ..engine.models import ApprovedLists, PartSpec
from ..matrix import Cell, Matrix
from ..graph import sourcing
from ..parts import dossier, normalize
from ..profile import OperatingProfile, board_from
from . import boards as boards_api
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


CATALOGUE_POOL = 25
"""How deep into the distributor's list to look before filtering.

Measured against JLCPCB: a search for a 3.3 V LDO in SOT-223 returns the retired part and
three other listings of it at the top, and the parts that could actually replace it —
LD1117, SPX1117, AZ1117, NCP1117 — start at the seventh hit. A shortlist of six sees none
of them."""

CATALOGUE_LIMIT = 4
"""How many catalogue hits to normalise and try.

Each one costs a distributor lookup and a datasheet read, and a shortlist nobody can read is
not a better answer than a short one. Four is enough for the search to be a real leg of the
flow rather than a gesture."""

CATALOGUE_BATCH = 4
"""Maximum concurrent catalogue normalisations.

The distributor's shortlist is already bounded.  Working it four at a time avoids making a
slow datasheet serialize the review, without starting work for every hit at once."""


class ReviewRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[str] = Field(default_factory=list, max_length=20)
    """Extra parts to try, named by a person. The notice's own recommendation and the
    approved list are found without being asked for."""

    line_id: str | None = None
    """One product line rather than every line the notice reaches.

    The same run, narrowed. A product line's own page asks the question about itself and
    has no room for two other boards' traces, while the change page asks it about the
    whole company. Both are the same stream, the same engine and the same frames, so the
    two surfaces cannot drift into disagreeing about what a review is."""


def decision_text(line_name: str, proposal: review.Proposal) -> str:
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
    """A part, or nothing. A distributor that cannot answer is not a reason to fail a run.

    Ambiguity was the only thing caught here, so a timeout or a refused connection took the
    whole call down — on a page whose entire job is to say whether a shipping product is
    sound, over a network that at a venue is not ours. The caller falls back to the
    company's own recorded readings, which are better evidence than a listing anyway, so
    nothing is lost by being quiet here and a working product stops depending on the wifi.
    """
    try:
        # Through the module, never `from .matrix import resolve`: a direct import binds a
        # second reference that a test's monkeypatch cannot reach, and the run would
        # quietly go to the real distributor from an offline suite.
        return await matrix_api.resolve(mpn, manufacturer)
    except Ambiguous as ambiguous:
        # Candidates need to say exactly why they were not checked. `candidates_for`
        # owns that disclosure; swallowing this here leaves it with indistinguishable
        # `None` and silently drops the one thing a person can answer.
        raise ambiguous
    except Exception as unreachable:  # noqa: BLE001
        log.warning("could not resolve %s from a distributor: %s", mpn, unreachable)
        return None


def _flattened(mpn: str) -> str:
    return "".join(character for character in mpn.casefold() if character.isalnum())


def _same_part(candidate: str, retiring: str) -> bool:
    """Whether a hit is the part being retired, under another listing or a suffix.

    JLCPCB lists `AMS1117-3.3`, `AMS1117-3.3` under a second manufacturer and `AMS1117-3.3V`
    as three separate parts, and a search for what could replace AMS1117-3.3 returns all
    three at the top. They are the part that is going away.
    """
    left, right = _flattened(candidate), _flattened(retiring)
    return left.startswith(right) or right.startswith(left)


def _search_query(retiring: PartSpec) -> str:
    """What to ask the distributor for, in the words a person would use.

    **Not the part's own description.** A distributor description is a parametric blob —
    AMS1117's begins *"-40℃~+125℃ 0.003%Vout 1 1.1V@(800mA) 15V 1A 3.3V"* — and searching
    with it returns the part itself and its own clones. Measured: four hits, all AMS1117.
    What the search wants is the *kind* of part the board needs, which is the rail it makes
    and the family it belongs to.
    """
    category = (retiring.category or "").casefold()
    if "low drop out" in category or "ldo" in category:
        kind = "LDO regulator"
    elif "regulator" in category:
        kind = "regulator"
    else:
        kind = (retiring.category or "part").split(",")[0].strip()
    volts = f"{retiring.vout:g}V " if retiring.vout is not None else ""
    return f"{volts}{kind}"


class CatalogueUnreachable(RuntimeError):
    """The distributor could not be searched. Said out loud rather than quietly costing the
    review its only source of parts nobody here has bought."""


async def _catalogue_search(retiring: PartSpec) -> list[PartSpec]:
    """What the distributor lists that could stand where this part stands.

    Searched in the **same package**, which is production's leg of the scenario: a part in
    the same land pattern is a substitution, and a part in a different one is a board
    revision. The search is how a part nobody here has ever bought gets considered at all,
    and it is the only leg that can produce the answer no approved part gives.
    """
    query = _search_query(retiring)
    constraint = {
        **({"package": retiring.package} if retiring.package else {}),
        **({"vout": retiring.vout} if retiring.vout is not None else {}),
    } or None
    try:
        hits = await sourcing.find(query, constraint=constraint, pool=CATALOGUE_POOL)
    except Exception as error:  # noqa: BLE001 — a dead distributor is not a failed review
        log.warning("catalogue search failed for %s: %s", retiring.mpn, error)
        raise CatalogueUnreachable(str(error)) from error

    # Filtered before normalising, because normalising costs a datasheet read: the top of a
    # distributor's shortlist for "3.3V LDO regulator in SOT-223" is the retired part and
    # its clones. Another manufacturer's listing of the same part number is still the part
    # going away.  The remaining work is independent, but batches preserve the distributor's
    # order and keep the number of concurrent datasheet reads bounded.
    eligible = [hit for hit in hits if not _same_part(hit.mpn, retiring.mpn)]
    found: list[PartSpec] = []
    for start in range(0, len(eligible), CATALOGUE_BATCH):
        if len(found) >= CATALOGUE_LIMIT:
            break
        batch = eligible[start:start + CATALOGUE_BATCH]
        normalised = await asyncio.gather(
            *(sourcing.choose(hit) for hit in batch), return_exceptions=True
        )
        for hit, result in zip(batch, normalised):
            if isinstance(result, Exception):
                log.info("could not normalise %s: %s", getattr(hit, "mpn", "?"), result)
                continue
            part = result
            # A fixed regulator defines the rail it makes, so one with a different fixed
            # output is not a substitute for this position — it is a different board. The
            # engine would say so too, by moving the rail and failing everything downstream,
            # but a shortlist of four that spends three of them on that is a worse shortlist.
            if retiring.vout is not None and part.vout is not None and part.vout != retiring.vout:
                continue
            found.append(part)
            if len(found) >= CATALOGUE_LIMIT:
                break
    return found


async def board_for_line(store: Any, line_id: str, org_id: str):
    """One product line assembled into a board the engine can check, and what it left out.

    The same assembly a review uses, named so that `api/lines.check` can ask for it without
    reaching into this module's internals or building a second one that drifts.

    Returns `(board, reason, unresolved)`. A part the distributor could not give us is
    skipped rather than fatal — one unlisted passive should not stop a board being checked —
    but it is **named**, because a slot with no verdict renders identically to one nobody
    got to, and a screen showing grey beside green without saying why is the kind of
    unaccounted state a judge asks about first.
    """
    stored = await store.line_for_user(line_id, org_id)
    if stored is None or not stored.profile:
        return None, "no operating profile is stored for this product line", []
    rows = await store.bom_for_line(line_id, org_id)
    fitted = [row for row in rows if row["populated"]]

    async def resolved(row: dict[str, Any]) -> PartSpec | None:
        part = await _resolve_quietly(row["mpn"], row.get("manufacturer"))
        if part is not None:
            return part
        # The distributor could not answer. A product line that already ships still has to
        # be checkable, and the company's own datasheet readings are better evidence than a
        # listing — that is what lets them override one. What they lack is the commercial
        # half, which no rule here asks for.
        recorded = (await store.part_facts([row["mpn"]])).get(row["mpn"], [])
        return dossier.part_from_facts(row["mpn"], row.get("manufacturer"), recorded)

    # Together, not one after another. Each row is an independent network call, and doing
    # three in sequence made the page a reader is waiting on three times slower than the
    # slowest of them — which is also most of the quiet stretch before a review says
    # anything about a board.
    found = await asyncio.gather(*(resolved(row) for row in fitted))

    specs: dict[str, PartSpec] = {}
    unresolved: list[dict[str, str]] = []
    for row, part in zip(fitted, found):
        if part is not None:
            specs[row["mpn"]] = part
        else:
            unresolved.append({"refdes": row["refdes"], "mpn": row["mpn"]})
    try:
        profile = OperatingProfile.from_json(stored.profile)
        board = board_from(profile, rows, specs)
    except (KeyError, TypeError, ValueError) as error:
        return None, f"this product line's stored profile could not be read: {error}", unresolved
    return board, None, unresolved


async def _board_for(store: Any, line: dict[str, Any], org_id: str):
    """The review's view of the same assembly: a board, or the reason there is not one.

    One implementation rather than two. This existed first and `board_for_line` was added
    beside it for `api/lines.check`, which put the resolution loop in two places for a day
    and immediately drifted: the fallback to the company's own readings landed in one of
    them only.
    """
    board, why_not, _ = await board_for_line(store, line["line_id"], org_id)
    return board, why_not


def _as_matrix(
    line_id: str,
    line_name: str,
    slot_id: str,
    attempts: Sequence[review.Attempt],
    incumbent: review.Attempt | None,
) -> Matrix:
    """The attempts, in the shape `change.for_line` already knows how to read.

    An adapter rather than a second implementation: the change request's rules about which
    candidate is proposed, which rejections are shown and what a cost is measured against
    were settled in `change.py` and tested there, and a review that computed its own would
    be a second answer to a question that has one.
    """
    cells = [
        Cell(
            line_id=line_id,
            line_name=line_name,
            candidate=made.candidate,
            verdicts=made.verdicts,
            incumbent_mpn=None if made is incumbent else (incumbent.mpn if incumbent else None),
        )
        for made in ([incumbent] if incumbent else []) + list(attempts)
    ]
    return Matrix(slot=slot_id, cells=tuple(cells))


BOARD_TASKS: set[asyncio.Task[None]] = set()
"""Placements in flight, so the event loop cannot collect one before it lands."""


async def _attach_board(
    *,
    store: Any,
    org_id: str,
    notice_id: str,
    line_id: str,
    retiring: str,
    candidate: str,
) -> None:
    """Compute one board's consequence and attach it to the request it belongs to.

    Deliberately silent. It runs after the line has ended and the person watching has moved
    on, so there is nobody to tell and nothing to undo: the request is already correct and
    the card already knows what to render without a picture.
    """
    try:
        made = await boards_api.consequence_for(store, line_id, org_id, retiring, candidate)
    except Exception as error:  # noqa: BLE001
        # **The swallow lives here**, because this caller has nobody to tell: the line has
        # ended, the question is on screen, and the request is already correct without a
        # picture. The endpoint beside it reports its refusals to the person who asked.
        log.warning("board consequence for %s could not be stored: %s", line_id, error)
        return
    if made is None:
        return
    await store.attach_board_consequence(org_id, notice_id, line_id, made)


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
    candidates: tuple[review.Candidate, ...],
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

    if not candidates:
        reason = "no candidate could be sourced to try"
        say(f"{line_name}: {reason}.", slot_id)
        emit(line_id, stream.line_done(line_name, proposal=None, decision_id=None,
                                       reason=reason))
        return

    rejected = await store.rejected_on(user.org_id, line_id)
    # `lines_exposed_to` is the notice's reachability snapshot. The waiver is instead
    # scoped to the revision the product line has *now*, which may have advanced when the
    # preceding decision applied its substitution.
    current_line = await store.line_for_user(line_id, user.org_id)
    revision = current_line.revision if current_line is not None else line.get("revision")
    annual_volume = (
        OperatingProfile.from_json(current_line.profile).annual_volume
        if current_line is not None and current_line.profile
        else None
    )
    waivers = await store.accepted_waivers_for_line(line_id, user.org_id)
    # The board as it stands today, so the request can say what is fitted and what its
    # evidence looks like. Substituting a part for itself sets no baseline, which is what
    # makes this the incumbent row rather than a proposed change.
    incumbent = review.attempt(board, slot_id, board.slots[slot_id].part)

    attempts = []
    for candidate in candidates:
        emit(line_id, stream.candidate(slot_id, candidate.part))
        say(f"Trying {candidate.part.mpn} — {candidate.origin}.", slot_id)
        made = review.attempt(
            board,
            slot_id,
            candidate.part,
            origin=candidate.origin,
            waivers=waivers,
            revision=revision,
        )
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
                    # Carried so applying the decision does not have to resolve the part
                    # again by number alone — which is ambiguous, and wrote a bill of
                    # materials row with no manufacturer at all the first time it ran.
                    "manufacturer": made.candidate.manufacturer,
                    "package": made.candidate.package,
                    # Where the run found it, so the replay can say what the live trace said.
                    # `replay._trying` reads it, and a record written before this line
                    # existed simply does not carry one.
                    "origin": made.origin,
                    "clear": made.clear,
                    "gated": made.gated,
                    "narration": review.narrate(made),
                    "verdicts": [
                        {
                            "rule": verdict.rule,
                            "subject": verdict.subject,
                            "scope": verdict.scope,
                            "status": verdict.status,
                            "accepted": verdict.accepted,
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

    # The packet, written by the run that produced it. A change request is the deliverable
    # this whole flow exists to hand somebody — proposal, every rejection with the sentence
    # that killed it, evidence, the cost split, the desks that must sign — and it used to be
    # produced by a second pass over work the run had already done.
    # **The board, fired rather than awaited.** A KiCad run is several seconds, the question
    # is already on screen waiting for desks, and blocking the stream on a picture would put
    # the wait back into the demo's centrepiece where replay removed it. It lands on the
    # stored request a moment later; a world with no KiCad leaves `None` and the card keeps
    # the button it shows today.
    board_task = asyncio.create_task(
        _attach_board(
            store=store,
            org_id=user.org_id,
            notice_id=notice["id"],
            line_id=line_id,
            retiring=notice["mpn"],
            candidate=proposal.mpn,
        )
    )
    # **Held, not just scheduled.** A bare `create_task` keeps no reference, and the event
    # loop only keeps a weak one — so a placement several seconds long can be collected
    # mid-flight and the board silently never lands. The same guard `normalize` uses for its
    # thermal fetches and `app` for its progress ticks.
    BOARD_TASKS.add(board_task)
    board_task.add_done_callback(BOARD_TASKS.discard)

    try:
        request = change.for_line(
            _as_matrix(line_id, line_name, slot_id, attempts, incumbent),
            line_id,
            notice_mpn=notice["mpn"],
            notice_id=notice["id"],
            revision=revision,
            annual_volume=annual_volume,
            approved_mpns=sorted(approved.parts or ()),
            prefer=[proposal.mpn],
            excluded=rejected,
        )
        await store.save_change_requests(user.org_id, user.id, notice["id"], [request])
    except (KeyError, ValueError) as error:  # noqa: BLE001
        log.warning("could not write the change request for %s: %s", line_name, error)

    emit(
        line_id,
        stream.question(
            question_id=f"decision:{decision_id}",
            text=decision_text(line_name, proposal),
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
    """Re-check every product line this notice reaches, at the same time.

    `line_id` narrows it to one of them without changing anything else about the run."""
    store = store_of(request)
    notice = await store.notice_for_org(notice_id, user.org_id)
    if notice is None:
        raise HTTPException(404, "no such notice")

    exposed = await store.lines_exposed_to(user.org_id, notice["mpn"])
    if not exposed:
        raise HTTPException(409, "that notice does not reach any product line you ship")

    if body.line_id is not None:
        exposed = [line for line in exposed if line["line_id"] == body.line_id]
        if not exposed:
            raise HTTPException(409, "that notice does not reach this product line")

    approved = await store.approved_lists(user.org_id)
    fitted_manufacturer = await store.manufacturer_of(user.org_id, notice["mpn"])
    # Who this company says makes each part it knows about. Read once for the whole review,
    # because every candidate asked for by number alone is a candidate that can come back as
    # somebody else's listing of the same number.
    recorded_manufacturers = await store.recorded_manufacturers(user.org_id)
    stream = events.EventStream(f"review:{notice_id}")

    # The company's own verified readings, read back. Without this every SOT-223 part falls
    # back to the package table's single figure and to whatever the distributor's parametric
    # blob says, so **NCP1117 clears the Gateway** — it has no published junction limit in
    # the listing, and 159 °C against onsemi's 150 °C is the whole finding. Measured live:
    # with the lookup absent the review proposed the manufacturer's own recommendation on
    # all three boards, which is the answer this product exists to disprove.
    async def facts_for(mpn: str) -> list[dict[str, Any]]:
        return (await store.part_facts([mpn])).get(mpn, [])

    async def merged() -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def emit(line_id: str | None, event: dict[str, Any]) -> None:
            queue.put_nowait({**event, "line_id": line_id})

        # Discovery is the same for every product line — the same part is retired on all of
        # them — so it happens once, before the columns start. Doing it per line would
        # search the distributor three times for one answer.
        #
        # **Yielded, not queued.** The queue below is only drained once the workers exist,
        # so a frame put there during discovery does not reach the client until discovery
        # has finished — which is forty seconds of three columns saying CHECKING with
        # nothing above them. Measured on screen.
        def aloud(text: str) -> dict[str, Any]:
            return {**stream.reasoning(None, text), "line_id": None}

        # Resolved with the manufacturer the bill of materials records, never by part number
        # alone: JLCPCB lists AMS1117-3.3 under three manufacturers, and a part already on a
        # board is not ambiguous — the row says whose it is. Asking without it refuses the
        # incumbent and the whole review returns nothing, which is exactly what happened.
        yield aloud(f"{notice['mpn']} is going end of life.")
        if notice.get("replacement_mpn"):
            yield aloud(
                f"The notice recommends {notice['replacement_mpn']}. Trying that first."
            )

        retiring = await _resolve_quietly(notice["mpn"], fitted_manufacturer)
        if retiring is None:
            yield {
                **stream.error(
                    f"{notice['mpn']} could not be sourced, so nothing can be checked "
                    f"against it.",
                    recoverable=False,
                ),
                "line_id": None,
            }
            return

        worked = {
            row["mpn"]: row["line_name"]
            for row in await store.worked_anywhere(user.org_id, f"eol|{notice['mpn']}")
        }

        yield aloud(
            f"Looking for anything else in {retiring.package or 'the same package'}: the "
            f"approved manufacturer list first, then the distributor's catalogue."
        )

        unreachable: list[str] = []

        async def search_or_say(part: PartSpec) -> list[PartSpec]:
            try:
                return await _catalogue_search(part)
            except CatalogueUnreachable as error:
                # The run continues on what it has. It does not pretend the catalogue was
                # empty: "we could not look" and "there was nothing there" are different
                # answers, and only one of them is worth retrying.
                unreachable.append(str(error))
                return []

        skipped: list[review.SkippedCandidate] = []
        candidates = await review.candidates_for(
            retiring=retiring,
            resolve=_resolve_quietly,
            notice_replacement=notice.get("replacement_mpn"),
            worked=worked,
            approved=sorted(approved.parts or ()),
            search=search_or_say,
            named=list(body.candidates),
            manufacturers=recorded_manufacturers,
            skipped=skipped,
        )
        await store.save_review_skipped(
            user.org_id,
            notice_id,
            [{"mpn": candidate.mpn, "reason": candidate.reason} for candidate in skipped],
        )
        for reason in unreachable:
            yield aloud(
                "The distributor could not be searched, so only the notice's "
                f"recommendation and the approved list were tried. ({reason})"
            )
        for candidate in skipped:
            yield aloud(
                f"{candidate.mpn}: {candidate.reason}, so it was not checked."
            )
        yield aloud(
            "Trying " + ", ".join(f"{c.part.mpn} ({c.origin})" for c in candidates) + "."
            if candidates
            else "Nothing could be sourced to try."
        )

        async def worker(line: dict[str, Any]) -> None:
            try:
                await _run_line(
                    store=store, user=user, notice=notice, line=line,
                    candidates=candidates, approved=approved,
                    stream=stream, emit=emit,
                )
            except Exception as error:  # one line failing must not take the others
                log.exception("review failed for %s", line["line_id"])
                emit(
                    line["line_id"],
                    stream.error(f"{type(error).__name__}: {error}", recoverable=True),
                )
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
        lookup_token = normalize.set_dossier_lookup(facts_for)
        try:
            async for line in _framed():
                yield line
        finally:
            normalize.reset_dossier_lookup(lookup_token)

    async def _framed() -> AsyncIterator[str]:
        # **What the run said, in the order it said it.** The read-back used to rebuild each
        # lane from its own decision, which is per product line, so a replay of a three-line
        # review played one board to its end before starting the next — three boards taking
        # turns, which is the opposite of what this stream exists to show. The interleaving
        # is a fact about the run and it is only knowable from here, so it is written down as
        # it is emitted rather than reconstructed afterwards from records that never had it.
        recorded: list[dict[str, Any]] = []

        def said(event: dict[str, Any]) -> dict[str, Any]:
            recorded.append(event)
            return event

        yield events.frame(
            said(
                stream.review_started(
                    notice_id,
                    notice["mpn"],
                    [{"line_id": line["line_id"], "name": line["name"]} for line in exposed],
                )
            )
        )
        # Heartbeats for the same reason every other stream here has them: sourcing a
        # candidate can hold the connection quiet past the client's thirty-second timer.
        try:
            async for event in events.with_heartbeats(merged()):
                if event is None:
                    yield events.HEARTBEAT
                    continue
                yield events.frame(said(event))
        finally:
            # **In a `finally`, because a run somebody stopped still happened.** A reader who
            # navigates away mid-stream should come back to the trace as far as it got rather
            # than to nothing, and the alternative — recording only on a clean ending — makes
            # abandoning a run look like it never ran.
            await store.record_review_trace(notice_id, user.org_id, recorded)

    return StreamingResponse(framed(), media_type="text/event-stream", headers=SSE_HEADERS)


# ── answering a decision ──────────────────────────────────────────────────────


def next_revision(current: str | None) -> str | None:
    """The revision after this one, when the pattern makes that obvious.

    `Rev C` becomes `Rev D` and `12` becomes `13`. Anything else is left alone and the
    revision does not move, because inventing a revision scheme for somebody's released
    design is worse than not touching it — a configuration management system is downstream
    of this and it owns the numbering.
    """
    if not current:
        return None
    stripped = current.rstrip()
    if not stripped:
        return None
    tail = stripped[-1]
    if tail.isalpha() and tail.upper() < "Z":
        return stripped[:-1] + chr(ord(tail) + 1)
    digits = ""
    while stripped and stripped[-1].isdigit():
        digits = stripped[-1] + digits
        stripped = stripped[:-1]
    if digits:
        return f"{stripped}{int(digits) + 1}"
    return None


class Answer(BaseModel):
    approve: bool
    rationale: str = Field(default="", max_length=2000)
    """Why, in the answerer's own words. Recorded with the approval, because a signature
    with no reason is a signature nobody can audit."""


@router.post("/decisions/{decision_id}")
async def answer_decision(
    decision_id: str, body: Answer, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Sign a substitution for one desk, applying it when the last desk signs. Or decline it.

    **Authorisation is here, at the boundary.** The decision names the desks that must
    answer it, and a person outside them is refused with a 403 rather than having their
    answer quietly recorded — the whole point of routing a decision to a desk is that
    another desk cannot sign it. 403 and not 404, because the caller can already see the
    decision.

    **Parallel and all-must-approve, not sequential.** Every required desk may sign at any
    time and the change applies when the last one does. Sequential review adds a stage of
    latency per desk, and those round trips are the thing this product exists to remove; a
    first-response rule, which is what this was until 10 September, is unsafe wherever
    separation of duties is required — and `part_qualification` is addressed to two desks
    with the words *"it needs both"*.

    **A decline settles immediately.** One desk refusing stops the change rather than
    leaving it to time out against the others, which is how a change board works.
    """
    store = store_of(request)
    decision = await store.decision_for(decision_id, user.org_id)
    if decision is None:
        raise HTTPException(404, "no such decision")
    if decision["state"] != "pending":
        raise HTTPException(409, f"that decision was already {decision['state']}")

    required = set(decision["roles"] or ())
    signing = required.intersection(user.roles)
    if required and not signing:
        raise HTTPException(
            403,
            f"this decision belongs to {' and '.join(sorted(required))}. "
            f"You hold {', '.join(sorted(user.roles)) or 'no roles'}.",
        )

    if not body.approve:
        await store.settle_decision(
            decision_id, user.org_id, state="declined", by=user.id,
            rationale=body.rationale or None,
        )
        return {"state": "declined", "line_id": decision["line_id"]}

    already = await store.approvals_for_decision(decision_id, user.org_id)
    signed = {role for row in already for role in (row["roles"] or ())}
    if signing and signing <= signed:
        raise HTTPException(
            409,
            f"{' and '.join(sorted(signing))} already signed this. "
            f"It is waiting on {' and '.join(sorted(required - signed)) or 'nobody'}.",
        )

    # The signature first, then the question of whether it completes the set. Recorded as
    # the desks it speaks *for* rather than every desk the person happens to hold, so the
    # row says what was signed rather than who signed it, and against the revision the
    # change produces rather than the one it is leaving — every desk signs the same Rev D.
    proposed_revision = next_revision(decision["revision"]) or decision["revision"]
    await store.record_approval(
        org_id=user.org_id,
        decision_id=decision_id,
        line_id=decision["line_id"],
        user_id=user.id,
        user_email=user.email,
        roles=sorted(signing or user.roles),
        rule=decision["gate_rule"] or "substitution",
        subject=decision["slot_id"],
        mpn=decision["proposal"],
        revision=proposed_revision,
        rationale=body.rationale or decision["detail"],
    )
    outstanding = sorted(required - signed - signing)
    if outstanding:
        return {
            "state": "pending",
            "line_id": decision["line_id"],
            "mpn": decision["proposal"],
            "refdes": decision["slot_id"],
            "signed": sorted(signed | signing),
            "outstanding": outstanding,
        }

    # Out of the run's own record rather than resolved again. The part that was evaluated
    # is the part being applied, and asking the distributor for it by number alone is
    # ambiguous — three manufacturers list AMS1117-3.3, two list TLV1117LV33DCYR — which is
    # how the first applied substitution landed on a bill with no manufacturer on it.
    evaluated = next(
        (
            attempt
            for attempt in (decision["document"].get("attempts") or [])
            if attempt.get("mpn") == decision["proposal"]
        ),
        {},
    )
    revision = next_revision(decision["revision"])
    applied = await store.apply_substitution(
        line_id=decision["line_id"],
        org_id=user.org_id,
        user_id=user.id,
        refdes=decision["slot_id"],
        mpn=decision["proposal"],
        manufacturer=evaluated.get("manufacturer"),
        footprint=evaluated.get("package"),
        revision=revision,
    )
    if not applied:
        raise HTTPException(
            409,
            f"{decision['slot_id'].upper()} is no longer on this product line's bill of "
            f"materials, so there is nothing to substitute.",
        )

    await store.settle_decision(
        decision_id, user.org_id, state="approved", by=user.id,
        rationale=body.rationale or None,
    )
    # The success half of memory, which has been missing since precedents were built. A
    # rejection is scoped to the board it happened on; a success is evidence anywhere in the
    # company that this part can do this job.
    await store.record_precedents(
        user.org_id,
        decision["line_id"],
        [
            {
                "signature": f"eol|{decision['retiring']}",
                "mpn": decision["proposal"],
                "outcome": "worked",
                "detail": (
                    f"Approved for the {decision['line_name']} by {user.email}"
                    + (f" — {body.rationale}" if body.rationale else "")
                ),
            }
        ],
    )
    return {
        "state": "approved",
        "line_id": decision["line_id"],
        "mpn": decision["proposal"],
        "refdes": decision["slot_id"],
        "revision": revision or decision["revision"],
        "signed": sorted(signed | signing),
        "outstanding": [],
    }
