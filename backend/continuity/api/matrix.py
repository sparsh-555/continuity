"""One candidate against every product line that carries the part it would replace.

The endpoint behind item 12's matrix. It resolves stored product lines into boards, puts
each candidate into the slot under review, and returns the grid — every cell attributable
to a board, a candidate and the desk that owns whatever failed on it.

## Why the parts are sourced rather than read out of a column

A BOM row is a refdes and an mpn. Checking it electrically needs voltage ratings, current
limits, a package and a θJA, and those are properties of the part rather than of the line,
so they come from the same sourcing path a design run uses — searched, normalised, and
cached. A column of denormalised specs would be a second copy of the part catalogue that
nothing keeps current.

That makes this endpoint slower than a read, which is why it takes the whole matrix in one
request instead of a cell at a time: the parts are resolved once and reused across every
cell in the grid.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import current_user, store_of
from .store import User
from ..engine.models import PartSpec
from ..graph import sourcing
from ..matrix import Cell, Matrix, evaluate_matrix
from ..parts import normalize
from ..parts import search as part_search
from ..profile import OperatingProfile, board_from

router = APIRouter(prefix="/matrix", tags=["matrix"])


class MatrixRequest(BaseModel):
    line_ids: list[str] = Field(min_length=1, max_length=25)
    slot: str = Field(min_length=1, max_length=100)
    """The refdes under review — the position the part being replaced sits in."""

    candidates: list[str] = Field(min_length=1, max_length=10)
    """MPNs to try in that position, the incumbent included where the caller wants the
    row that says what the board does today."""


class Ambiguous(Exception):
    """One MPN, more than one manufacturer, and no way to tell which was meant."""

    def __init__(self, mpn: str, manufacturers: Sequence[str]) -> None:
        self.mpn = mpn
        self.manufacturers = list(manufacturers)
        super().__init__(
            f"{mpn} is listed by {' and '.join(self.manufacturers)}, and their listings "
            "disagree — say which manufacturer you mean"
        )


async def resolve(mpn: str, manufacturer: str | None = None) -> PartSpec | None:
    """One MPN, through the path a design run already trusts.

    Returns `None` rather than raising when the distributor has never heard of the part.
    A matrix that refuses to render because one candidate could not be found tells the
    reader nothing about the other three, and "we could not find this part" is itself a
    result worth putting on screen.

    **Raises `Ambiguous` when one MPN is listed by more than one manufacturer**, because
    picking the first is picking a part nobody named. JLCPCB carries `TLV1117LV33DCYR`
    twice: TI's own listing states a 5.5 V supply ceiling, and a second manufacturer's
    states 12 V. Those are not two descriptions of one part — they are two parts wearing
    the same number, and checking a 12 V substitution into a board whose regulator dies
    above 6 V is precisely the mistake a substitution review exists to catch.
    """
    try:
        hits = await part_search.search(mpn, limit=10)
    except Exception:
        return None

    exact = [c for c in hits if c.mpn.upper() == mpn.upper()]
    if not exact:
        return None

    # A part already on a bill of materials is not ambiguous: the BOM row says whose it is.
    # Without this the guard fires on the incumbent — JLCPCB lists AMS1117-3.3 under three
    # manufacturers — and a board that has shipped for years cannot be assembled at all.
    if manufacturer:
        named = [c for c in exact if (c.manufacturer or "").upper() == manufacturer.upper()]
        if named:
            return await sourcing.choose(named[0])

    makers = list(dict.fromkeys(c.manufacturer for c in exact if c.manufacturer))
    if len(makers) > 1:
        raise Ambiguous(mpn, makers)
    return await sourcing.choose(exact[0])


def _view(cell: Cell) -> dict[str, Any]:
    return {
        "line_id": cell.line_id,
        "line_name": cell.line_name,
        "mpn": cell.candidate.mpn,
        "manufacturer": cell.candidate.manufacturer,
        "is_incumbent": cell.is_incumbent,
        "replaces": cell.incumbent_mpn,
        "ok": cell.ok,
        "margin": cell.margin,
        "counts": cell.counts,
        "departments": list(cell.departments),
        "checks": [
            {
                "rule": v.rule,
                "scope": v.scope,
                "status": v.status,
                "detail": v.detail,
                "margin": v.margin,
                "accepted": v.accepted,
                "evidence": [
                    {"field": e.field, "value": e.value, "source": e.source}
                    for e in v.evidence
                ],
            }
            for v in cell.verdicts
        ],
    }


def _matrix_view(
    matrix: Matrix, unresolved: list[str], ambiguous: Mapping[str, str] | None = None
) -> dict[str, Any]:
    return {
        "slot": matrix.slot,
        "lines": list(matrix.lines),
        "candidates": list(matrix.candidates),
        "viable_everywhere": list(matrix.viable_on_every_board()),
        "departments": list(matrix.departments()),
        # Named rather than dropped. A candidate the distributor has never heard of is a
        # missing column, and a grid that quietly renders three of four is a grid that
        # lies about what was checked.
        "unresolved": unresolved,
        # One MPN, two manufacturers, two different parts. Named rather than resolved by
        # coin toss: which one you meant is a question only the person asking can answer.
        "ambiguous": dict(ambiguous or {}),
        "cells": [_view(cell) for cell in matrix.cells],
    }


@router.post("")
async def build_matrix(
    body: MatrixRequest, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    store = store_of(request)

    # The same stored-dossier lookup a design run installs. Without it every SOT-223 part
    # falls back to the package table's single figure, so four different regulators come
    # out with four identical junction temperatures — the evidence row says so plainly,
    # which is honest and useless. What a verified datasheet reading is *for* is being
    # read back here.
    lookup_token = normalize.set_dossier_lookup(
        lambda mpn: _facts_for(store, mpn)
    )
    try:
        return await _build(body, store, user)
    finally:
        normalize.reset_dossier_lookup(lookup_token)


async def _facts_for(store: Any, mpn: str) -> list[dict[str, Any]]:
    return (await store.part_facts([mpn])).get(mpn, [])


async def _build(body: MatrixRequest, store: Any, user: User) -> dict[str, Any]:
    lines = []
    for line_id in body.line_ids:
        line = await store.line_for_user(line_id, user.org_id)
        if line is None:
            raise HTTPException(404, "no such line")
        if not line.profile:
            raise HTTPException(
                409,
                f"{line.name} has no operating profile, so there are no conditions to "
                "check a substitution against",
            )
        lines.append(line)

    boms = {
        line.id: await store.bom_for_line(line.id, user.org_id) for line in lines
    }

    wanted = {row["mpn"] for bom in boms.values() for row in bom if row.get("populated", True)}
    wanted |= set(body.candidates)
    ordered = sorted(wanted)
    # Who this company says makes each of these, from its own bills and its approved list.
    # An MPN alone does not name a part — JLCPCB lists `AMS1117-3.3` under three
    # manufacturers and `TLV1117LV33DCYR` under two — so asking by number came back as
    # *several companies list this* and the part was skipped rather than checked. The
    # record answers the question for anything this company has bought or qualified.
    recorded = await store.recorded_manufacturers(user.org_id)
    resolved = await asyncio.gather(
        *(resolve(mpn, recorded.get(mpn.upper())) for mpn in ordered),
        return_exceptions=True,
    )

    specs: dict[str, PartSpec] = {}
    ambiguous: dict[str, str] = {}
    for mpn, outcome in zip(ordered, resolved):
        if isinstance(outcome, Ambiguous):
            ambiguous[mpn] = str(outcome)
        elif isinstance(outcome, BaseException):
            raise outcome
        elif outcome is not None:
            specs[mpn] = outcome

    candidates = [specs[mpn] for mpn in body.candidates if mpn in specs]
    if not candidates:
        raise HTTPException(422, "none of the candidates could be sourced")

    # The same lists a design run is checked against. A substitution review that ignored
    # the company's own AML would recommend a part nobody has qualified.
    approved = await store.approved_lists(user.org_id)

    boards = []
    for line in lines:
        try:
            profile = OperatingProfile.from_json(line.profile)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(409, f"{line.name}: {exc}") from exc
        board = replace(board_from(profile, boms[line.id], specs), approved=approved)
        if body.slot not in board.slots:
            raise HTTPException(
                409,
                f"{line.name} does not carry {body.slot}, so it is not affected by this part",
            )
        boards.append((line.id, line.name, board))

    matrix = evaluate_matrix(boards, candidates, body.slot)
    # "Never heard of it" and "heard of it twice" are different answers and belong in
    # different lists. Reporting an ambiguous part as merely missing would hide the one
    # thing the reader has to act on: saying which manufacturer they meant.
    return _matrix_view(
        matrix,
        sorted(
            mpn for mpn in body.candidates if mpn not in specs and mpn not in ambiguous
        ),
        ambiguous,
    )
