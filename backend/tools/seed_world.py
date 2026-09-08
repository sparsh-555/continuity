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


KICAD_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "kicad"
PROPICO = KICAD_FIXTURES / "propico"
PROPICO_BOM = KICAD_FIXTURES / "propico_bom.json"

BOARDS = {
    "Sensor node": ("propico", "ProPico", "ProPico.zip"),
    "Gateway": ("ws2812", "WS2812Controller", "WS2812Controller.zip"),
    "Cabinet controller": ("openjbod", "OpenJBOD-RP2040", "OpenJBOD-RP2040.zip"),
}
"""One real board per affected product line, each drawn by somebody else.

Three different projects rather than one file attached three times, because attaching one
file to three products claims they are the same board and anybody can check that by opening
two of them. Each was found by searching GitHub for a KiCad schematic carrying an
`AMS1117-3.3`, and each carries it at a different reference designator — U3, U1 and U2 —
which is what the world looks like and what a uniform fixture was hiding.

The fits are not forced. A JBOD is a disk enclosure, and OpenJBOD's controller carries
Ethernet and a fan controller, which is what a cabinet controller does. The WS2812 board is
an ESP-12F WiFi module on a 3.3 V rail, which is a gateway.

Licences travel with them: ProPico MIT, WS2812Controller MIT, OpenJBOD CERN-OHL-P-2.0.
"""

BOARD_LINE = "Sensor node"
"""The product line whose board the run-through demonstrates.

**A board is not a bill.** Continuity validates at block level — the regulator, what it
feeds, and the output capacitor the stability rule needs — and the Singapore proposal draws
that boundary on purpose: *"synthesis requires pin-level connectivity, a substantially
larger data problem than the one described here."* The planner's own prompt says passives
are an implementation detail. So a product line's bill stays the three parts it has always
been, and importing a real board's forty-one rows would drag thirty-five passives into a
system with no business checking them.

What the project *is* is the design: the picture beside the component graph, and the thing a
substitution is actually applied to once the engine has given its verdict. That needs the
file attached and nothing else.

One line rather than all five because there is one real project, and attaching one file to
several products would claim they are the same board, which anybody can check by opening
two of them.
"""


def zipped(folder: str) -> bytes:
    """One vendored project, zipped exactly as an engineer would upload it."""
    source = KICAD_FIXTURES / folder
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.iterdir()):
            if path.is_file():
                archive.write(path, f"{folder}/{path.name}")
    return buffer.getvalue()


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
        if line.label == BOARD_LINE:
            board_line_id = created.id
        if line.label in BOARDS:
            folder, project_name, filename = BOARDS[line.label]
            await store.save_board(
                line_id=created.id,
                org_id=org_id,
                user_id=engineer.id,
                filename=filename,
                project=project_name,
                bundle=zipped(folder),
            )
        await store.save_bom_rows(
            created.id, engineer.id, org_id, bom_for(AMS1117, line.load_part)
        )
        await store.save_profile(
            created.id,
            org_id,
            _profile(profile_for(line, ambient=line.ambient_c, ambient_source=line.ambient_basis)),
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
