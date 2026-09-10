"""What a product line states about the conditions it runs under.

## Why this is not part of `Requirements`

`Requirements` is what one run was asked for, parsed out of a brief and thrown away with
the run. A product line's ambient, its copper and its signed rail load outlive every run
against it: they describe a board that already exists and already ships. They are stored
against the line, at a revision, and they reach the engine from there.

## Why every field but the ambient is optional, and why unstated means untouched

A profile is a set of *statements*, not a complete picture of a board. A line that has
recorded its enclosure ambient and nothing else must not, by being applied, erase the
mounting note or the supply basis a board already carried. So `applied_to` writes only
the fields the profile actually states, which is the same rule the brief set for
`mounting` and the same reason `Rail.i_load` exists at all: a stated number wins, and
silence is not a number.

That is sharpest on rail voltage. The `vin` rail has no part behind it — 5 V on the
gateway and 12 V on the cabinet controller is a fact about the product, and it is the
whole reason a 5.5 V candidate fails one line and not the others. The 3V3 rail's voltage
comes from the regulator's datasheet instead, and a profile that restated it would
overwrite each candidate's own output with whatever number was stored the day the line
was entered.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Mapping, Sequence

from .engine.models import Board, PartSpec, Rail, Requirements, Slot


@dataclass(frozen=True)
class RailProfile:
    """One rail of a product line's board, as the line records it.

    `source` and `members` were left out when this was written, on the reasoning that
    topology comes from the BOM rather than from operating conditions. That was right for
    a *design* run, whose rails the planner lays out, and wrong for a stored line: a BOM is
    a list of parts and refdes, and nothing in it says which part feeds which net. Without
    them a stored line cannot be turned into a board at all, which is what item 12's matrix
    needs — and the gateway's 3V3 rail being fed by U1 is as much a fact about the shipping
    product as its enclosure ambient is.
    """

    voltage: float | None = None
    i_limit: float | None = None
    basis: str | None = None
    i_load: float | None = None
    i_load_basis: str | None = None

    source: str | None = None
    """The refdes that produces this rail. `None` for a rail fed from outside the board."""

    members: tuple[str, ...] = ()
    """The refdes drawing from it. The producing part is not a member of its own output."""

    KEYS: ClassVar[frozenset[str]] = frozenset(
        ("voltage", "i_limit", "basis", "i_load", "i_load_basis", "source", "members")
    )

    def stated(self) -> dict[str, Any]:
        """Only what this profile actually says, for `replace` onto an existing rail.

        `members` is excluded when empty rather than when `None`: an empty tuple is how a
        profile says nothing about who draws from a rail, and writing it over a design
        run's membership would empty a rail the planner had populated.
        """
        stated = {key: value for key in self.KEYS if (value := getattr(self, key)) is not None}
        if not stated.get("members"):
            stated.pop("members", None)
        return stated

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "RailProfile":
        unknown = set(value) - cls.KEYS
        if unknown:
            raise ValueError(f"unknown rail profile keys: {sorted(unknown)}")
        fields = dict(value)
        if "members" in fields:
            fields["members"] = tuple(fields["members"] or ())
        return cls(**fields)

    def to_json(self) -> dict[str, Any]:
        stored = {key: getattr(self, key) for key in sorted(self.KEYS)}
        stored["members"] = list(self.members)
        return stored


@dataclass(frozen=True)
class OperatingProfile:
    """One product line's stored operating conditions, as a revision recorded them."""

    ambient_c: int
    ambient_source: str
    """Never optional, together. An ambient with no stated source is the silent 25 °C
    default this project already removed once, wearing a database row as a disguise."""

    mounting: str | None = None
    rails: Mapping[str, RailProfile] = field(default_factory=dict)

    build_quantity: int | None = None
    """How many of this product the company needs to be able to build.

    A property of the product, not of a review. `availability` fails below
    `Requirements.min_stock`, which defaults to 100, so on a product shipping in volume a
    part with four figures of stock is not a part you can buy — and that is procurement's
    judgement to make rather than a wall. Unstated leaves the default, which is right for a
    product line nobody has told us the volume of.
    """

    build_quantity_source: str | None = None
    """Where the figure came from, in the company's own words.

    The same rule the ambient is held to: a number with no stated source is a silent
    default wearing a database row as a disguise, and this one decides whether a desk is
    asked a question.
    """

    annual_volume: int | None = None
    """How many units of this product the company plans to make each year.

    Unlike `build_quantity`, this does not decide whether stock clears a review. It gives
    the recurring half of a change request its one stated basis.
    """

    annual_volume_source: str | None = None
    """Where the annual figure came from, in the company's own words."""

    KEYS: ClassVar[frozenset[str]] = frozenset(
        (
            "ambient_c",
            "ambient_source",
            "mounting",
            "rails",
            "build_quantity",
            "build_quantity_source",
            "annual_volume",
            "annual_volume_source",
        )
    )

    def to_requirements(self, base: Requirements) -> Requirements:
        """`base` with this profile's statements over it. Unstated fields survive."""
        changes: dict[str, Any] = {
            "ambient_c": self.ambient_c,
            "ambient_source": self.ambient_source,
        }
        if self.mounting is not None:
            changes["mounting"] = self.mounting
        if self.build_quantity is not None:
            changes["min_stock"] = self.build_quantity
        return replace(base, **changes)

    def applied_to(self, board: Board) -> Board:
        """A new board carrying this line's conditions. The original is untouched.

        A rail the profile names and the board does not have is an error rather than a
        skip. A stored 45 °C ambient or a signed 420 mA load that reaches no verdict is
        invisible in exactly the way the five coverage labels exist to prevent: the board
        would go green having never been checked against the condition that was stored.
        """
        missing = set(self.rails) - set(board.rails)
        if missing:
            raise ValueError(f"profile names rails absent from board: {sorted(missing)}")

        rails: dict[str, Rail] = {
            rail_id: replace(rail, **self.rails[rail_id].stated()) if rail_id in self.rails else rail
            for rail_id, rail in board.rails.items()
        }
        return replace(
            board, requirements=self.to_requirements(board.requirements), rails=rails
        )

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "OperatingProfile":
        """Strict about unknown keys, in both directions.

        A key written by a newer build and ignored by an older one is a stored operating
        condition that never reached a check, and the board still goes green.
        """
        unknown = set(value) - cls.KEYS
        if unknown:
            raise ValueError(f"unknown operating profile keys: {sorted(unknown)}")
        return cls(
            ambient_c=value["ambient_c"],
            ambient_source=value["ambient_source"],
            mounting=value.get("mounting"),
            build_quantity=value.get("build_quantity"),
            build_quantity_source=value.get("build_quantity_source"),
            annual_volume=value.get("annual_volume"),
            annual_volume_source=value.get("annual_volume_source"),
            rails={
                rail_id: RailProfile.from_json(rail)
                for rail_id, rail in dict(value.get("rails") or {}).items()
            },
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "ambient_c": self.ambient_c,
            "ambient_source": self.ambient_source,
            "mounting": self.mounting,
            "build_quantity": self.build_quantity,
            "build_quantity_source": self.build_quantity_source,
            "annual_volume": self.annual_volume,
            "annual_volume_source": self.annual_volume_source,
            "rails": {rail_id: rail.to_json() for rail_id, rail in self.rails.items()},
        }


