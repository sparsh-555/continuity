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

import base64
import binascii
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import current_user, store_of
from .store import User
from .. import notices as reader

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
