"""The seeded world, and the demo playing through it.

BUILD item 16: *the seed runs from an empty database and the demo plays end to end
afterwards.* The second half is the test that matters — a seed that produces rows nobody
can tell a story with is scaffolding, not a demo.

The shape carries the story. Three of five lines carry the retired part, so exposure
reaching three proves something about exposure. **LD1117S33 is deliberately off the AML**:
it is the one candidate that clears every board thermally, so leaving it unqualified puts
the electrically-best answer in front of quality rather than handing it over free. The
manufacturer's own recommendation is qualified and cooks the gateway. Two gates, two desks,
neither of them the obvious one.
"""

from __future__ import annotations

import asyncio
import base64
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api.app import app
from continuity.api.store import Store
from tools import seed_world
from tools.eol_differential import AMS1117, LD1117, NCP1117, TLV1117

DB_URL = os.environ.get("CONTINUITY_TEST_DB")

pytestmark = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB to run the seed")


def run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def empty():
    """An genuinely empty database, because that is what the seed claims to work from."""
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=3, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute(
                "TRUNCATE users, organisations, sessions, product_lines, threads, "
                "part_facts CASCADE"
            )
        previous = app.state.store
        app.state.store = store
        try:
            yield store
        finally:
            app.state.store = previous


def test_the_seed_builds_the_world_the_scenario_needs():
    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            lists = await store.approved_lists(world["org_id"])
            lines = await store.lines_for_user(world["org_id"])
            exposed = await store.lines_exposed_to(world["org_id"], AMS1117.mpn)
            approver = await store.user_by_email(seed_world.APPROVER[0])
            return world, lists, lines, exposed, approver

    world, lists, lines, exposed, approver = run(go())

    assert len(lines) == 5, "five product lines"
    assert len(exposed) == 3, "three of them carry the retired part, and two do not"

    assert world["engineer"].roles == ("engineering",)
    assert set(approver.roles) == {"quality", "procurement"}
    assert approver.org_id == world["org_id"], "both people in one company"

    assert lists.vendors == frozenset({seed_world.APPROVED_VENDOR.upper()})
    assert LD1117.mpn.upper() not in lists.parts, (
        "LD1117 must stay off the AML — it is the part that clears every board, and "
        "qualifying it here would remove the decision the demo turns on"
    )
    assert NCP1117.mpn.upper() in lists.parts, "the recommendation is qualified and still wrong"


def test_every_seeded_line_can_be_turned_into_a_board():
    """A line without a profile cannot be checked, which would fail silently at the matrix."""
    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            built = []
            for line in await store.lines_for_user(world["org_id"]):
                bom = await store.bom_for_line(line.id, world["org_id"])
                built.append((line.name, line.revision, line.profile is not None, len(bom)))
            return built

    for name, revision, has_profile, rows in run(go()):
        assert has_profile, f"{name} has no operating profile"
        assert revision == seed_world.REVISION, f"{name} states no revision"
        assert rows == 3, f"{name} has {rows} BOM rows"


def test_the_seed_writes_verified_part_facts():
    """The writer the verified-over-listing rule was built for and did not have.

    Sourced live and unaided, four SOT-223 regulators come back with one shared package-table
    figure and no junction limit — honest, and useless for telling them apart.
    """
    async def go():
        async with empty() as store:
            await seed_world.seed(store)
            return await store.part_facts([LD1117.mpn, NCP1117.mpn])

    facts = run(go())

    for mpn, expected_theta in ((LD1117.mpn, 110.0), (NCP1117.mpn, 160.0)):
        by_field = {row["field"]: row for row in facts[mpn]}
        assert float(by_field["theta_ja"]["value"]) == expected_theta
        assert by_field["theta_ja"]["source"].startswith("datasheet —"), (
            "an unmarked fact only fills a blank and cannot outrank a listing"
        )
        assert "t_j_max" in by_field, "the junction limit is not the ambient grade"


def test_running_the_seed_twice_is_refused_rather_than_doubling_the_world():
    async def go():
        async with empty() as store:
            await seed_world.seed(store)
            try:
                await seed_world.seed(store)
            except SystemExit as refusal:
                return str(refusal), len(await store.lines_for_user(
                    (await store.user_by_email(seed_world.ENGINEER[0])).org_id
                ))
            return None, None

    refusal, lines = run(go())

    assert refusal is not None and "--reset" in refusal
    assert lines == 5, "the refused second run left the world untouched"


