"""The board a product line is built from, and what a substitute would do to it.

Two things happen here that happen nowhere else. A **bill of materials that came out of the
design** rather than off a spreadsheet, so the parts under review are the parts on the
board. And the **footprint consequence**: KiCad places the substitute where the retired part
sits, checks the board again, and says which connections that broke.

## KiCad is optional and its absence is said out loud

Every route works without it up to the point where it cannot. An upload is stored and
structurally checked with no KiCad at all; a bill of materials and a consequence need it,
and answer *unavailable* rather than guessing. Nothing here degrades into an estimate.

## It runs in a thread

`subprocess.run` blocks, and a substitution takes the better part of a minute inside an
emulated container. On the event loop that would stop every other request in the process.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import current_user, store_of
from .store import User
from ..kicad import board as board_module
from ..kicad import bom as bom_module
from ..kicad import catalogue, project, render as render_module, runner

log = logging.getLogger(__name__)

router = APIRouter(prefix="/lines", tags=["boards"])

MAX_BUNDLE_BYTES = 60 * 1024 * 1024


class BoardUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    bundle: str = Field(description="The zipped KiCad project, base64 encoded.")
    adopt: bool | None = Field(
        default=None,
        description=(
            "Replace the line's bill of materials with the one in the project. Left unset "
            "it adopts only when the line has no bill yet, because overwriting one somebody "
            "entered is not something to do by default."
        ),
    )


class Substitution(BaseModel):
    retiring: str = Field(min_length=1, max_length=300)
    candidate: str = Field(min_length=1, max_length=300)


def _decoded(bundle: str) -> bytes:
    try:
        raw = base64.b64decode(bundle, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, "that bundle was not valid base64") from error
    if not raw:
        raise HTTPException(422, "that bundle is empty")
    if len(raw) > MAX_BUNDLE_BYTES:
        raise HTTPException(413, "that bundle is larger than 60 MB")
    return raw


async def _owned(request: Request, line_id: str, org_id: str):
    line = await store_of(request).line_for_user(line_id, org_id)
    if line is None:
        raise HTTPException(404, "no such line")
    return line


def _unpacked(raw: bytes, into: Path) -> project.Project:
    try:
        return project.find(project.unpack(raw, into))
    except project.NotAProject as error:
        raise HTTPException(422, str(error)) from error


def _needs_kicad() -> runner.Runner:
    if not runner.available():
        raise HTTPException(
            503,
            "no KiCad is configured on this instance, so a board cannot be read or "
            "substituted here. The project is stored and this works as soon as one is.",
        )
    return runner.require()


def _bill_rows(bill: bom_module.Bill) -> list[dict[str, Any]]:
    return [
        {
            "refdes": row.refdes,
            "mpn": row.mpn,
            "value": row.value,
            "footprint": row.footprint,
            "distributor_code": row.distributor_code,
        }
        for row in bill.rows
    ]


def _read_bill(raw: bytes) -> tuple[bom_module.Bill, str]:
    """Unpack into a scratch directory, read the bill, throw the directory away."""
    kicad = _needs_kicad()
    workdir = Path(tempfile.mkdtemp(prefix="continuity-kicad-"))
    try:
        found = _unpacked(raw, workdir)
        return bom_module.read(found, kicad), found.name
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@router.put("/{line_id}/board")
async def put_board(
    line_id: str,
    body: BoardUpload,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    await _owned(request, line_id, user.org_id)
    store = store_of(request)
    raw = _decoded(body.bundle)

    workdir = Path(tempfile.mkdtemp(prefix="continuity-kicad-"))
    try:
        found = _unpacked(raw, workdir)
        name = found.name
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    await store.save_board(
        line_id=line_id,
        org_id=user.org_id,
        user_id=user.id,
        filename=body.filename,
        project=name,
        bundle=raw,
    )

    answer: dict[str, Any] = {
        "project": name,
        "filename": body.filename,
        "bytes": len(raw),
        "kicad": runner.available(),
        "adopted": False,
    }
    if not runner.available():
        return answer

    bill, _ = await asyncio.to_thread(_read_bill, raw)
    answer["bom"] = _bill_rows(bill)
    answer["mpn_field"] = bill.mpn_field

    existing = await store.bom_for_line(line_id, user.org_id)
    adopt = body.adopt if body.adopt is not None else not existing
    if adopt:
        await store.save_bom_rows(
            line_id,
            user.id,
            user.org_id,
            [
                {
                    "refdes": row.refdes,
                    "mpn": row.mpn,
                    "footprint": row.footprint or None,
                    "populated": True,
                }
                for row in bill.rows
                if row.mpn
            ],
        )
        answer["adopted"] = True
    return answer


@router.get("/{line_id}/board")
async def get_board(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    await _owned(request, line_id, user.org_id)
    stored = await store_of(request).board_for(line_id, user.org_id)
    if stored is None:
        return {"board": None, "kicad": runner.available()}
    return {
        "board": {
            "filename": stored["filename"],
            "project": stored["project"],
            "bytes": stored["bytes"],
            "uploaded_at": stored["uploaded_at"].isoformat(),
        },
        "kicad": runner.available(),
    }


@router.delete("/{line_id}/board", status_code=204)
async def delete_board(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> None:
    await _owned(request, line_id, user.org_id)
    if not await store_of(request).delete_board(line_id, user.org_id):
        raise HTTPException(404, "no board is stored for that line")


@router.get("/{line_id}/board/bom")
async def board_bom(
    line_id: str, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    await _owned(request, line_id, user.org_id)
    stored = await store_of(request).board_bundle(line_id, user.org_id)
    if stored is None:
        raise HTTPException(404, "no board is stored for that line")
    _needs_kicad()
    bill, name = await asyncio.to_thread(_read_bill, stored[1])
    return {"project": name, "mpn_field": bill.mpn_field, "rows": _bill_rows(bill)}


def _consequence(raw: bytes, retiring: str, candidate: str) -> dict[str, Any]:
    """Everything the substitution needs, computed in one scratch directory."""
    kicad = _needs_kicad()
    workdir = Path(tempfile.mkdtemp(prefix="continuity-kicad-"))
    try:
        found = _unpacked(raw, workdir)
        bill = bom_module.read(found, kicad)
        carrying = bill.carrying(retiring)
        if not carrying:
            raise HTTPException(
                409,
                f"this board does not carry {retiring}. Its bill of materials was read "
                f"from the {bill.mpn_field} field.",
            )
        if len(carrying) > 1:
            raise HTTPException(
                409,
                f"{retiring} sits at {', '.join(row.refdes for row in carrying)} on this "
                f"board. Substituting several positions at once is not supported yet.",
            )
        placed = carrying[0]

        try:
            pinout = catalogue.pinout(candidate)
        except catalogue.NoPinout as error:
            raise HTTPException(422, str(error)) from error
        try:
            incumbent = catalogue.pinout(retiring)
        except catalogue.NoPinout as error:
            raise HTTPException(422, str(error)) from error

        footprint = catalogue.footprint_for(
            pinout.package,
            incumbent_package=incumbent.package,
            incumbent_footprint=placed.footprint,
        )
        outcome = board_module.consequence(
            found,
            kicad,
            refdes=placed.refdes,
            footprint=footprint,
            pinout=pinout.pins,
            value=candidate,
        )
        return {
            "refdes": placed.refdes,
            "retiring": retiring,
            "candidate": candidate,
            "package": {"from": incumbent.package, "to": pinout.package},
            "footprint": {"from": outcome.placement.footprint, "to": footprint},
            "pinout_source": pinout.source,
            "wiring": {
                "wired": dict(outcome.wiring.wired),
                "unwired_pads": list(outcome.wiring.unwired_pads),
                "stranded": list(outcome.wiring.roles_with_nowhere_to_go),
            },
            "broke_connections": outcome.broke_connections,
            "added": [
                {
                    "rule": finding.rule,
                    "description": finding.description,
                    "severity": finding.severity,
                    "items": list(finding.items),
                }
                for finding in outcome.delta.added
            ],
            "counts": {
                rule: {"before": before, "after": after}
                for rule, (before, after) in outcome.delta.by_rule().items()
                if before != after
            },
            "crop": outcome.crop.view_box,
            "page": {"width": outcome.before.width_mm, "height": outcome.before.height_mm},
            "before_svg": outcome.before.svg,
            "after_svg": outcome.after.svg,
        }
    except board_module.NoSuchPart as error:
        raise HTTPException(409, str(error)) from error
    except runner.KicadFailed as error:
        log.warning("kicad refused a substitution: %s", error)
        raise HTTPException(502, "KiCad could not complete that substitution") from error
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


_DRAWN: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_DRAWN_LIMIT = 12
"""Boards already drawn, by content.

