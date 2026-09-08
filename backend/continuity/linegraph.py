"""The power tree of a product line that already exists, drawn from what it states.

Continuity's graph has always come out of a *design run*: the planner invents slots, sourcing
fills them, and the edges are whatever the plan said. A product line that already ships has
no plan and no run. It has a bill of materials and an operating profile, and the profile's
rails carry `source` and `members` — which is a power tree, written down by the person who
described the product.

So this reads that tree back out. The seeded Gateway states `vin` at 5 V feeding `u1`, and
`3v3` sourced from `u1` feeding `u2` and `c1`, and that is exactly the picture: supply,
regulator, loads.

## What it is not

**It is not a netlist.** A rail says which parts it feeds, so every edge here is a power
edge. The data connections between an MCU and its sensors are in the schematic, and nothing
here has read one. The screen says so rather than drawing a graph that looks complete.

**Nothing is checked.** Every slot comes back `unchecked`, which is the truthful status for a
part that is fitted and shipping and that no rule has looked at in this session. A run is
what turns those green or red.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SUPPLY_ID = "__supply"

POWER_PREFIXES = ("u",)
PASSIVE_PREFIXES = ("c", "r", "l", "d", "f")

REGULATOR_WORDS = ("regulator", "ldo", "converter", "buck", "boost", "pmic")
CORE_WORDS = ("mcu", "microcontroller", "module", "processor", "soc", "wifi", "ble")
PASSIVE_WORDS = ("capacitor", "resistor", "inductor", "ferrite", "diode")


def _tier(refdes: str, description: str, *, is_source: bool) -> str:
    """Which band of the graph a part sits in.

    The rail structure decides before any word does: a part that *sources* a rail is the
    power tier whatever its description says, because that is what it is doing on this
    board.
    """
    if is_source:
        return "power"
    text = description.casefold()
    if any(word in text for word in REGULATOR_WORDS):
        return "power"
    if any(word in text for word in CORE_WORDS):
        return "core"
    if any(word in text for word in PASSIVE_WORDS):
        return "passives"
    prefix = refdes[:1].casefold()
    if prefix in PASSIVE_PREFIXES:
        return "passives"
    if prefix in POWER_PREFIXES:
        return "core"
    return "peripherals"


def _rail_label(name: str, rail: Mapping[str, Any]) -> str:
    voltage = rail.get("voltage")
    if isinstance(voltage, (int, float)):
        return f"{voltage:g}V"
    return name.upper()


def _supply_rail(rails: Mapping[str, Mapping[str, Any]]) -> tuple[str, Mapping[str, Any]] | None:
    """The rail nothing on the board makes, which is where the board's power comes from.

    A rail with no `source` is fed from outside — a connector, a battery, a bench supply.
    Where a product states more than one, the one carrying the most volts is the input and
    the others are unstated intermediates; taking the highest is a guess, so it is the only
    guess made here and it is made in one place.
    """
    external = [
        (name, rail)
        for name, rail in rails.items()
        if not rail.get("source") and rail.get("members")
    ]
    if not external:
        return None
    return max(
        external,
        key=lambda pair: pair[1].get("voltage") if isinstance(pair[1].get("voltage"), (int, float)) else -1.0,
    )


@dataclass(frozen=True)
class LineGraph:
    """The shape the workspace already renders, built from stored data alone."""

    slots: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    supply: dict[str, Any] | None

    def to_json(self) -> dict[str, Any]:
        return {
            "slots": list(self.slots),
            "edges": list(self.edges),
            "supply": self.supply,
        }


def graph_from(
    profile: Mapping[str, Any] | None, bom: Sequence[Mapping[str, Any]]
) -> LineGraph:
    """A product line's power tree, or as much of one as it has described.

    Everything is derived from stored fields and nothing is fetched. A line with no profile
    still gets its parts as unconnected nodes, which is the honest picture of a bill of
    materials nobody has described the power tree of yet.
    """
    rails: Mapping[str, Mapping[str, Any]] = (profile or {}).get("rails") or {}
    sources = {
        str(rail["source"]) for rail in rails.values() if rail.get("source")
    }

    fitted = [row for row in bom if row.get("populated", True) and row.get("refdes")]
    slots = []
    for row in fitted:
        refdes = str(row["refdes"])
        mpn = row.get("mpn") or ""
        description = " ".join(
            str(row.get(field) or "") for field in ("description", "category", "mpn")
        )
        slots.append(
            {
                "id": refdes,
                "label": refdes.upper(),
                "tier": _tier(refdes, description, is_source=refdes in sources),
                "pinned": True,
                # Fitted, shipping, and looked at by no rule in this session. A run is what
                # turns these green or red, and claiming `pass` before one would be the
                # system asserting a verdict nobody produced.
                "status": "unchecked",
                "part": {
                    "mpn": mpn,
                    "manufacturer": row.get("manufacturer"),
                    "package": row.get("footprint"),
                },
                "constraint": None,
                "repair_count": 0,
            }
        )

    known = {slot["id"] for slot in slots}
    supply_pair = _supply_rail(rails)
    supply_name = supply_pair[0] if supply_pair else None

    edges = []
    for name, rail in rails.items():
        source = rail.get("source")
        origin = str(source) if source else (SUPPLY_ID if name == supply_name else None)
        if origin is None:
            continue
        if origin != SUPPLY_ID and origin not in known:
            continue
        for member in rail.get("members") or []:
            target = str(member)
            if target not in known or target == origin:
                continue
            edges.append(
                {
                    "id": f"{name}-{target}",
                    "from": origin,
                    "to": target,
                    "label": _rail_label(name, rail),
                    "kind": "power",
                    # The rail says these are connected. No rule has run on the connection,
                    # and `unchecked` is the vocabulary the client already has for that.
                    "status": "unchecked",
                }
            )

    supply = None
    if supply_pair:
        name, rail = supply_pair
        voltage = rail.get("voltage")
        supply = {
            "id": SUPPLY_ID,
            "label": rail.get("basis") or f"{name.upper()} input",
            "voltage": voltage if isinstance(voltage, (int, float)) else None,
        }

    return LineGraph(slots=tuple(slots), edges=tuple(edges), supply=supply)
