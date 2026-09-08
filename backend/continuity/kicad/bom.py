"""A bill of materials, out of the schematic, by asking KiCad for it.

`kicad-cli sch export bom` is the supported path and it is stable across 8 and 9. We ask
for one row per reference — no grouping — because everything downstream is keyed by
reference designator: which board position carries the retired part, and which position a
substitute would land in.

## Which column is the part number

There is no standard. A schematic states `Value`, which on a regulator is usually the part
number and on a capacitor is `100n`; a design meant for manufacture usually carries a real
field, but it may be called `MPN`, `Manufacturer Part Number`, `P/N` or half a dozen other
things, and plenty of projects carry only a distributor code.

So the field is **chosen and then named**. `Bill.mpn_field` says which column the part
numbers came from, and it reaches the screen, because "we read your MPN column" and "we
guessed from the Value field" are different claims about the same table and the reader is
entitled to know which one they are looking at.

A field KiCad does not find comes back as an empty column rather than an error, which is
what makes asking for all the candidates at once safe.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .project import Project
from .runner import Runner

PART_NUMBER_FIELDS = (
    "MPN",
    "Manufacturer Part Number",
    "Manufacturer_Part_Number",
    "Part Number",
    "PartNumber",
    "P/N",
    "PN",
)
"""Field names real projects use for a manufacturer part number, in the order preferred."""

DISTRIBUTOR_FIELDS = ("LCSC", "JLCPCB", "LCSC Part", "LCSC#")
"""A distributor code is not a part number, but it resolves to one exactly."""

VALUE_FIELD = "Value"

_EXPORTED = ("Reference", VALUE_FIELD, "Footprint", *PART_NUMBER_FIELDS, *DISTRIBUTOR_FIELDS)


@dataclass(frozen=True)
class Row:
    """One placed part, as the schematic states it."""

    refdes: str
    value: str
    footprint: str
    mpn: str | None
    distributor_code: str | None


@dataclass(frozen=True)
class Bill:
    rows: tuple[Row, ...]
    mpn_field: str
    """The column the part numbers were read from. `Value` means no real field existed."""

    @property
    def by_refdes(self) -> dict[str, Row]:
        return {row.refdes: row for row in self.rows}

    def carrying(self, mpn: str) -> tuple[Row, ...]:
        wanted = mpn.strip().casefold()
        return tuple(row for row in self.rows if (row.mpn or "").strip().casefold() == wanted)


def _chosen_field(records: list[dict[str, str]]) -> str:
    """The first candidate column that is actually populated, else `Value`.

    "Actually populated" rather than "present": every candidate is present, because we
    asked for all of them and KiCad fills the ones it does not know with blanks.
    """
    for field in PART_NUMBER_FIELDS:
        if any((record.get(field) or "").strip() for record in records):
            return field
    return VALUE_FIELD


def _first_populated(record: dict[str, str], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = (record.get(field) or "").strip()
        if value:
            return value
    return None


def read(project: Project, runner: Runner, *, timeout: float = 300.0) -> Bill:
    """Export and read the bill of materials for a project."""
    output = Path("kicad-bom.csv")
    runner.cli_run(
        [
            "sch",
            "export",
            "bom",
            "-o",
            str(output),
            "--fields",
            ",".join(_EXPORTED),
            "--labels",
            ",".join(_EXPORTED),
            "--sort-field",
            "Reference",
            "--exclude-dnp",
            project.schematic_name,
        ],
        workdir=project.root,
        timeout=timeout,
    )
    return parse((project.root / output).read_text(encoding="utf-8"))


def parse(text: str) -> Bill:
    records = list(csv.DictReader(text.splitlines()))
    field = _chosen_field(records)
    rows = []
    for record in records:
        refdes = (record.get("Reference") or "").strip()
        if not refdes:
            continue
        rows.append(
            Row(
                refdes=refdes,
                value=(record.get(VALUE_FIELD) or "").strip(),
                footprint=(record.get("Footprint") or "").strip(),
                mpn=(record.get(field) or "").strip() or None,
                distributor_code=_first_populated(record, DISTRIBUTOR_FIELDS),
            )
        )
    return Bill(rows=tuple(rows), mpn_field=field)
