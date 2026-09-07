"""The matrix endpoint: stored lines in, an attributable grid out.

Part resolution is stubbed to the sourced demo specs. That is deliberate — what is under
test here is the endpoint's own work: reading lines out of the store, refusing the ones it
cannot honestly check, assembling boards, and reporting what it could not source. Whether
JLCPCB can find an MPN is `tests/test_parts.py`'s question, and `tests/test_matrix.py`
already holds the arithmetic.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api import app as app_module
from continuity.api.app import app
from continuity.api.store import Store
from tools.eol_differential import AMS1117, LD1117, LINES, NCP1117, OUTPUT_CAPACITOR, TLV1117

DB_URL = os.environ.get("CONTINUITY_TEST_DB")

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="set CONTINUITY_TEST_DB to run the matrix endpoint tests"
)

SPECS = {
    part.mpn: part
    for part in (AMS1117, TLV1117, LD1117, NCP1117, OUTPUT_CAPACITOR, *(l.load_part for l in LINES))
}


def run(coro):
    return asyncio.run(coro)


from continuity.api.matrix import resolve as _REAL_RESOLVE  # noqa: E402


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


@asynccontextmanager
async def signed_in(email: str = "eng@example.com"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
    ) as http:
        await http.post("/auth/register", json={"email": email, "password": "a-good-password"})
        yield http


def profile_for(line):
    return {
        "ambient_c": line.ambient_c,
        "ambient_source": line.ambient_basis,
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


async def seed(http) -> dict[str, str]:
    """Three product lines, each carrying the incumbent regulator."""
    ids = {}
    for line in LINES:
        created = (await http.post("/lines", json={"name": line.label})).json()
        ids[line.id] = created["id"]
        await http.put(
            f"/lines/{created['id']}/bom",
            json={
                "rows": [
                    {"refdes": "u1", "mpn": AMS1117.mpn, "populated": True},
                    {"refdes": "u2", "mpn": line.load_part.mpn, "populated": True},
                    {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn, "populated": True},
                ]
            },
        )
        await http.put(
            f"/lines/{created['id']}/profile",
            json={"revision": "C", "profile": profile_for(line)},
        )
    return ids


@pytest.fixture(autouse=True)
def sourced(monkeypatch):
    """Resolve MPNs from the demo's sourced specs instead of calling a distributor."""
    from continuity.api import matrix as matrix_api

    async def resolve(mpn: str):
        return SPECS.get(mpn)

    monkeypatch.setattr(matrix_api, "resolve", resolve)


def post_matrix(http, ids, **overrides):
    payload = {
        "line_ids": [ids[line.id] for line in LINES],
        "slot": "u1",
        "candidates": [AMS1117.mpn, TLV1117.mpn, LD1117.mpn, NCP1117.mpn],
    }
    payload.update(overrides)
    return http.post("/matrix", json=payload)


def test_the_endpoint_returns_the_whole_grid_attributable():
    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)
                return (await post_matrix(http, ids)).json(), ids

    body, ids = run(go())

    assert len(body["cells"]) == 12
    assert len(body["lines"]) == 3 and len(body["candidates"]) == 4
    for cell in body["cells"]:
        assert cell["line_id"] in body["lines"]
        assert cell["mpn"] in body["candidates"]
        assert cell["checks"], "a cell with no checks is a hole pretending to be a result"
        assert bool(cell["departments"]) == (not cell["ok"])


def test_the_recommendation_fails_the_gateway_and_lands_on_engineering():
    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)
                body = (await post_matrix(http, ids)).json()
                return body, ids

    body, ids = run(go())
    gateway = ids["B"]

    cell = next(c for c in body["cells"] if c["line_id"] == gateway and c["mpn"] == NCP1117.mpn)
    assert cell["ok"] is False
    assert cell["departments"] == ["engineering"]
    thermal = [c for c in cell["checks"] if c["rule"] == "thermal_dissipation"]
    assert thermal and "159 °C" in thermal[0]["detail"]
    assert body["viable_everywhere"] == [AMS1117.mpn, LD1117.mpn]


def test_every_cell_carries_all_five_coverage_counts_and_the_margin():
    """The two gaps this screen closes: coverage and narrowness were invisible before."""
    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)
                return (await post_matrix(http, ids)).json(), ids

    body, ids = run(go())

    for cell in body["cells"]:
        assert set(cell["counts"]) == {
            "satisfied", "failed", "not_applicable", "not_assessed", "evidence_missing",
        }
        assert cell["counts"]["not_assessed"] == 3

    gateway = next(
        c for c in body["cells"] if c["line_id"] == ids["B"] and c["mpn"] == LD1117.mpn
    )
    assert gateway["margin"] == "1.5 °C"


def test_a_candidate_nobody_can_source_is_named_rather_than_dropped():
    """A grid that silently renders three of four columns lies about what was checked."""
    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)
                return (
                    await post_matrix(
                        http, ids, candidates=[AMS1117.mpn, "NOT-A-REAL-PART"]
                    )
                ).json()

    body = run(go())

    assert body["unresolved"] == ["NOT-A-REAL-PART"]
    assert body["candidates"] == [AMS1117.mpn]


def test_a_line_with_no_operating_profile_is_refused_rather_than_assumed():
    """Checking a substitution against conditions nobody stated is the whole failure mode."""
    async def go():
        async with a_store():
            async with signed_in() as http:
                bare = (await http.post("/lines", json={"name": "Undescribed"})).json()
                return await post_matrix(
                    http, {line.id: bare["id"] for line in LINES}
                )

    response = run(go())

    assert response.status_code == 409
    assert "operating profile" in response.json()["detail"]