def board_from(
    profile: "OperatingProfile",
    bom: Sequence[Mapping[str, Any]],
    specs: Mapping[str, PartSpec],
) -> Board:
    """A board the engine can check, built from what a product line has stored.

    This is the other direction from everything Continuity did first. A design run invents
    a board and then sources it; here the board already exists, ships, and is described by
    its bill of materials and its operating profile — so the whole of it comes out of the
    database and nothing is inferred from a brief.

    **Rows the BOM marks unpopulated are left out.** A do-not-populate line is on the
    document and not on the board, and checking a part that is not fitted would report
    conflicts against a circuit nobody built.

    **A row whose part could not be resolved is left out too, and that is a real limit.**
    The board is then checked without it, so a rail load derived from summing parts would
    under-count — which is exactly why `Rail.i_load` exists and why a product line states
    its own load rather than having one derived. A line with no stated load and an
    unresolved part is checked on a floor, and the verdicts say so.
    """
    slots: dict[str, Slot] = {}
    sources = {rail.source for rail in profile.rails.values() if rail.source}

    for row in bom:
        refdes = row["refdes"]
        spec = specs.get(row["mpn"])
        if not row.get("populated", True) or spec is None:
            continue
        slots[refdes] = Slot(
            id=refdes,
            label=f"{refdes} · {spec.description or spec.mpn}",
            # Never read by any rule — `evaluate` does not look at it. It steers policy
            # and the screen, so it is derived here rather than stored and kept in sync.
            tier="power" if refdes in sources else "core",
            status="pass",
            part=spec,
        )

    def voltage_of(rail: RailProfile) -> float:
        """A stated voltage wins; otherwise the part that makes the rail decides it.

        A rail fed by a regulator takes its voltage from that regulator's datasheet, which
        is why a profile does not store it — storing 3.3 would overwrite each candidate's
        own output with whatever number was true the day the line was entered, and the
        matrix exists precisely to put different regulators in that slot. An external
        supply has no part behind it, so there the profile is the only source and a
        missing value is a gap in the stored line rather than something to invent.
        """
        if rail.voltage is not None:
            return rail.voltage
        source = specs.get(next((r["mpn"] for r in bom if r["refdes"] == rail.source), ""))
        stated = source.vout if source is not None else None
        return stated if stated is not None else 0.0

    rails = {
        rail_id: Rail(
            id=rail_id,
            voltage=voltage_of(rail),
            source=rail.source,
            members=tuple(m for m in rail.members if m in slots),
            i_limit=rail.i_limit,
            i_load=rail.i_load,
            i_load_basis=rail.i_load_basis,
            basis=rail.basis,
        )
        for rail_id, rail in profile.rails.items()
    }

    return Board(
        requirements=profile.to_requirements(Requirements()),
        slots=slots,
        rails=rails,
    )
