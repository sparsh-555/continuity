"""The company the demo happens inside.

    ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo
    ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo --reset

Five product lines, two people, and the two standing lists — everything Scenario B needs to
be told, and none of it invented at the moment of telling. **The demo does not exist without
this**, which is why it is a script in `tools/` under test rather than a fixture nobody runs.

## What the shape of it is doing

Three of the five lines carry AMS1117-3.3, so a notice about that part reaches three
products and leaves two alone — exposure returning *everything* would prove nothing about
exposure. The three that carry it run at 25 °C, 45 °C and 55 °C on 5 V, 5 V and 12 V, which
is what makes one recommendation right for one of them and wrong for another.

**LD1117S33 is deliberately absent from the AML.** It is the one candidate that clears every
board thermally, so leaving it unqualified puts the electrically-best answer in front of
quality rather than making it a free win. The manufacturer's own recommendation, NCP1117,
*is* qualified and cooks the gateway. Two different gates, two different desks, and neither
is the obvious one.

## Verified facts, and why the seed is what writes them

Sourced live and unaided, four SOT-223 regulators come back with one shared package-table
θJA and no junction limit at all — honest, since the evidence row says so, and useless for
telling them apart. The figures in `PARTS.md` were read off the manufacturers' datasheets by
hand, so this writes them as *verified* facts, which is what lets them outrank a
distributor's parametric table. Until something wrote them, that rule could not fire.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg_pool import AsyncConnectionPool

from continuity.api.store import Store
from continuity.parts import dossier
from tools.eol_differential import (
    AMS1117,
    LD1117,
    LINE_A,
    LINE_B,
    LINE_C,
    NCP1117,
    OUTPUT_CAPACITOR,
    TLV1117,
)

COMPANY = "Northwind Instruments"
ENGINEER = ("engineer@northwind.example", "continuity-demo-2026")
APPROVER = ("quality@northwind.example", "continuity-demo-2026")

REVISION = "Rev C"

AFFECTED = (LINE_A, LINE_B, LINE_C)
"""The three that carry the retired part."""

UNAFFECTED = (
    ("Bench supply", TLV1117, LINE_A.load_part, 25, "bench instrument, 25 °C laboratory ambient"),
    ("Handheld meter", NCP1117, LINE_C.load_part, 30, "handheld enclosure, 30 °C ambient"),
)
"""Two that do not, so a notice about AMS1117 reaches three of five rather than everything.

Exposure that returned every line would demonstrate nothing about exposure."""

QUALIFIED = (AMS1117, TLV1117, NCP1117, OUTPUT_CAPACITOR,
             LINE_A.load_part, LINE_B.load_part, LINE_C.load_part)
"""The approved manufacturer list: **everything already on a shipping board.**

Derived from what the company ships rather than picked, because that is what an AML is. A
part sitting in production has been qualified by definition, and an AML that omitted the
modules and the output capacitor would fail every board on every line for parts nobody was
proposing to change — which is exactly what the first version of this seed did.

**LD1117S33 is the one part not on it**, and it is not on it because nothing ships with it.
That is the whole shape of the scenario: it is the candidate that clears the gateway most
comfortably on the numbers, and taking it is a decision for quality rather than a free win.
The manufacturer's own recommendation *is* qualified, and cooks the gateway. Two gates, two
desks, neither the obvious one."""

APPROVED_VENDOR = "JLCPCB"

EVERY_PART = (AMS1117, TLV1117, LD1117, NCP1117, OUTPUT_CAPACITOR,
              LINE_A.load_part, LINE_B.load_part, LINE_C.load_part)


def profile_for(line, *, ambient: int, ambient_source: str) -> dict:
    return {
        "ambient_c": ambient,
        "ambient_source": ambient_source,
        "mounting": "1000 mm² top and back copper, 1/16in FR-4, 1 oz",
        "rails": {
            "vin": {
                "voltage": line.input_voltage,
                "i_limit": line.input_limit,
                "basis": line.input_basis,
                "members": ["u1"],
            },
            "3v3": {
                "source": "u1",
                "members": ["u2", "c1"],
                "i_load": line.load,
                "i_load_basis": line.load_basis,
            },
        },
    }


PROPICO = Path(__file__).resolve().parent.parent / "fixtures" / "kicad" / "propico"
PROPICO_BOM = PROPICO.parent / "propico_bom.json"

BOARD_LINE = "Sensor node"
"""The one product line that is a real board, and is described by it.

We have exactly one real KiCad project. Attaching it to three product lines would claim
three different products are the same board, which anybody can check by opening two of
them, and a stated bill of three parts beside a project of forty disagrees with itself.