A render is three KiCad invocations — export the picture, export the schematic bill, inspect
the placements — and about three seconds on this machine. The answer is a pure function of
the stored project and the part being pointed at, and a stored project does not change
between two presses of the same button, so the second press has nothing to recompute. It was
three seconds every time, which on a toggle reads as broken rather than slow.

Keyed on the bundle's digest rather than the line id: replacing a board changes the digest,
and two product lines that somehow carried the same file would share the work.
"""


def _drawn(key: str) -> dict[str, Any] | None:
    found = _DRAWN.get(key)
    if found is not None:
        _DRAWN.move_to_end(key)
    return found


def _remember(key: str, picture: dict[str, Any]) -> dict[str, Any]:
    _DRAWN[key] = picture
    while len(_DRAWN) > _DRAWN_LIMIT:
        _DRAWN.popitem(last=False)
    return picture


CONTENT_MARGIN_MM = 8.0
"""Room around the outermost footprint, so the board's edge is not flush with the frame."""


def _extent(placements: Any) -> "render_module.Crop | None":
    """The rectangle the placed footprints occupy, in board millimetres.

    A footprint's origin rather than its outline, which under-reads the true edge by a
    pad or two — that is what the margin is for. Reading the real board outline means
    parsing `Edge.Cuts` out of the SVG, and a picture that is eight millimetres generous
    is not worth a parser that can be wrong.
    """
    points = [(one.x_mm, one.y_mm) for one in placements]
    if not points:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return render_module.Crop(
        x=min(xs) - CONTENT_MARGIN_MM,
        y=min(ys) - CONTENT_MARGIN_MM,
        width=(max(xs) - min(xs)) + CONTENT_MARGIN_MM * 2,
        height=(max(ys) - min(ys)) + CONTENT_MARGIN_MM * 2,
    )


