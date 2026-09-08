"""Three product lines, one notice, one stream, and the desks that have to answer.

This is the scenario's own question on the wire: *how does your tool coordinate the
cross-team response*. The answer these tests hold is that all three boards are checked at
once, each against every department's rules, and each ends in one of three places — applied
by engineering, waiting on another desk, or nothing that works.

Skipped unless `CONTINUITY_TEST_DB` is set. Sourcing is stubbed: what is under test is the
coordination, and JLCPCB's inventory is not.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api import app as app_module
from continuity.api import matrix as matrix_api
from continuity.api.app import app
from continuity.api.store import Store
from tools.eol_differential import (
    AMS1117,
    LD1117,
    LINES,
    NCP1117,
    OUTPUT_CAPACITOR,
    TLV1117,
)
from tools.seed_world import profile_for

DB_URL = os.environ.get("CONTINUITY_TEST_DB")

pytestmark = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")

CATALOGUE = {
    part.mpn: part
    for part in (AMS1117, NCP1117, LD1117, TLV1117, OUTPUT_CAPACITOR,
                 *(line.load_part for line in LINES))
}

QUALIFIED = [
    AMS1117.mpn, NCP1117.mpn, TLV1117.mpn, OUTPUT_CAPACITOR.mpn,
    *(line.load_part.mpn for line in LINES),
]
"""What the company ships, which is what an approved list is. LD1117 is deliberately not on
it: it is the part that holds the Gateway and has never been qualified."""


class _Notice:
    mpn = AMS1117.mpn
    mpn_line = f"Affected part: {AMS1117.mpn} (SOT-223)"
    manufacturer = "Advanced Monolithic Systems"
    effective_date = "2027-03-31"
    effective_date_line = "Last time buy: 2027-03-31"
    replacement_mpn = NCP1117.mpn
    replacement_line = f"Recommended replacement: {NCP1117.mpn}."
    reason = "Wafer fabrication line closure."


def run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def a_store():
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
            yield store
        finally:
            app.state.store = previous


def bom_for(regulator, load_part):
    return [
        {"refdes": "u1", "mpn": regulator.mpn, "manufacturer": regulator.manufacturer,
         "footprint": regulator.package},
        {"refdes": "u2", "mpn": load_part.mpn, "manufacturer": load_part.manufacturer},
        {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn,
         "manufacturer": OUTPUT_CAPACITOR.manufacturer},
    ]


@asynccontextmanager
async def a_company(store, *, qualified=QUALIFIED):
    """Three products carrying the retired part, and the two standing lists."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120.0
    ) as http:
        await http.post(
            "/auth/register", json={"email": "run@example.com", "password": "a-good-password"}
        )
        me = (await http.get("/auth/me")).json()
        for line in LINES:
            created = (await http.post("/lines", json={"name": line.label})).json()
            await http.put(
                f"/lines/{created['id']}/bom", json={"rows": bom_for(AMS1117, line.load_part)}
            )
            await http.put(
                f"/lines/{created['id']}/profile",
                json={
                    "profile": profile_for(
                        line, ambient=line.ambient_c, ambient_source=line.ambient_basis
                    ),
                    "revision": "Rev C",
                },
            )
        await store.keep_lists(me["org_id"], aml=True, avl=True)
        for mpn in qualified:
            await store.qualify_part(me["org_id"], mpn, manufacturer=None, by=me["id"])
        # A kept list that approves nobody rejects everybody, which is the whole point of
        # `None` meaning "no list" and an empty list meaning "nothing is approved". Leaving
        # this out made every candidate fail source approval, correctly.
        await store.approve_vendor(me["org_id"], "JLCPCB", by=me["id"])
        notice_id = await store.save_notice(me["org_id"], me["id"], _Notice(), source="test")
        yield http, me, notice_id


async def frames_of(http, notice_id, **body):
    async with http.stream(
        "POST", f"/notices/{notice_id}/review/run", json={"candidates": [], **body}
    ) as response:
        assert response.status_code == 200, await response.aread()
        return [
            json.loads(line[6:])
            async for line in response.aiter_lines()
            if line.startswith("data: ")
        ]


@pytest.fixture(autouse=True)
def catalogue(monkeypatch):
    """Sourcing from a fixed catalogue. Reached through the module, because a direct import
    would bind a second reference this patch cannot see."""

    async def resolve(mpn: str, manufacturer: str | None = None):
        return CATALOGUE.get(mpn)

    monkeypatch.setattr(matrix_api, "resolve", resolve)


# ── the whole review, on one stream ───────────────────────────────────────────


def test_every_affected_product_line_is_checked_on_one_stream():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id)

    frames = run(go())

    started = frames[0]
    assert started["type"] == "review_started"
    assert {line["name"] for line in started["lines"]} == {
        "Sensor node", "Gateway", "Cabinet controller"
    }

    assert [frame["seq"] for frame in frames] == sorted(frame["seq"] for frame in frames), (
        "one sequence space across every product line, or the client drops frames"
    )
    assert all("line_id" in frame for frame in frames[1:]), "every frame says whose it is"


