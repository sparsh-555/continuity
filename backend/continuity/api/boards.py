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
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import current_user, store_of
from .store import User
from ..kicad import board as board_module
from ..kicad import bom as bom_module
from ..kicad import catalogue, project, runner

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


@router.post("/{line_id}/board/consequence")
async def consequence(
    line_id: str,
    body: Substitution,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """What this substitute does to this line's board, as KiCad reports it."""
    await _owned(request, line_id, user.org_id)
    stored = await store_of(request).board_bundle(line_id, user.org_id)
    if stored is None:
        raise HTTPException(404, "no board is stored for that line")
    _needs_kicad()
    return await asyncio.to_thread(_consequence, stored[1], body.retiring, body.candidate)
