"""Where the pins are, for the parts we have read a datasheet for.

A board tells us what the *outgoing* part's pins do, because the schematic put a function on
every pad. Nothing tells us what the *incoming* part's pins do. That is a datasheet reading,
it is the difference between a working substitution and a regulator wired backwards, and it
is not something to infer from a package name: SOT-23-5 is a shape, and different parts in
it put ground, enable and output in different places.

So this is a table of readings, each with the line it was read from, and **a part that is
not in it has no board consequence computed**. The screen says so. That is the same rule the
rest of the system runs on — a fact needs a source — and the absence below is the proof it
is being followed: LD1117 publishes its pin connections as a *figure*, and a figure is not
extractable text, so LD1117 is not here.

The land pattern is a separate question and mostly answers itself: a substitute in the same
package keeps the board's own footprint, because the pads it has to land on are already
there. Only a package change needs a footprint chosen out of KiCad's library.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Pinout:
    """What each pad of a part is for, and where that was read."""

    mpn: str
    package: str
    pins: Mapping[str, str]
    source: str

    def __post_init__(self) -> None:
        if not self.pins:
            raise ValueError(f"{self.mpn} has no pins")


SOT223_1117 = {"1": "GND", "2": "VOUT", "3": "VIN"}
"""The 1117 family's SOT-223 assignment. Read separately for each part below, not shared
by assumption — a family that agreed on three pins for thirty years is still three
datasheets."""

PINOUTS: dict[str, Pinout] = {
    part.mpn.casefold(): part
    for part in (
        Pinout(
            mpn="AMS1117-3.3",
            package="SOT-223",
            pins=SOT223_1117,
            source="AMS1117 datasheet, PIN DESCRIPTION: '1 GND/ADJ', '2 VOUT O Output "
            "voltage', '3 VIN I Input supply voltage'",
        ),
        Pinout(
            mpn="NCP1117ST33T3G",
            package="SOT-223",
            pins=SOT223_1117,
            source="onsemi NCP1117/D, PIN CONFIGURATION: 'Pin: 1. Adjust/Ground', "
            "'2 Output', '3 Input', and 'Heatsink tab is connected to Pin 2.'",
        ),
        Pinout(
            mpn="TLV1117LV33DCYR",
            package="SOT-223",
            pins=SOT223_1117,
            source="TI SBVS160C, Table 5-1 Pin Functions: 'IN 3', 'OUT 2, Tab', 'GND 1'",
        ),
        Pinout(
            mpn="ME6211C33M5G-N",
            package="SOT-23-5",
            pins={"1": "VIN", "2": "VSS", "3": "CE", "4": "NC", "5": "VOUT"},
            source="Nanjing Micro One ME6211 datasheet, Pin Configuration, SOT23-5 column: "
            "'1 VIN Power Input, 2 VSS Ground, 3 CE ON/OFF Control, 4 NC No Connect, "
            "5 VOUT Output'",
        ),
    )
}

FOOTPRINTS = {
    "SOT-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
}
"""KiCad's own land patterns, for the packages a substitution here can land in.

Only consulted when the package *changes*. Each of these has hand-solder variants with
larger pads; the machine-assembly pattern is the right default for a board that is already
in production, and a board that used a different variant keeps its own — see `footprint_for`.
"""


class NoPinout(LookupError):
    """No datasheet reading on file for this part, so no board consequence is computed."""

    def __init__(self, mpn: str) -> None:
        super().__init__(
            f"no pin functions are on file for {mpn}. A substitution cannot be placed on a "
            f"board without knowing which of its pins is the input, the output and the "
            f"ground, and that is a datasheet reading rather than something to infer from "
            f"the package."
        )
        self.mpn = mpn


def pinout(mpn: str) -> Pinout:
    found = PINOUTS.get(mpn.strip().casefold())
    if found is None:
        raise NoPinout(mpn)
    return found


def known(mpn: str) -> bool:
    return mpn.strip().casefold() in PINOUTS


def _package_key(package: str) -> str:
    return package.strip().upper().replace(" ", "").replace("_", "-")


_BY_PACKAGE = {_package_key(name): footprint for name, footprint in FOOTPRINTS.items()}


def footprint_for(
    package: str, *, incumbent_package: str, incumbent_footprint: str
) -> str:
    """The land pattern a substitute goes into.

    An unchanged package keeps the board's own footprint, and that is not a shortcut: the
    pads are already there, in whichever variant this design chose, and swapping them for a
    library pattern would report differences the substitution does not cause.
    """
    if _package_key(package) == _package_key(incumbent_package):
        return incumbent_footprint
    wanted = _BY_PACKAGE.get(_package_key(package))
    if wanted is None:
        raise LookupError(
            f"no KiCad land pattern on file for the {package!r} package, so a part in it "
            f"cannot be placed on a board here."
        )
    return wanted