def _render(raw: bytes, mark: str | None) -> dict[str, Any]:
    """The board as it is, and where one part sits on it.

    Separate from `_consequence` because it answers a question that does not involve a
    substitute: *show me the board*. Before a review has proposed anything there is nothing
    to place, and a picture of the product's actual PCB is a real answer where a disabled
    control is not.

    `mark` is a part number to locate — the retiring one, normally. It is optional and its
    absence is not an error: a product line with no notice against it still has a board.
    """
    kicad = _needs_kicad()
    workdir = Path(tempfile.mkdtemp(prefix="continuity-kicad-"))
    try:
        found = _unpacked(raw, workdir)
        picture = render_module.svg(
            kicad, workdir=found.root, board=found.board_name, out="kicad-board.svg"
        )
        # Always, because the picture is otherwise unusable. KiCad is asked for the *page*
        # rather than the board — deliberately, so a before and an after share coordinates —
        # and a 46 mm board on a 297 mm page is a stamp in the middle of a black rectangle.
        # The footprints are where the board is, so their extent is what to look at.
        placed = board_module.placements(found, kicad)
        content = _extent(placed.values()) or render_module.Crop(
            x=0.0, y=0.0, width=picture.width_mm, height=picture.height_mm
        )

        crop: str | None = None
        refdes: str | None = None
        if mark:
            carrying = bom_module.read(found, kicad).carrying(mark)
            if carrying:
                one = placed.get(carrying[0].refdes)
                if one is not None:
                    refdes = one.refdes
                    crop = render_module.around(one.x_mm, one.y_mm).view_box
        return {
            "svg": picture.svg,
            "page": {"width": picture.width_mm, "height": picture.height_mm},
            "content": content.view_box,
            "marked": refdes,
            "crop": crop,
        }
    except runner.KicadFailed as error:
        log.warning("kicad could not render a board: %s", error)
        raise HTTPException(502, "KiCad could not render that board") from error
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@router.get("/{line_id}/board/render")
async def board_render(
    line_id: str,
    request: Request,
    mark: str | None = None,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """A picture of this product line's board, with one part located on it."""
    await _owned(request, line_id, user.org_id)
    stored = await store_of(request).board_bundle(line_id, user.org_id)
    if stored is None:
        raise HTTPException(404, "no board is stored for that line")
    _needs_kicad()
    key = f"{hashlib.sha256(stored[1]).hexdigest()}:{mark or ''}"
    already = _drawn(key)
    if already is not None:
        return already
    return _remember(key, await asyncio.to_thread(_render, stored[1], mark))


async def consequence_for(
    store: Any,
    line_id: str,
    org_id: str,
    retiring: str,
    candidate: str,
) -> dict[str, Any] | None:
    """One board's consequence, or `None` where it cannot be had.

    **Both callers share this**, so a picture stored by a run and one drawn on demand are the
    same picture. The endpoint below reports why it could not be done; the review fires this
    from a background task and cannot report anything to anybody, so it asks first whether
    KiCad is there and swallows everything else. A world with no KiCad gets the button it
    gets today, which is the honest degradation that surface already renders.
    """
    if not runner.available():
        return None
    stored = await store.board_bundle(line_id, org_id)
    if stored is None:
        return None
    # **Raised, not swallowed.** `_consequence` refuses a part with no pinout on file by
    # name and a board that does not carry the part with its own sentence, and those are the
    # only actionable things this endpoint can say. Catching here turned every one of them
    # into a generic "that board could not be substituted" — the swallow belongs to the
    # background caller, which has nobody to tell, and it lives there.
    return await asyncio.to_thread(_consequence, stored[1], retiring, candidate)


@router.post("/{line_id}/board/consequence")
async def consequence(
    line_id: str,
    body: Substitution,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """What this substitute does to this line's board, as KiCad reports it."""
    store = store_of(request)
    await _owned(request, line_id, user.org_id)
    # The 404 and the 503 are the two things this caller *can* be told; the shared coroutine
    # answers `None` for both because a background caller has nobody to tell.
    if await store.board_bundle(line_id, user.org_id) is None:
        raise HTTPException(404, "no board is stored for that line")
    _needs_kicad()
    made = await consequence_for(store, line_id, user.org_id, body.retiring, body.candidate)
    if made is None:
        raise HTTPException(409, "that board could not be substituted")
    return made