def test_each_product_line_ends_once_and_says_what_it_found():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id)

    endings = [frame for frame in run(go()) if frame["type"] == "line_done"]

    assert len(endings) == 3, "one ending per product line, and no stream-wide `done`"
    by_line = {frame["line_name"]: frame for frame in endings}
    assert set(by_line) == {"Sensor node", "Gateway", "Cabinet controller"}


def test_the_three_products_do_not_agree():
    """The finding a single manufacturer-wide recommendation cannot express."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id)

    endings = {
        frame["line_name"]: frame
        for frame in run(go())
        if frame["type"] == "line_done"
    }

    assert endings["Sensor node"]["proposal"] == NCP1117.mpn, (
        "the manufacturer's own answer is right for the coolest board"
    )
    assert endings["Gateway"]["proposal"] != NCP1117.mpn, (
        "159 °C against a 150 °C limit is not a signature away"
    )


def test_an_approved_part_that_clears_the_board_beats_qualifying_a_new_one():
    """Cost decides between two working answers. Resolving with a part already on the
    approved list runs about $1,281; qualifying one from scratch about $15,656."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id, candidates=[LD1117.mpn])

    gateway = next(
        frame for frame in run(go())
        if frame["type"] == "line_done" and frame["line_name"] == "Gateway"
    )

    assert gateway["proposal"] == TLV1117.mpn, "approved and clear wins"
    assert gateway["conditional"] is False
    assert gateway["roles"] == ["engineering"]


def test_the_decision_leaves_engineering_when_no_approved_part_clears():
    """The thirty seconds the whole scenario is about. With nothing qualified that holds
    this board, the part that does hold it has never been qualified — and qualifying it is
    not engineering's to grant."""

    qualified = [mpn for mpn in QUALIFIED if mpn != TLV1117.mpn]

    async def go():
        async with a_store() as store:
            async with a_company(store, qualified=qualified) as (http, _me, notice_id):
                return await frames_of(http, notice_id, candidates=[LD1117.mpn])

    frames = run(go())
    gateway = next(
        frame for frame in frames
        if frame["type"] == "line_done" and frame["line_name"] == "Gateway"
    )

    assert gateway["proposal"] == LD1117.mpn
    assert gateway["conditional"] is True
    assert "quality" in gateway["roles"], "qualification is not engineering's to grant"

    question = next(
        frame for frame in frames
        if frame["type"] == "question" and frame["line_id"] == gateway["line_id"]
    )
    assert "quality" in question["roles"]
    assert LD1117.mpn in question["text"]
    assert "clears every electrical check" in question["text"], (
        "the desk being asked did not watch the run: say the part works before asking "
        "them to qualify it"
    )


def test_the_reasoning_names_where_each_candidate_came_from():
    """A reader deciding between two candidates is entitled to know which one the
    manufacturer named and which one we already ship."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id)

    said = " ".join(
        frame["text"] for frame in run(go()) if frame["type"] == "reasoning"
    )

    assert "recommended by the notice" in said
    assert "already on the approved manufacturer list" in said


def test_a_decision_outlives_the_stream():
    """Nothing is suspended. The answer can arrive tomorrow, from somebody who was not
    watching, in a different browser."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                frames = await frames_of(http, notice_id, candidates=[LD1117.mpn])
                stored = await store.decisions_for_notice(notice_id, me["org_id"])
                return frames, stored

    frames, stored = run(go())

    proposals = {
        frame["line_name"]: frame["decision_id"]
        for frame in frames
        if frame["type"] == "line_done" and frame["decision_id"]
    }
    assert {row["line_name"] for row in stored} == set(proposals)
    for row in stored:
        assert row["state"] == "pending"
        assert row["document"]["attempts"], "a decision without its evidence is a signature on nothing"


def test_a_second_run_replaces_the_pending_decision_rather_than_stacking_one():
    """Two open decisions about the same position on the same board is a question nobody
    can answer."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                await frames_of(http, notice_id)
                await frames_of(http, notice_id, candidates=[LD1117.mpn])
                return await store.decisions_for_notice(notice_id, me["org_id"])

    stored = run(go())

    assert len(stored) == len({row["line_id"] for row in stored})


def test_a_notice_that_reaches_nothing_is_refused_with_the_reason():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, _notice_id):
                class Other(_Notice):
                    mpn = "NOT-ON-ANY-BOARD"
                    mpn_line = "Affected part: NOT-ON-ANY-BOARD"

                other = await store.save_notice(me["org_id"], me["id"], Other(), source="test")
                return await http.post(f"/notices/{other}/review/run", json={"candidates": []})

    response = run(go())

    assert response.status_code == 409
    assert "does not reach" in response.json()["detail"]


def test_the_review_needs_an_account():
    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                return await http.post("/notices/whatever/review/run", json={"candidates": []})

    assert run(go()).status_code == 401