def test_a_line_that_does_not_carry_the_part_is_refused():
    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)
                return await post_matrix(http, ids, slot="u9")

    response = run(go())

    assert response.status_code == 409
    assert "does not carry" in response.json()["detail"]


def test_another_organisations_line_is_a_404():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                ids = await seed(mine)
            async with signed_in("stranger@example.com") as stranger:
                return await post_matrix(stranger, ids)

    assert run(go()).status_code == 404


def test_the_endpoint_needs_an_account():
    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                return await http.post(
                    "/matrix", json={"line_ids": ["x"], "slot": "u1", "candidates": ["y"]}
                )

    assert run(go()).status_code == 401


def test_a_verified_datasheet_reading_reaches_the_matrix_instead_of_the_package_table():
    """The mechanism the demo's arithmetic depends on, asserted end to end.

    Sourced live, four SOT-223 regulators all fall back to the package table's single
    figure and come out with four identical junction temperatures. The evidence row says
    so plainly — *"Continuity package table (per-package approximation, board unknown)"* —
    which is honest and useless for choosing between them.

    A θJA read off a datasheet and stored as a part fact is what makes them different, and
    this asserts the stored value wins and travels with its quoted source.
    """
    from continuity.parts import dossier, normalize

    async def go():
        async with a_store() as store:
            await store.save_part_facts(dossier.facts_from_part(LD1117))

            async def lookup(mpn: str):
                return (await store.part_facts([mpn])).get(mpn, [])

            token = normalize.set_dossier_lookup(lookup)
            try:
                return (await store.part_facts([LD1117.mpn]))[LD1117.mpn]
            finally:
                normalize.reset_dossier_lookup(token)

    facts = {row["field"]: row for row in run(go())}

    assert float(facts["theta_ja"]["value"]) == LD1117.theta_ja == 110.0
    assert "SOT-223" in (facts["theta_ja"]["source"] or ""), "the quoted line travels with it"
    assert facts["theta_ja"]["source"] != "Continuity package table"


def test_the_endpoint_installs_the_stored_dossier_lookup():
    """Without it the matrix sources parts blind to everything already verified about them."""
    from continuity.api import matrix as matrix_api
    from continuity.parts import normalize

    seen: list[str | None] = []

    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)

                real = matrix_api._build

                async def spy(body, store, user):
                    seen.append(normalize._dossier_lookup.get())
                    return await real(body, store, user)

                matrix_api._build = spy
                try:
                    await post_matrix(http, ids)
                finally:
                    matrix_api._build = real

    run(go())

    assert seen and seen[0] is not None, "no dossier lookup was in scope while building"


def test_resolve_refuses_to_choose_between_two_manufacturers_of_one_mpn():
    """JLCPCB carries `TLV1117LV33DCYR` twice, and the two listings disagree.

    TI's own listing states a 5.5 V supply ceiling; a second manufacturer's states 12 V.
    Those are not two descriptions of one part — they are two parts wearing one number,
    and picking whichever came back first checks a board against a part nobody named.
    Above 6 V TI's device is destroyed, so the wrong pick turns a substitution review into
    the very thing it exists to prevent.
    """
    from continuity.api import matrix as matrix_api
    from continuity.parts.search import Candidate

    def listing(manufacturer: str) -> Candidate:
        return Candidate(
            lcsc="C1", mpn="TLV1117LV33DCYR", manufacturer=manufacturer,
            description="LDO", package="SOT-223", category="ICs",
            subcategory="LDO", stock=1000, unit_price=0.3, library_type="extended",
        )

    async def two_listings(mpn: str, **_kwargs):
        return [listing("Texas Instruments"), listing("JSMSEMI")]

    async def go():
        real = matrix_api.part_search.search
        matrix_api.part_search.search = two_listings
        try:
            return await _REAL_RESOLVE("TLV1117LV33DCYR")
        finally:
            matrix_api.part_search.search = real

    with pytest.raises(matrix_api.Ambiguous) as raised:
        run(go())

    assert "Texas Instruments" in str(raised.value)
    assert "JSMSEMI" in str(raised.value)


def test_an_ambiguous_candidate_is_named_on_the_matrix_rather_than_checked():
    """Saying which one you meant is a question only the person asking can answer."""
    from continuity.api import matrix as matrix_api

    async def go():
        async with a_store():
            async with signed_in() as http:
                ids = await seed(http)
                real = matrix_api.resolve

                async def resolve(mpn: str):
                    if mpn == TLV1117.mpn:
                        raise matrix_api.Ambiguous(mpn, ["Texas Instruments", "JSMSEMI"])
                    return SPECS.get(mpn)

                matrix_api.resolve = resolve
                try:
                    return (
                        await post_matrix(http, ids, candidates=[AMS1117.mpn, TLV1117.mpn])
                    ).json()
                finally:
                    matrix_api.resolve = real

    body = run(go())

    assert TLV1117.mpn in body["ambiguous"]
    assert "JSMSEMI" in body["ambiguous"][TLV1117.mpn]
    assert body["candidates"] == [AMS1117.mpn], "an ambiguous part is not silently checked"
    assert TLV1117.mpn not in body["unresolved"], "not found and not sure are different things"
