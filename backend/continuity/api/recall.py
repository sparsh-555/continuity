"""Assemble what a company knows about a part, from the rows that record it.

Memory used to be built out of design runs: parts came from `threads.bom` and every
finding joined through `threads`, so a company that had never opened the design side had
no memory at all, and the three things this product actually produces — a notice, a
decision, a precedent — were invisible to it.

The record is wider than that. A product line carries a bill of materials in `line_parts`
whether or not anyone ran a design here, a notice retires a part in a manufacturer's own
words, an approval names who signed and why, and a precedent records what a board already
ruled out. This module takes those rows and puts them under the part they are about.

Pure on purpose: the reads live in `Store.memory_for_user` and everything below is
arithmetic on the rows they return, so the shape of a memory can be tested without a
database.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from ..parts import dossier

Row = Mapping[str, Any]


def fact_from(row: Row) -> dict[str, Any]:
    """One verified part fact, with its citation separated from its marker.

    `part_facts.source` carries both: `datasheet — ` says the reading outranks a
    distributor's listing, and what follows is the line it was read from *when there was
    one*. A reading with no line stores the marker plus `source unavailable`, which is
    honest in the database and was a lie on screen, where the panel printed the whole
    string inside quotation marks. Ten of AMS1117-3.3's eleven facts appeared to cite a
    datasheet line that said the source was unavailable.
    """
    source = row.get("source")
    verified = dossier.is_verified(source)
    quote = source[len(dossier.VERIFIED_PREFIX):] if verified and source else source
    return {
        "field": row.get("field"),
        "value": row.get("value"),
        "verified": verified,
        "quote": None if quote == dossier.NO_SOURCE else quote,
    }


def lifecycle_from(notice: Row, today: date) -> str:
    """What a notice makes a part's lifecycle, from the date the notice states.

    Two different answers, and the difference is the one a buyer cares about. A part whose
    last order date has passed is **obsolete**: no more can be bought at any price. A part
    whose date is still ahead is **nrnd**, which is to say it is still orderable and must
    not go into anything new.

    A notice with no date at all gets `nrnd` rather than nothing, because a preliminary
    notice withholding its date is still the manufacturer saying this part is going away.
    Nothing here overwrites a lifecycle a distributor stated: `compose` only reaches this
    when no other source has answered.
    """
    stated = notice.get("effective_date")
    if isinstance(stated, str):
        try:
            stated = date.fromisoformat(stated)
        except ValueError:
            stated = None
    if isinstance(stated, date) and stated <= today:
        return "obsolete"
    return "nrnd"


def _blank(mpn: str) -> dict[str, Any]:
    return {
        "mpn": mpn,
        "manufacturer": None,
        "lifecycle": None,
        "used_in": {},
        "retirement": None,
        "history": [],
        "findings": [],
        "facts": [],
    }


class _Parts:
    """Parts under construction, keyed by MPN, in first-seen order."""

    def __init__(self) -> None:
        self._by_mpn: dict[str, dict[str, Any]] = {}

    def at(self, mpn: object) -> dict[str, Any] | None:
        """The part this row is about, or `None` when the row does not name one.

        A row with no MPN cannot be filed anywhere useful, and inventing a bucket for it
        would put an approval or a rejection under a heading no reader could act on.
        """
        if not isinstance(mpn, str) or not mpn:
            return None
        return self._by_mpn.setdefault(mpn, _blank(mpn))

    def describe(self, part: dict[str, Any], row: Row) -> None:
        """Fill in what the part *is*, without letting a later row overwrite an earlier one.

        Rows arrive from several tables and disagree about how much they know: a bill of
        materials states a manufacturer, a design run's finding may state a lifecycle, a
        precedent states neither. First non-empty answer wins, which makes the read order
        in `Store.memory_for_user` the priority order.
        """
        for field in ("manufacturer", "lifecycle"):
            if part[field] is None and row.get(field):
                part[field] = row[field]

    def used_on(self, part: dict[str, Any], row: Row, refdes: Sequence[str] = ()) -> None:
        edge = part["used_in"].setdefault(
            row["line_id"],
            {"line_id": row["line_id"], "line_name": row["line_name"], "refdes": []},
        )
        for designator in refdes:
            if designator not in edge["refdes"]:
                edge["refdes"].append(designator)

    def values(self) -> list[dict[str, Any]]:
        return list(self._by_mpn.values())


def compose(
    *,
    lines: Sequence[Row],
    bom: Sequence[Row],
    notices: Sequence[Row],
    precedents: Sequence[Row],
    approvals: Sequence[Row],
    decisions: Sequence[Row],
    thread_parts: Sequence[Row],
    findings: Sequence[Row],
    facts: Mapping[str, list[dict[str, Any]]],
    part_limit: int,
    today: date | None = None,
) -> dict[str, Any]:
    """One entry per part, carrying every board it sits on and everything decided about it."""
    today = today or date.today()
    parts = _Parts()

    for row in bom:
        part = parts.at(row["mpn"])
        if part is None:
            continue
        parts.describe(part, row)
        parts.used_on(part, row, row.get("refdes") or ())

    # A design run's parts list, kept beside the bill of materials rather than instead of
    # it. The design side still exists and its parts are as real as any other; what it
    # cannot state is a reference designator, so those edges carry an empty one.
    for row in thread_parts:
        part = parts.at(row["mpn"])
        if part is None:
            continue
        parts.describe(part, row)
        parts.used_on(part, row)

    for row in notices:
        part = parts.at(row["mpn"])
        if part is None:
            continue
        parts.describe(part, row)
        if part["retirement"] is None:
            part["retirement"] = _retirement(row)
        if part["lifecycle"] is None:
            part["lifecycle"] = lifecycle_from(row, today)
        # The replacement the manufacturer recommended is a part in its own right, and the
        # reason it is on this screen at all. Without this it appears only if some board
        # already carries it, which is exactly what is not true of a recommendation.
        proposed = parts.at(row.get("replacement_mpn"))
        if proposed is not None:
            proposed["history"].append(
                {
                    "kind": "recommended",
                    "for_mpn": row["mpn"],
                    "detail": row.get("replacement_line"),
                    "source": row.get("source"),
                    "at": _when(row.get("created_at")),
                }
            )

    for row in precedents:
        part = parts.at(row["mpn"])
        if part is None:
            continue
        part["history"].append(
            {
                "kind": "worked" if row["outcome"] == "worked" else "rejected",
                "line_id": row["line_id"],
                "line_name": row["line_name"],
                "signature": row.get("signature"),
                "detail": row.get("detail"),
                "at": _when(row.get("recorded_at")),
            }
        )

    for row in approvals:
        part = parts.at(row["mpn"])
        if part is None:
            continue
        part["history"].append(
            {
                "kind": "approved",
                "line_id": row.get("line_id"),
                "line_name": row.get("line_name"),
                "by": row["user_email"],
                "roles": list(row.get("roles") or []),
                "rule": row.get("rule"),
                "subject": row.get("subject"),
                "revision": row.get("revision"),
                "rationale": row.get("rationale"),
                "at": _when(row.get("created_at")),
            }
        )

    for row in decisions:
        # An **approved** decision is not listed here, because answering one writes an
        # approval in the same request and the approval is the fuller record: it names the
        # person, and this row can only name the roles that were allowed to answer.
        # Listing both read on screen as one board approving the same part twice.
        #
        # A declined one is listed, because a refusal writes no approval and nothing else
        # in the record remembers that somebody said no.
        if row["state"] == "approved":
            continue
        part = parts.at(row["proposal"])
        if part is None:
            continue
        part["history"].append(
            {
                "kind": "awaiting" if row["state"] == "pending" else row["state"],
                "line_id": row["line_id"],
                "line_name": row["line_name"],
                "replaces": row.get("retiring"),
                "roles": list(row.get("roles") or []),
                "rule": row.get("gate_rule"),
                "subject": row.get("slot_id"),
                "detail": row.get("detail"),
                "at": _when(row.get("created_at")),
            }
        )

    for row in findings:
        part = parts.at(row["mpn"])
        if part is None:
            continue
        parts.describe(part, row)
        part["findings"].append(
            {
                "thread_id": row["thread_id"],
                "line_id": row["line_id"],
                "line_name": row["line_name"],
                "rule": row["rule"],
                "slot": row["slot"],
                "verdict": row["verdict"],
                "outcome": row["outcome"],
                "action": row["action"],
                "replacement_mpn": row["replacement_mpn"],
            }
        )

    ordered = sorted(parts.values(), key=_rank)
    return {
        "lines": [dict(line) for line in lines],
        "parts": [_finish(part, facts) for part in ordered[:part_limit]],
        "parts_capped": len(ordered) > part_limit,
        "part_limit": part_limit,
    }


def _rank(part: Mapping[str, Any]) -> tuple[Any, ...]:
    """What a person came to this screen to find, first.

    A retired part is the reason anyone opens memory during an end-of-life, and a part
    something was decided about outranks one that has only ever sat quietly on a board.
    """
    return (
        part["retirement"] is None,
        -len(part["history"]),
        -len(part["findings"]),
        -len(part["used_in"]),
        part["mpn"],
    )


def _finish(part: Mapping[str, Any], facts: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        **part,
        "used_in": sorted(part["used_in"].values(), key=lambda edge: edge["line_name"]),
        "facts": [fact_from(fact) for fact in facts.get(part["mpn"], [])],
    }


def _retirement(row: Row) -> dict[str, Any]:
    return {
        "mpn_line": row.get("mpn_line"),
        "manufacturer": row.get("manufacturer"),
        "effective_date": _when(row.get("effective_date")),
        "effective_date_line": row.get("effective_date_line"),
        "replacement_mpn": row.get("replacement_mpn"),
        "replacement_line": row.get("replacement_line"),
        "reason": row.get("reason"),
        "source": row.get("source"),
        "at": _when(row.get("created_at")),
    }


def _when(value: object) -> str | None:
    """Dates and timestamps as text, because that is what crosses the wire."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def mpns_in(*groups: Iterable[Row], fields: Sequence[str] = ("mpn",)) -> list[str]:
    """Every part number these rows mention, for one bounded read of `part_facts`."""
    found: set[str] = set()
    for group in groups:
        for row in group:
            for field in fields:
                value = row.get(field)
                if isinstance(value, str) and value:
                    found.add(value)
    return sorted(found)