So one line **is** ProPico: its bill is what KiCad reads out of the project, at the
designators the project uses, with the footprints the project draws. The retired part sits
at U3 in both records because it sits at U3. The other four lines keep their stated bills
and honestly have no project, which is an ordinary thing for a company and a better answer
than pretending otherwise.
"""


def propico_bundle() -> bytes:
    """The project, zipped exactly as an engineer would upload it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PROPICO.iterdir()):
            if path.is_file():
                archive.write(path, f"propico/{path.name}")
    return buffer.getvalue()


def propico_bom() -> list[dict]:
    """ProPico's own bill, as `kicad-cli` read it.

    Vendored rather than read at seed time, so seeding needs no Docker. The file records
    which field the part numbers came from and which KiCad read them, because a bill whose
    provenance cannot be checked is a bill somebody typed.
    """
    read = json.loads(PROPICO_BOM.read_text())
    return [
        {
            "refdes": row["refdes"],
            "mpn": row["mpn"],
            "manufacturer": PROPICO_MANUFACTURERS.get(row["mpn"]),
            "footprint": row["footprint"],
            "populated": True,
        }
        for row in read["rows"]
    ]


PROPICO_MANUFACTURERS = {
    "AMS1117-3.3": "Advanced Monolithic Systems",
    "RP2040": "Raspberry Pi",
    "W25Q16JVUXIQ": "Winbond",
    "FM24CL16B": "Infineon",
    "LM4040D30FTA": "Texas Instruments",
}
"""Only where the manufacturer is not in question.

The board states part numbers, not manufacturers. Guessing the rest would put a name
against a passive nobody has checked, and `None` is the honest answer for a row whose
maker the project does not say.
"""


def propico_profile(ambient: int, ambient_source: str, load: float, load_basis: str) -> dict:
    """The operating profile of a real board, with each part of it sourced.

    **The topology is read, not stated.** `nets` in the vendored file is what
    `kicad-cli sch export netlist` says: VBUS arrives at the USB-C connector, +5V reaches the
    regulator at U3, and U3's +3V3 output reaches U1, U2 and U5. Nothing here is a guess about
    what feeds what.

    **The members are the loads, not everything on the net.** Twenty-one components sit on
    +3V3 and most are decoupling: a capacitor across a rail is on it without drawing from it,
    and a power tree that drew every one of them would be a wall rather than a picture. So
    the members are the active devices plus the regulator's output capacitor, which the
    capacitor rule needs by name. Stated here rather than inferred quietly, because it is the
    one place in this file where a person chose which rows to keep.

    **The ambient and the load current remain the company's own claims.** A board file does
    not know where a product is installed or how hard it is driven, and pretending to read
    those out of KiCad would be inventing provenance.
    """
    read = json.loads(PROPICO_BOM.read_text())
    on_3v3 = read["nets"]["+3V3"]
    loads = [ref for ref in on_3v3 if ref.startswith("U") and ref != "U3"]
    return {
        "ambient_c": ambient,
        "ambient_source": ambient_source,
        "mounting": "1000 mm² top and back copper, 1/16in FR-4, 1 oz",
        "rails": {
            "vin": {
                "voltage": 5.0,
                "i_limit": 3.0,
                "basis": "USB Type-C default Rp advertisement",
                "members": ["U3"],
            },
            "3v3": {
                "source": "U3",
                "members": [*loads, "C1"],
                "i_load": load,
                "i_load_basis": load_basis,
            },
        },
    }


def bom_for(regulator, load_part) -> list[dict]:
    return [
        {"refdes": "u1", "mpn": regulator.mpn, "manufacturer": regulator.manufacturer,
         "footprint": regulator.package, "populated": True},
        {"refdes": "u2", "mpn": load_part.mpn, "manufacturer": load_part.manufacturer,
         "populated": True},
        {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn,
         "manufacturer": OUTPUT_CAPACITOR.manufacturer, "populated": True},
    ]


