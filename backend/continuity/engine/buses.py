"""Bus vocabulary and compatibility facts owned by the constraint engine.

Distributor interface fields are free text. A protocol can reach the engine under a
vendor's transliteration, a conventional abbreviation, or a differently cased spelling;
the rule layer must not turn those presentation differences into electrical conflicts.

The table is deliberately local to ``engine``. It is a constraint-engine fact rather
than a catalogue taxonomy, so it remains deterministic and imports no other module.
"""

from __future__ import annotations


# payload spelling → engine's single protocol name
_ALIASES: dict[str, str] = {
    "SINGLE BUS": "1-WIRE",
    "SINGLE_BUS": "1-WIRE",
    "ONE-WIRE": "1-WIRE",
    "ONEWIRE": "1-WIRE",
    "TWI": "I2C",
    "IIC": "I2C",
    "I²C": "I2C",
}


def canonical_bus(bus: str) -> str:
    """Return a case- and surrounding-whitespace-insensitive bus name.

    Unknown names are still folded to uppercase. This gives equality checks a stable
    representation without falsely claiming that an unfamiliar protocol is known.
    """
    name = bus.strip().upper()
    return _ALIASES.get(name, name)


# peripheral bus → master buses that can safely host it
_MASTER_COMPATIBILITY: dict[str, frozenset[str]] = {
    "SMBUS": frozenset({"I2C"}),
}
"""Directed, not symmetric: SMBus devices work on I²C masters, but I²C devices are
not reliably safe on SMBus-only masters. Equality is handled separately below."""


def master_satisfies_bus(peripheral_bus: str, master_bus: str) -> bool:
    """Whether one peripheral interface is usable with one offered master interface."""
    peripheral = canonical_bus(peripheral_bus)
    master = canonical_bus(master_bus)
    return peripheral == master or master in _MASTER_COMPATIBILITY.get(peripheral, ())
