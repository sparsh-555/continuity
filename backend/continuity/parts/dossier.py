"""The board-independent facts a part can carry across deployments.

Distributor listings are current but incomplete. These facts preserve measurements and
properties learned on an earlier run, while the whitelist keeps a board-specific verdict
from ever being mistaken for a property of the part itself.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

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
        "cout_min_uf",
        "cout_dielectrics",
        "capacitance_uf",
        "dielectric",
        "vout_accuracy_pct",
        "load_regulation_pct",
        "esr_stable_from_ohms",
        "esr_stable_to_ohms",
        "esr_ohms",
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

`vout_accuracy_pct` and `load_regulation_pct` joined on 11 September for the same reason,
and their absence had the same shape of consequence. P2 built `signal_integrity` to stack
them, the rule was correct, and it declined on every real board because the figures could
not survive this far — so the change request still admitted it could not check something.
The rule was tested against fixture parts that carried the numbers, which is why the tests
were green while the product was not.

The three `esr_*` fields are the same mistake in the rule beside it, found by looking for the
class rather than the instance: `output_capacitor_stability` compares a capacitor's published
ESR against the window its regulator publishes, both readings are recorded here, and neither
could survive this far — so the comparison could not run on any board the company had
described. It does not bite today only because the demo's capacitor publishes no ESR at all,
which is exactly the kind of silence that hides a dead check.
"""

ENGINEERING_FIELDS: frozenset[str] = frozenset(
    {
        "theta_ja", "t_j_max", "temp_min", "temp_max",
        "vmin", "vmax", "vout_min", "vout_max", "i_max",
        "package", "topology", "synchronous", "efficiency",
        "cout_min_uf", "cout_dielectrics",
        "vout_accuracy_pct", "load_regulation_pct",
        "esr_stable_from_ohms", "esr_stable_to_ohms", "esr_ohms",
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


NO_SOURCE = "source unavailable"
"""What stands in when a reading has no quotable line.

Named rather than repeated, because anything that has to tell a quotation apart from this
marker would otherwise be matching a sentence by hand. `api/recall.fact_from` does exactly
that, and got it wrong on screen for as long as the string lived in two places.
"""


def verified_source(source: str | None) -> str:
    return f"{VERIFIED_PREFIX}{source or NO_SOURCE}"


def is_verified(source: str | None) -> bool:
    return bool(source) and source.startswith(VERIFIED_PREFIX)

DOSSIER_PROVENANCE_PREFIX = DOSSIER_SOURCE
"""One spelling, owned by the engine, because `rules` and `models` match on it too."""

_FLOAT_FIELDS = frozenset(
    {
        "theta_ja", "efficiency", "temp_min", "temp_max", "t_j_max",
        "vmin", "vmax", "vout_min", "vout_max", "i_max",
        "cout_min_uf", "capacitance_uf",
        "vout_accuracy_pct", "load_regulation_pct",
        "esr_stable_from_ohms", "esr_stable_to_ohms", "esr_ohms",
    }
)
"""Which stored facts decode back into numbers.

**Every numeric field on `PartSpec` belongs here, without exception.** This set answers one
question — what type does the stored string turn back into — and it is not the set that
decides whether a recorded reading outranks a live listing. That is `ENGINEERING_FIELDS`,
and confusing the two cost a live 500: `capacitance_uf` was kept out of here on the entirely
correct grounds that a distributor states an MLCC's value accurately, which is an argument
about precedence and none at all about type. A recorded 22 µF came back as `"22.0"`,
`capacitor_requirements` summed a str into an int, and `/lines/{id}/check` failed on every
seeded product line — the call the whole product line page is painted from."""

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
        if isinstance(value, tuple):
            if not value:
                # Empty means the datasheet named none, which is not the same as a
                # requirement of nothing, and storing it would turn a silence into a claim.
                continue
            value = ", ".join(str(item) for item in value)
        if not _is_stated(value):
            continue
        # The two fields whose evidence sentence lives on the part rather than in its
        # provenance map, because both were read out of a datasheet by hand.
        if field == "theta_ja":
            source = part.theta_ja_source_line
        elif field in ("cout_min_uf", "cout_dielectrics"):
            source = part.cout_source_line
        elif field in ("esr_stable_from_ohms", "esr_stable_to_ohms"):
            # One sentence on the part covers the window's two ends, the way
            # `cout_source_line` covers the requirement and its dielectrics.
            source = part.esr_source_line
        else:
            source = part.provenance.get(field)
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
    if field == "cout_dielectrics":
        named = tuple(item.strip() for item in value.split(",") if item.strip())
        return named or None
    return value.strip() or None


def provenance(source: str | None) -> str:
    """Make a carried-forward fact visibly distinct from this run's live payload."""
    return f"{DOSSIER_PROVENANCE_PREFIX} ({source or NO_SOURCE})"


def original_source(value: str | None) -> str | None:
    """Avoid nesting the dossier label when a carried-forward fact is refreshed."""
    prefix = f"{DOSSIER_PROVENANCE_PREFIX} ("
    if value is not None and value.startswith(prefix) and value.endswith(")"):
        return value[len(prefix) : -1]
    return value


def part_from_facts(
    mpn: str, manufacturer: str | None, facts: Sequence[Mapping[str, Any]]
) -> PartSpec | None:
    """A part built from the readings this company recorded, with no distributor involved.

    The fallback for a product line that already ships. A distributor is a network call and
    a venue's network is not ours, and a line whose parts cannot be resolved cannot be
    checked — which put a grey node beside two green ones on the page a demo opens with.

    These readings are **better evidence than a listing**, not worse: they were read off the
    manufacturer's own datasheets and are exactly what `set_dossier_lookup` exists to let
    override a parametric table. What they lack is the commercial half — stock, price, lead
    time, lifecycle — which no datasheet knows and no rule here needs.

    `None` when nothing was recorded, because a part with no facts is not a part.
    """
    fields: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for fact in facts:
        field = str(fact.get("field") or "")
        value = value_from_text(field, str(fact.get("value") or ""))
        if value is not None:
            fields[field] = value
            # **Kept, not stamped over.** The stored reading carries the line it was read
            # from, and this used to replace every one of them with the bare dossier label —
            # so a change request showed *vmax (dossier) 20.0* against nothing, and the
            # source line PARTS.md promises for every figure stopped at the door. The
            # `normalize` path has always carried it; this one is the fallback a product
            # line's own parts are built by, which is the path most evidence goes through.
            sources[field] = provenance(fact.get("source"))
    if not fields:
        return None
    return PartSpec(
        mpn=mpn,
        manufacturer=manufacturer or "",
        description=f"{mpn}, from readings this company recorded",
        category=fields.pop("category", "") or "",
        provenance=sources,
        **fields,
    )
