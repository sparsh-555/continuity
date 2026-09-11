"""A company states its own policy, and the gate it turns on is survivable.

Both lists have gated every board since they were built, and nothing but `tools/seed_world.py`
and the tests could write them — so a company could not say which parts it had qualified, or
which sources it buys from, without a Python shell.

**The other half of that row was worse than a missing screen.** Turning an AML on reports every
fitted part that is not on it, which is correct and means that for a company which ships
anything, declaring a policy fails every board it has until somebody qualifies the lot. The
seed does that by deriving the list from the bills; a real company had no such step, and this
is the test of it.

Skipped unless `CONTINUITY_TEST_DB` is set.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api.app import app
from continuity.api.store import Store
from tools.eol_differential import AMS1117, OUTPUT_CAPACITOR

DB_URL = os.environ.get("CONTINUITY_TEST_DB")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")


@asynccontextmanager
async def a_company(*, roles: tuple[str, ...] = ("engineering", "quality", "procurement")):
    """One product line that ships two parts, and a person holding the desks asked for."""
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=3, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute(
                "TRUNCATE users, organisations, sessions, product_lines, threads CASCADE"
            )
        previous = app.state.store
        app.state.store = store
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "policy@example.com", "password": "a-good-password"},
                )
                me = (await http.get("/auth/me")).json()
                await store.add_user_to_organisation(me["id"], me["org_id"], list(roles))
                line = (await http.post("/lines", json={"name": "Sensor node"})).json()
                await http.put(
                    f"/lines/{line['id']}/bom",
                    json={
                        "rows": [
                            {
                                "refdes": "u1",
                                "mpn": AMS1117.mpn,
                                "manufacturer": AMS1117.manufacturer,
                                "populated": True,
                            },
                            {
                                "refdes": "c1",
                                "mpn": OUTPUT_CAPACITOR.mpn,
                                "manufacturer": OUTPUT_CAPACITOR.manufacturer,
                                "populated": True,
                            },
                        ]
                    },
                )
                yield http, store, me, line
        finally:
            app.state.store = previous


def _read(result):
    return asyncio.run(result)


def test_a_list_nobody_keeps_is_not_a_list_that_fails_everything():
    """The distinction the model already draws, on the wire: no list configured is not the
    same as a configured list that happens to be empty, and a company that has never set an
    AML must not be told it is short of every part it ships."""

    async def go():
        async with a_company() as (http, _store, _me, _line):
            return (await http.get("/policy")).json()

    policy = _read(go())
    assert policy["parts"]["kept"] is False
    assert policy["parts"]["missing"] == []
    assert policy["parts"]["shipping"] == 2


def test_switching_an_aml_on_shows_what_it_would_fail_before_anything_else():
    """The row's own complaint, measured rather than described."""

    async def go():
        async with a_company() as (http, _store, _me, _line):
            await http.put("/policy/lists", json={"parts": True})
            return (await http.get("/policy")).json()

    policy = _read(go())
    assert policy["parts"]["kept"] is True
    assert sorted(row["mpn"] for row in policy["parts"]["missing"]) == [
        AMS1117.mpn,
        OUTPUT_CAPACITOR.mpn,
    ]


def test_one_action_qualifies_everything_the_company_already_ships():
    """The step the seed does by hand. It keeps the list as well, because this is the action
    that makes keeping one possible at all."""

    async def go():
        async with a_company() as (http, _store, _me, _line):
            outcome = (await http.post("/policy/parts/from-bill")).json()
            return outcome, (await http.get("/policy")).json()

    outcome, policy = _read(go())
    assert outcome == {"qualified": 2}
    assert policy["parts"]["kept"] is True
    assert policy["parts"]["missing"] == []
    assert {row["mpn"] for row in policy["parts"]["entries"]} == {
        AMS1117.mpn,
        OUTPUT_CAPACITOR.mpn,
    }
    # Whose part it is, carried from the bill rather than left blank.
    assert all(row["manufacturer"] for row in policy["parts"]["entries"])


def test_a_desk_that_does_not_keep_the_list_is_refused_by_name():
    """A 403 that says which desk keeps the list is the difference between knowing who to
    ask and concluding that the button is broken."""

    async def go():
        async with a_company(roles=("production",)) as (http, _store, _me, _line):
            response = await http.put("/policy/lists", json={"parts": True})
            return response.status_code, response.json().get("detail", "")

    status, detail = _read(go())
    assert status == 403
    assert "engineering and quality" in detail
    assert "production" in detail


def test_a_source_is_procurements_and_a_part_is_not():
    """Two lists, two owners, and the routing table already said so."""

    async def go():
        async with a_company(roles=("engineering",)) as (http, _store, _me, _line):
            vendor = await http.post("/policy/vendors", json={"distributor": "Mouser"})
            part = await http.post("/policy/parts", json={"mpn": "XYZ-1"})
            return vendor.status_code, part.status_code

    assert _read(go()) == (403, 201)


def test_a_part_can_be_taken_off_again_however_it_is_cased():
    async def go():
        async with a_company() as (http, _store, _me, _line):
            await http.post("/policy/parts", json={"mpn": "XYZ-1"})
            gone = await http.delete("/policy/parts/xyz-1")
            again = await http.delete("/policy/parts/xyz-1")
            return gone.status_code, again.status_code

    assert _read(go()) == (204, 404)
