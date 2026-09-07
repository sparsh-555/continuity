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
from typing import Any, ClassVar, Mapping

from .engine.models import Board, Rail, Requirements


@dataclass(frozen=True)
class RailProfile:
    """The fields of `Rail` a product line states about itself.

    `source` and `members` are deliberately absent: they describe the board's topology,
    which comes from the BOM, not from the conditions the product operates under.
    """

    voltage: float | None = None
    i_limit: float | None = None
    basis: str | None = None
    i_load: float | None = None
    i_load_basis: str | None = None

    KEYS: ClassVar[frozenset[str]] = frozenset(
        ("voltage", "i_limit", "basis", "i_load", "i_load_basis")
    )

    def stated(self) -> dict[str, Any]:
        """Only what this profile actually says, for `replace` onto an existing rail."""
        return {key: value for key in self.KEYS if (value := getattr(self, key)) is not None}

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "RailProfile":
        unknown = set(value) - cls.KEYS
        if unknown:
            raise ValueError(f"unknown rail profile keys: {sorted(unknown)}")
        return cls(**dict(value))

    def to_json(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in sorted(self.KEYS)}


@dataclass(frozen=True)
class OperatingProfile:
    """One product line's stored operating conditions, as a revision recorded them."""

    ambient_c: int
    ambient_source: str
    """Never optional, together. An ambient with no stated source is the silent 25 °C
    default this project already removed once, wearing a database row as a disguise."""

    mounting: str | None = None
    rails: Mapping[str, RailProfile] = field(default_factory=dict)

    KEYS: ClassVar[frozenset[str]] = frozenset(
        ("ambient_c", "ambient_source", "mounting", "rails")
    )

    def to_requirements(self, base: Requirements) -> Requirements:
        """`base` with this profile's statements over it. Unstated fields survive."""
        changes: dict[str, Any] = {
            "ambient_c": self.ambient_c,
            "ambient_source": self.ambient_source,
        }
        if self.mounting is not None:
            changes["mounting"] = self.mounting
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
            "rails": {rail_id: rail.to_json() for rail_id, rail in self.rails.items()},
        }
