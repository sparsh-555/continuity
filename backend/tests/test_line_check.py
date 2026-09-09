"""Checking a product line that already ships, under its own stored conditions.

The graph on a product line page was grey, because every slot came back `unchecked` and
that was the truthful answer: no rule had looked at the board. The result is a screen that
says nothing works about products that ship today.

Painting it green without running anything would be worse — an unearned verdict is the one
thing this system must not produce. So it runs the engine. A stored line has a bill, an
operating profile and verified part facts, which is everything `rules.py` needs.

The check is its own endpoint rather than part of `/overview` on purpose: resolving parts
reaches a distributor, and the page has to render offline and instantly. It loads grey and
settles.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api import matrix as matrix_api
from continuity.api.app import app
from continuity.api.store import Store
from tools import seed_world as SEED
from tools.eol_differential import AMS1117, NCP1117, OUTPUT_CAPACITOR, TLV1117

DB_URL = os.environ.get("CONTINUITY_TEST_DB")
database = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB to run these")

CATALOGUE = {part.mpn: part for part in (AMS1117, NCP1117, TLV1117, OUTPUT_CAPACITOR)}


@pytest.fixture(autouse=True)
def catalogue(monkeypatch):
    """Parts as a distributor hands them over: **without the datasheet readings.**

    This matters more than it looks. Returning the fixtures whole would hand the engine
    `cout_min_uf`, `t_j_max` and a real θJA that no listing publishes, and every test here
    would pass whether or not the endpoint reads the company's verified facts. That is the
    trap that let NCP1117 clear the Gateway in the review: the check looked right because
    the fixture was doing the work.

    So the fields a datasheet supplies are stripped here, and only
    `normalize.set_dossier_lookup` can put them back.
    """
    from dataclasses import replace

    async def resolve(mpn: str, manufacturer: str | None = None):
        part = CATALOGUE.get(mpn)
        if part is None:
            return None
        return replace(
            part,
            cout_min_uf=None,
            cout_source_line=None,
            t_j_max=None,
            theta_ja=None,
            theta_ja_source_line=None,
        )

    monkeypatch.setattr(matrix_api, "resolve", resolve)


@asynccontextmanager
async def a_world():
    from psycopg_pool import AsyncConnectionPool

    from tools import seed_world

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=2, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE users, organisations CASCADE")
        world = await seed_world.seed(store)
        previous = app.state.store
        app.state.store = store
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
            ) as http:
                await http.post(
                    "/auth/login",
                    json={"email": seed_world.ENGINEER[0], "password": seed_world.ENGINEER[1]},
                )
                yield http, world
        finally:
            app.state.store = previous


def named(world: dict, label: str) -> str:
    return next(line_id for line_id, name, _ in world["lines"] if name == label)


@database
def test_a_shipping_line_checks_out_green():
    """These products ship. Saying so is a verdict the engine produced, not an assumption."""

    async def go():
        async with a_world() as (http, world):
            return await http.post(f"/lines/{named(world, 'Bench supply')}/check")

    response = asyncio.run(go())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slots"]["u1"]["status"] == "pass"
    assert body["checked"] > 0, "a green with no checks behind it is not a green"


@database
def test_the_check_says_what_it_could_not_assess():
    """Green means nothing failed, not that everything was checkable, and the difference is
    the whole reason there are five coverage labels rather than three."""

    async def go():
        async with a_world() as (http, world):
            return (await http.post(f"/lines/{named(world, 'Bench supply')}/check")).json()

    body = asyncio.run(go())

    assert "not_assessed" in body and "evidence_missing" in body
    assert isinstance(body["not_assessed"], list)


@database
def test_a_line_with_no_profile_is_refused_rather_than_reported_green():
    """Nothing to check it against. Reporting a pass would be inventing the conditions."""

    async def go():
        async with a_world() as (http, world):
            store = app.state.store
            line = await store.create_line(
                (await store.user_by_email(__import__("tools.seed_world", fromlist=["x"]).ENGINEER[0])).id,
                world["org_id"],
                "Undescribed",
            )
            return await http.post(f"/lines/{line.id}/check")

    response = asyncio.run(go())

    assert response.status_code == 409
    assert "profile" in response.json()["detail"]


@database
def test_another_company_cannot_check_this_line():
    async def go():
        async with a_world() as (http, world):
            line_id = named(world, "Bench supply")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as other:
                await other.post(
                    "/auth/register",
                    json={"email": "someone@else.example", "password": "a-good-password"},
                )
                return await other.post(f"/lines/{line_id}/check")

    assert asyncio.run(go()).status_code == 404


@database
def test_the_check_installs_the_companys_verified_part_facts(monkeypatch):
    """The trap that has now bitten twice, tested at the mechanism rather than the symptom.

    Without `normalize.set_dossier_lookup`, every SOT-223 part falls back to the package
    table's one figure and to whatever the distributor's parametric blob says. In the review
    that made NCP1117 clear the Gateway, which is the answer this product exists to
    disprove. Here it is quieter and no better: a green computed against a listing rather
    than against the datasheets the company read. Live, the symptom was
    `capacitor_requirements` landing in `evidence_missing` while the same board offline
    reports it satisfied.

    Asserted on the installation rather than on a resulting label on purpose. A stub that
    hands back a whole `PartSpec` never goes through normalisation at all, so the fields
    arrive whether or not the lookup exists and the test would pass either way — which is
    exactly how the first version of this test passed while the endpoint was still wrong.
    """
    from continuity.parts import normalize

    installed: list[object] = []
    real = normalize.set_dossier_lookup

    def spy(lookup):
        installed.append(lookup)
        return real(lookup)

    monkeypatch.setattr(normalize, "set_dossier_lookup", spy)

    async def go():
        async with a_world() as (http, world):
            return await http.post(f"/lines/{named(world, 'Bench supply')}/check")

    response = asyncio.run(go())

    assert response.status_code == 200, response.text
    assert installed and installed[0] is not None, (
        "the check graded a shipping product against a distributor's listing"
    )


@database
def test_a_part_nobody_knows_anything_about_is_named(monkeypatch):
    """A slot with no verdict renders exactly like a slot nobody got to.

    This is now the narrow case it should be: no distributor listing **and** no reading the
    company recorded. A part on a shipping line usually has one or the other, and when it
    has neither the honest answer is to say which part, rather than leave a grey node beside
    two green ones with nothing explaining the difference.
    """
    from continuity.api import matrix as matrix_api

    async def resolve(mpn: str, manufacturer: str | None = None):
        return None

    monkeypatch.setattr(matrix_api, "resolve", resolve)

    async def go():
        async with a_world() as (http, world):
            store = app.state.store
            line_id = named(world, "Bench supply")
            rows = await store.bom_for_line(line_id, world["org_id"])
            engineer = await store.user_by_email(SEED.ENGINEER[0])
            # One part nothing has ever recorded a fact about.
            await store.save_bom_rows(
                line_id, engineer.id, world["org_id"],
                [*rows, {"refdes": "u9", "mpn": "NOBODY-KNOWS-THIS-1", "populated": True}],
            )
            return (await http.post(f"/lines/{line_id}/check")).json()

    body = asyncio.run(go())

    named_back = {row["refdes"]: row["mpn"] for row in body["unresolved"]}
    assert named_back == {"u9": "NOBODY-KNOWS-THIS-1"}
    assert "u9" not in body["slots"], "no verdict was produced for it, and none is claimed"


@database
def test_a_line_is_still_checked_when_no_distributor_answers(monkeypatch):
    """A product line in the demo is live. It has to be checked, not excused.

    The distributor is a network call and the venue's network is not ours. When it cannot
    answer, the parts fall back to the readings the company recorded — which are better
    evidence than a listing anyway, being read off the manufacturer's own datasheets — so
    a shipping product is checked rather than reported as unresolvable.

    Without this, one flaky lookup put a grey node beside two green ones on the main demo
    page, with the product unable to say anything about a part it ships.
    """
    from continuity.api import matrix as matrix_api

    async def nothing(mpn: str, manufacturer: str | None = None):
        raise RuntimeError("no distributor today")

    monkeypatch.setattr(matrix_api, "resolve", nothing)

    async def go():
        async with a_world() as (http, world):
            return (await http.post(f"/lines/{named(world, 'Bench supply')}/check")).json()

    body = asyncio.run(go())

    assert body["unresolved"] == [], "the company's own readings are enough to check with"
    assert set(body["slots"]) == {"u1", "u2", "c1"}
    assert body["checked"] > 0


@database
def test_checking_the_same_board_twice_does_not_check_it_twice():
    """Four to seven seconds a visit, measured, because the answer was thrown away.

    The inputs are the stored bill, the stored profile and the recorded facts, so a second
    request with none of them changed has nothing to recompute. Asserted on the engine
    being reached rather than on a duration, because a timing assertion on a network call
    is a flake waiting for a slow morning.
    """
    from continuity.api import lines as lines_api
    from continuity.parts import normalize

    installs: list[object] = []
    real = normalize.set_dossier_lookup

    def spy(lookup):
        installs.append(lookup)
        return real(lookup)

    async def go():
        async with a_world() as (http, world):
            line = named(world, "Bench supply")
            first = await http.post(f"/lines/{line}/check")
            second = await http.post(f"/lines/{line}/check")
            return first, second

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(normalize, "set_dossier_lookup", spy)
        first, second = asyncio.run(go())

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json(), "the same board answered differently"
    assert len(installs) == 1, f"the engine ran {len(installs)} times for one unchanged board"

    # And a bill that changes is a different board, so it is checked again.
    lines_api.forget_checks()


@database
def test_a_changed_bill_is_checked_again():
    """The cache is keyed on what was checked, not on which line it was.

    Applying a substitution rewrites a row, and a page still showing the old verdict would
    be the worst possible thing for this cache to do — the whole demo ends in a bill
    changing.
    """
    from continuity.parts import normalize

    installs: list[object] = []
    real = normalize.set_dossier_lookup

    def spy(lookup):
        installs.append(lookup)
        return real(lookup)

    async def go():
        async with a_world() as (http, world):
            line = named(world, "Bench supply")
            await http.post(f"/lines/{line}/check")
            rows = (await http.get(f"/lines/{line}/bom")).json()
            for row in rows:
                if row["refdes"] == "u1":
                    row["mpn"] = "NCP1117ST33T3G"
                    row["manufacturer"] = "onsemi"
            await http.put(f"/lines/{line}/bom", json={"rows": rows})
            return await http.post(f"/lines/{line}/check")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(normalize, "set_dossier_lookup", spy)
        again = asyncio.run(go())

    assert again.status_code == 200, again.text
    assert len(installs) == 2, "a rewritten bill was answered from the old board's cache"