async def seed(store: Store, *, reset: bool = False) -> dict:
    """Build the world. Returns what was made, so a caller can assert on it."""
    existing = await store.user_by_email(ENGINEER[0])
    if existing is not None:
        if not reset:
            raise SystemExit(
                f"{ENGINEER[0]} already exists. Re-run with --reset to replace the demo "
                "company, which deletes its lines, runs and decisions."
            )
        async with store.pool.connection() as conn:
            async with conn.transaction():
                # The work first, then the people, then the company.
                #
                # This used to delete the users and let everything cascade off them, which
                # worked for as long as the demo world had never been used. It stopped the
                # moment a decision was answered: `decisions.decided_by` is ON DELETE SET
                # NULL while `decisions.line_id` cascades, so deleting a user made
                # PostgreSQL *update* a decision row whose product line the same statement
                # had already cascaded away, and the update re-checked `line_id` against a
                # row that was gone. Whether it fires depends on the order the rows come
                # off disk, so it survived a fresh test database and broke on the demo
                # one, twice, after a run that ended in an approval.
                #
                # Deleting the lines while their owners still exist removes the decisions
                # outright rather than nulling columns on them, and the ordering question
                # does not arise. `users.org_id` has no cascade on purpose, since deleting
                # a company should not silently delete its staff in production, so the
                # organisation still has to go last.
                await conn.execute(
                    "DELETE FROM product_lines WHERE org_id = %s", (existing.org_id,)
                )
                await conn.execute("DELETE FROM notices WHERE org_id = %s", (existing.org_id,))
                await conn.execute("DELETE FROM users WHERE org_id = %s", (existing.org_id,))
                await conn.execute(
                    "DELETE FROM organisations WHERE id = %s", (existing.org_id,)
                )

    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    engineer = await store.create_user(ENGINEER[0], hasher.hash(ENGINEER[1]))
    org_id = engineer.org_id
    async with store.pool.connection() as conn:
        await conn.execute(
            "UPDATE organisations SET name = %s WHERE id = %s", (COMPANY, org_id)
        )

    approver = await store.create_user(APPROVER[0], hasher.hash(APPROVER[1]))
    await store.add_user_to_organisation(approver.id, org_id, ["quality", "procurement"])

    # The datasheet readings from PARTS.md, marked as such. This is the writer the
    # verified-over-listing rule was built for and did not have.
    for part in EVERY_PART:
        await store.save_part_facts(dossier.facts_from_part(part, verified=True))

    await store.keep_lists(org_id, aml=True, avl=True)
    for part in QUALIFIED:
        await store.qualify_part(
            org_id, part.mpn, manufacturer=part.manufacturer, by=approver.id,
            note="Qualified on the 2025 audit.",
        )
    await store.approve_vendor(
        org_id, APPROVED_VENDOR, by=approver.id, note="Framework agreement, 2025."
    )

    made = []
    board_line_id = None
    for line in AFFECTED:
        created = await store.create_line(engineer.id, org_id, line.label)
        is_the_board = line.label == BOARD_LINE
        if is_the_board:
            board_line_id = created.id
            await store.save_board(
                line_id=created.id,
                org_id=org_id,
                user_id=engineer.id,
                filename="ProPico.zip",
                project="ProPico",
                bundle=propico_bundle(),
            )
        await store.save_bom_rows(
            created.id, engineer.id, org_id,
            propico_bom() if is_the_board else bom_for(AMS1117, line.load_part),
        )
        await store.save_profile(
            created.id,
            org_id,
            _profile(
                propico_profile(line.ambient_c, line.ambient_basis, line.load, line.load_basis)
                if is_the_board
                else profile_for(line, ambient=line.ambient_c, ambient_source=line.ambient_basis)
            ),
            REVISION,
        )
        made.append((created.id, line.label, AMS1117.mpn))

    for label, regulator, load_part, ambient, ambient_source in UNAFFECTED:
        created = await store.create_line(engineer.id, org_id, label)
        await store.save_bom_rows(
            created.id, engineer.id, org_id, bom_for(regulator, load_part)
        )
        await store.save_profile(
            created.id,
            org_id,
            _profile(profile_for(LINE_A, ambient=ambient, ambient_source=ambient_source)),
            REVISION,
        )
        made.append((created.id, label, regulator.mpn))

    return {
        "org_id": org_id,
        "engineer": engineer,
        "approver": approver,
        "lines": made,
        "board_line_id": board_line_id,
    }


def _profile(payload: dict):
    from continuity.profile import OperatingProfile

    return OperatingProfile.from_json(payload)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="the database URL to seed")
    parser.add_argument(
        "--reset", action="store_true", help="replace the demo company if it already exists"
    )
    args = parser.parse_args()

    async with AsyncConnectionPool(args.database, min_size=1, max_size=3, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        world = await seed(store, reset=args.reset)

    print(f"{COMPANY} — organisation {world['org_id']}")
    print(f"  {ENGINEER[0]} (engineering)")
    print(f"  {APPROVER[0]} (quality, procurement)")
    print(f"  AML: {len(QUALIFIED)} parts — everything already shipping")
    print(f"       {LD1117.mpn} absent: nothing ships with it yet")
    print(f"  AVL: {APPROVED_VENDOR}")
    for line_id, label, mpn in world["lines"]:
        carries = " ← carries the retired part" if mpn == AMS1117.mpn else ""
        print(f"  {label:22} {line_id}  {mpn}{carries}")


if __name__ == "__main__":
    asyncio.run(main())
