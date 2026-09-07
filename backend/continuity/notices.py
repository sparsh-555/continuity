"""What a change notice says, and which of our products it reaches.

A product change notice is the trigger the whole enterprise flow hangs off, and it arrives
as a PDF written for a human: a part number, a last-order date, and — often — a
recommendation the manufacturer made without seeing any of our boards.

## Claim and verify, as everywhere else

The model reports what it *read* and quotes the line it read it from; this module checks
each quoted line actually appears in the document before believing any of it. A notice that
invents an MPN would start a review of a part nobody sells, and a notice that invents a date
would put an urgency on it that nothing supports. The same discipline as `parts.datasheet`,
for the same reason: the expensive failures are the plausible ones.

## What this deliberately does not do

It does not decide anything. Which lines are affected is `store.lines_exposed_to`, a b-tree
probe against the BOMs; whether a replacement survives is the matrix. This module's whole
job is turning a document into the two or three facts those need.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from . import llm
from .parts.datasheet import text_from_pdf

log = logging.getLogger(__name__)

MAX_TEXT = 20_000
"""Enough for a notice. They run to a page or two; a longer document is not one."""

SYSTEM = """You read a product change notice and report only what it states.

Return ONE JSON object with ONLY these keys:
  mpn, mpn_line, manufacturer, effective_date, effective_date_line,
  replacement_mpn, replacement_line, reason

- mpn: the manufacturer part number being discontinued or changed. Exact, as printed.
- mpn_line: the exact full line of the document you read the MPN from.
- manufacturer: who issued the notice.
- effective_date: the date after which the part can no longer be ordered, ISO 8601
  (YYYY-MM-DD), or null.
- effective_date_line: the exact line you read that date from, or null.
- replacement_mpn: the part the notice recommends, or null if it recommends none.
- replacement_line: the exact line you read the recommendation from, or null.
- reason: one short sentence, in the notice's own terms, for why it was issued.

A notice prints several dates and only one of them ends ordering. Take the last time
buy or last order date. Never the date the notice was issued, never a last time ship
date, never a date by which a response is requested. If the notice states no date that
ends ordering, effective_date is null however many other dates are on the page.

A notice that recommends nothing says so in words: "none", "to be advised", "under
evaluation". Those are not part numbers. replacement_mpn is null unless the notice
prints a part number to order instead.

Every *_line must be copied verbatim from the document. Never paraphrase one, never
assemble one from separate places, and use null rather than inventing one. If the document
does not state something, that field is null — do not infer it from the part number, from
what is typical, or from another notice you have seen."""

_MPN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_./+]{2,49}$")
"""A part number's shape. Loose on purpose — vendors are inventive — but it rules out a
sentence, which is what an unconstrained field tends to come back as."""

_NOT_A_PART = frozenset(
    {
        "none", "nil", "null", "na", "tbd", "tba", "unknown", "pending",
        "tobeadvised", "tobeconfirmed", "notapplicable",
        "noreplacement", "underevaluation", "undetermined", "notyetdetermined",
    }
)
"""Words a notice uses where a part number would go, and which look like one.

