"""The board-independent facts a part can carry across deployments.

Distributor listings are current but incomplete. These facts preserve measurements and
properties learned on an earlier run, while the whitelist keeps a board-specific verdict
from ever being mistaken for a property of the part itself.
"""

from __future__ import annotations

import math
from typing import Any

from ..engine.models import DOSSIER_SOURCE, PartSpec

DOSSIER_FIELDS: frozenset[str] = frozenset(
    {
        "package",
        "theta_ja",
        "topology",
        "synchronous",
        "efficiency",
        "temp_min",
        "temp_max",
        "t_j_max",
        "vmin",
        "vmax",
        "vout_min",
        "vout_max",
        "i_max",
    }
)
"""Properties that remain true for this MPN on every board.

`t_j_max` belongs here for the same reason `theta_ja` does, and its absence had teeth: the
thermal rule falls back to `temp_max` when no junction limit is known, and those are two
different quantities — onsemi's NCP1117 is graded to 125 °C *ambient* and rated to 150 °C
at the *junction*. A stored dossier that carried the first and not the second would check
every board against a limit 25 °C below the one the datasheet states, and the verdict
would look entirely reasonable.

The electrical limits are here so that a figure read off a datasheet can be *kept*. Until
it was, they could only ever come from a distributor's parametric table — see
`ENGINEERING_FIELDS` for what that cost.
"""

ENGINEERING_FIELDS: frozenset[str] = frozenset(
    {
        "theta_ja", "t_j_max", "temp_min", "temp_max",
        "vmin", "vmax", "vout_min", "vout_max", "i_max",
        "package", "topology", "synchronous", "efficiency",
    }
)
"""Facts about the part, where the manufacturer's datasheet is the specification of record.

A distributor's parametric table is a hand-built index over somebody else's document. It
is a convenience and nobody warrants it — LCSC's own terms say they are not the
manufacturer and pass through manufacturer warranties only — and it is wrong often enough
to matter. JLCPCB lists `TLV1117LV33DCYR` at *Voltage - Supply 12 V*, with a link to TI's
datasheet attached to that very attribute; TI's document says 2 V to 5.5 V recommended and
6 V absolute maximum. Twelve volts is double the voltage at which the part dies, and the
number was almost certainly copied from the ordinary 1117 family — which is exactly what
the "LV" in the part number exists to distinguish.

So a **verified** reading beats the listing on these fields. Everything else — stock,
price, lead time, lifecycle, what is actually on the reel — is the opposite way round: the
distributor is authoritative and a datasheet cannot know any of it. `normalize`'s "a live
listing is the buying truth" was always right about *buying*, and was simply being applied
to fields it was not written for.
"""

VERIFIED_PREFIX = "datasheet — "
"""Marks a fact read from the manufacturer's document rather than copied from a listing.

An explicit marker rather than a guess at the shape of a source string, and it is what
decides whether a stored fact may override this run's listing. Facts stored without it
keep the older, weaker behaviour of filling a blank only, so nothing already in the
database changes meaning because this arrived.
"""


def verified_source(source: str | None) -> str:
    return f"{VERIFIED_PREFIX}{source or 'source unavailable'}"


def is_verified(source: str | None) -> bool:
    return bool(source) and source.startswith(VERIFIED_PREFIX)

DOSSIER_PROVENANCE_PREFIX = DOSSIER_SOURCE
"""One spelling, owned by the engine, because `rules` and `models` match on it too."""

_FLOAT_FIELDS = frozenset(
    {
        "theta_ja", "efficiency", "temp_min", "temp_max", "t_j_max",
        "vmin", "vmax", "vout_min", "vout_max", "i_max",
    }
)

NOT_STATED = frozenset({"-", "--", "–", "—", "n/a", "na", "none", "null", "tbd", "?"})
"""Values a listing uses to mean "we did not say", which must never become a fact.

JLCPCB publishes a bare `-` for an unknown package. Nothing upstream treats that as
absent, so it reaches here as an ordinary string — and this is the one place where a
transient blank would become *durable* and then gap-fill a later run's genuinely empty
field with a dash. Refuse it at the boundary rather than teaching every reader about it.
"""


def _is_stated(value: object) -> bool:
    return not (isinstance(value, str) and value.strip().casefold() in NOT_STATED)


def facts_from_part(
    part: PartSpec, *, verified: bool = False
) -> list[tuple[str, str, str, str | None]]:
    """(mpn, field, value, source) for every whitelisted field this part actually carries.

    `verified=True` asserts these were read from the manufacturer's datasheet rather than
    copied from a distributor's parametric table, which lets them override a listing on
    `ENGINEERING_FIELDS`. It is a claim about provenance, so only a caller that actually
    knows should make it — a run recording what it happened to source does not.
    """
    facts: list[tuple[str, str, str, str | None]] = []
    for field in sorted(DOSSIER_FIELDS):
        value = getattr(part, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if not _is_stated(value):
            continue
        source = part.theta_ja_source_line if field == "theta_ja" else part.provenance.get(field)
        source = original_source(source)
        if verified and field in ENGINEERING_FIELDS:
            source = verified_source(source)
        facts.append((part.mpn, field, repr(value) if isinstance(value, float) else str(value), source))
    return facts


def value_from_text(field: str, value: str) -> Any | None:
    """Decode a stored fact only when it still has the declared `PartSpec` type."""
    if field not in DOSSIER_FIELDS or not value:
        return None
    if field in _FLOAT_FIELDS:
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    if field == "synchronous":
        return {"True": True, "False": False}.get(value)
    return value.strip() or None


def provenance(source: str | None) -> str:
    """Make a carried-forward fact visibly distinct from this run's live payload."""
    return f"{DOSSIER_PROVENANCE_PREFIX} ({source or 'source unavailable'})"


def original_source(value: str | None) -> str | None:
    """Avoid nesting the dossier label when a carried-forward fact is refreshed."""
    prefix = f"{DOSSIER_PROVENANCE_PREFIX} ("
    if value is not None and value.startswith(prefix) and value.endswith(")"):
        return value[len(prefix) : -1]
    return value
