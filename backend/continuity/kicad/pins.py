"""What a pin is for, across the names different manufacturers give it.

A placed footprint carries a function on every pad — `VI`, `VO`, `GND` — because the
schematic put it there. A library footprint carries none: it is a shape, and the pins mean
whatever the symbol connected to them meant. So carrying a net from the old package to the
new one means matching *functions*, and the names do not agree: one datasheet says `VI`,
the next `VIN`, the next `IN`.

This normalises the handful that matter and **refuses to guess the rest**. A pad whose
function is not recognised is reported as unmatched rather than wired to whatever looked
close, because a regulator with its input and output swapped is a destroyed board, and it
is exactly the kind of mistake that reads as plausible in a diff.
"""

from __future__ import annotations

INPUT = "input"
OUTPUT = "output"
GROUND = "ground"
ENABLE = "enable"
ADJUST = "adjust"
NOT_CONNECTED = "not connected"

_NAMES = {
    INPUT: ("VI", "VIN", "IN", "V_IN", "VCC", "VDD"),
    OUTPUT: ("VO", "VOUT", "OUT", "V_OUT"),
    GROUND: ("GND", "VSS", "GROUND", "AGND", "DGND"),
    ENABLE: ("EN", "ENABLE", "CE", "SHDN"),
    ADJUST: ("ADJ", "FB", "FEEDBACK"),
    NOT_CONNECTED: ("NC", "N/C", "NOCONNECT", "NO CONNECT"),
}

_BY_NAME = {
    name.replace("_", "").replace("/", "").replace(" ", "").casefold(): role
    for role, names in _NAMES.items()
    for name in names
}


def role_of(function: str | None) -> str | None:
    """The role a pin function names, or `None` when it is not one we recognise."""
    if not function:
        return None
    return _BY_NAME.get(function.replace("_", "").replace("/", "").replace(" ", "").casefold())