A preliminary notice writes *Recommended replacement: none.* That line is real, so
quoting it proves nothing, and `none` passes the shape test above with room to spare.
Believed, it opens a review of a part called "none" and searches every distributor for
it. The absence has to survive as an absence."""


def _flattened(value: str) -> str:
    """Lowercase letters and digits only, so `To be advised.` meets `tobeadvised`."""
    return "".join(character for character in value.lower() if character.isalnum())


def _is_a_part_number(value: str) -> bool:
    return bool(_MPN.match(value.strip())) and _flattened(value) not in _NOT_A_PART


@dataclass(frozen=True)
class Notice:
    """One change notice, reduced to what a review needs and nothing else."""

    mpn: str
    mpn_line: str
    manufacturer: str | None = None
    effective_date: str | None = None
    effective_date_line: str | None = None
    replacement_mpn: str | None = None
    replacement_line: str | None = None
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "mpn": self.mpn,
            "mpn_line": self.mpn_line,
            "manufacturer": self.manufacturer,
            "effective_date": self.effective_date,
            "effective_date_line": self.effective_date_line,
            "replacement_mpn": self.replacement_mpn,
            "replacement_line": self.replacement_line,
            "reason": self.reason,
        }


def _collapsed(value: str) -> str:
    """Whitespace-insensitive, because PDF extraction re-flows lines unpredictably."""
    return " ".join(value.split())


def text_of(document: bytes) -> str | None:
    """The notice's text, whether it arrived as a PDF or as plain text.

    Mail carries both — a PCN is usually attached as a PDF and sometimes pasted into the
    body — and refusing the second would make the connector fail on a real message for a
    reason that has nothing to do with the notice.
    """
    if document[:5] == b"%PDF-":
        extracted = text_from_pdf(document)
        return extracted[:MAX_TEXT] if extracted else None
    try:
        return document.decode("utf-8")[:MAX_TEXT] or None
    except UnicodeDecodeError:
        return None


def _from_reply(reply: Mapping[str, Any], text: str) -> Notice | None:
    """Believe the model only where the document backs it up."""
    mpn = reply.get("mpn")
    mpn_line = reply.get("mpn_line")
    if not isinstance(mpn, str) or not _is_a_part_number(mpn):
        return None
    if not isinstance(mpn_line, str) or _collapsed(mpn_line) not in _collapsed(text):
        return None
    if _collapsed(mpn) not in _collapsed(mpn_line):
        # The quoted line has to be the line the part number is on. Without this a model
        # can quote any real sentence and attach any part number to it, which passes the
        # containment check above while sourcing nothing.
        return None

    def quoted(value_key: str, line_key: str) -> tuple[Any, str | None]:
        value = reply.get(value_key)
        line = reply.get(line_key)
        if value is None or not isinstance(line, str):
            return None, None
        if _collapsed(line) not in _collapsed(text):
            return None, None
        return value, line

    effective_date, effective_line = quoted("effective_date", "effective_date_line")
    replacement, replacement_line = quoted("replacement_mpn", "replacement_line")
    if replacement is not None and not (
        isinstance(replacement, str)
        and _is_a_part_number(replacement)
        # The same rule the affected part number lives under, and for the same reason:
        # quoting *a* line is not sourcing *this* value. Without it a reply can cite the
        # real recommendation line and name a different part on it, and the change
        # request then proposes a part the manufacturer never mentioned.
        and _collapsed(replacement) in _collapsed(replacement_line or "")
    ):
        replacement, replacement_line = None, None
    if effective_date is not None and not (
        isinstance(effective_date, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective_date.strip())
    ):
        effective_date, effective_line = None, None

    manufacturer = reply.get("manufacturer")
    reason = reply.get("reason")
    return Notice(
        mpn=mpn.strip(),
        mpn_line=mpn_line.strip(),
        manufacturer=manufacturer.strip() if isinstance(manufacturer, str) else None,
        effective_date=effective_date.strip() if isinstance(effective_date, str) else None,
        effective_date_line=effective_line,
        replacement_mpn=replacement.strip() if isinstance(replacement, str) else None,
        replacement_line=replacement_line,
        reason=reason.strip() if isinstance(reason, str) else None,
    )


async def read(document: bytes) -> Notice | None:
    """One notice, or `None` when nothing in it can be trusted.

    `None` rather than a partial guess: every downstream step keys off the MPN, so a notice
    whose part number could not be sourced from the text would start a review of whatever
    the model happened to say. Returning nothing lets the caller say *we could not read
    this*, which is a true and actionable answer.
    """
    text = text_of(document)
    if not text or not text.strip():
        return None
    if not llm.available():
        return None
    try:
        reply = await llm.complete_json(SYSTEM, text)
    except Exception as error:  # noqa: BLE001
        log.warning("could not read the change notice: %s", error)
        return None
    if not isinstance(reply, Mapping):
        return None
    return _from_reply(reply, text)