def test_reset_replaces_the_world_and_leaves_one_company():
    async def go():
        async with empty() as store:
            await seed_world.seed(store)
            await seed_world.seed(store, reset=True)
            async with store.pool.connection() as conn:
                cursor = await conn.execute("SELECT count(*) FROM organisations")
                (orgs,) = await cursor.fetchone()
                cursor = await conn.execute("SELECT count(*) FROM product_lines")
                (lines,) = await cursor.fetchone()
            return orgs, lines

    orgs, lines = run(go())

    assert orgs == 1, "signing up mints a company each, and the vacated ones must not pile up"
    assert lines == 5, "one world, not two"


# ── the demo plays ────────────────────────────────────────────────────────────


def test_the_demo_plays_end_to_end_on_the_seeded_world(monkeypatch):
    """BUILD's own test, and the one that decides whether the seed is worth anything.

    A notice arrives, three of five products are affected, and each gets a change request
    whose proposal differs — because the same substitute is right for one product and wrong
    for another, which is the entire argument.
    """
    from continuity import notices as reader
    from continuity.api import matrix as matrix_api
    from tools.eol_differential import LINES, OUTPUT_CAPACITOR
    from tools.make_notice import FULL

    specs = {
        part.mpn: part
        for part in (AMS1117, TLV1117, LD1117, NCP1117, OUTPUT_CAPACITOR,
                     *(line.load_part for line in LINES))
    }

    async def resolve(mpn: str, manufacturer: str | None = None):
        return specs.get(mpn)

    async def read_notice(_system, _user, **_kwargs):
        return {
            "mpn": AMS1117.mpn,
            "mpn_line": f"Affected part: {AMS1117.mpn} (SOT-223)",
            "manufacturer": "Advanced Monolithic Systems",
            "effective_date": "2027-03-31",
            "effective_date_line": "Last time buy: 2027-03-31",
            "replacement_mpn": NCP1117.mpn,
            "replacement_line": f"Recommended replacement: {NCP1117.mpn}.",
            "reason": "Wafer fabrication line closure.",
        }

    monkeypatch.setattr(matrix_api, "resolve", resolve)
    monkeypatch.setattr(reader.llm, "available", lambda: True)
    monkeypatch.setattr(reader.llm, "complete_json", read_notice)

    # The document the demonstration actually uploads, PDF and all, rather than four
    # typed lines that would prove nothing about extraction. Every line the stub above
    # quotes is a line of it; `test_notice_document.py` is what holds that true.
    pcn = FULL.pdf()

    async def go():
        async with empty() as store:
            await seed_world.seed(store)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
            ) as http:
                await http.post(
                    "/auth/login",
                    json={"email": seed_world.ENGINEER[0], "password": seed_world.ENGINEER[1]},
                )
                notice = (
                    await http.post(
                        "/notices",
                        json={"document": base64.b64encode(pcn).decode()},
                    )
                ).json()
                reviewed = await http.post(
                    f"/notices/{notice['id']}/review",
                    json={
                        "candidates": [NCP1117.mpn, LD1117.mpn, TLV1117.mpn],
                        "annual_volume": 20_000,
                    },
                )
                return notice, reviewed

    notice, reviewed = run(go())

    assert {row["name"] for row in notice["affected"]} == {
        "Sensor node", "Gateway", "Cabinet controller"
    }, "the notice reaches three of five products"

    assert reviewed.status_code == 201, reviewed.text
    requests = {r["line_name"]: r for r in reviewed.json()["requests"]}
    assert len(requests) == 3

    for name, request in requests.items():
        assert request["baseline_mpn"] == AMS1117.mpn
        assert request["revision"] == seed_world.REVISION
        assert request["not_assessed"], f"{name} does not say what it left unchecked"
        assert request["cost"]["recurring_annual"] is not None, "a volume was stated"

    # The manufacturer recommends NCP1117. It is qualified, and it cooks the gateway.
    assert requests["Gateway"]["proposal"] != NCP1117.mpn
    rejected = {a["mpn"]: a["rejected_because"] for a in requests["Gateway"]["alternatives"]}
    assert "159 °C" in (rejected.get(NCP1117.mpn) or "")

    # And LD1117 is refused by the *other* gate. It survives the gateway thermally — 1.5 °C
    # of margin — and nothing ships with it, so it is not on the approved list. Two gates,
    # two desks: the recommendation fails on physics, the alternative on qualification.
    assert LD1117.mpn in rejected
    assert "approved manufacturer list" in rejected[LD1117.mpn]

    # What the gateway does take is qualified and has room: TLV1117 at 35 °C of margin,
    # rather than LD1117 at 1.5 °C. The better answer on both counts, and it took the gates
    # to find it.
    assert requests["Gateway"]["proposal"] == TLV1117.mpn
