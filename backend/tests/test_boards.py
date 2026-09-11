"""Uploading the board a product line is built from, and asking what a substitute does.

Skipped unless `CONTINUITY_TEST_DB` is set, and the routes that shell out to KiCad are
skipped again unless `CONTINUITY_KICAD` names one. The split matters: storing a project,
refusing a bad one and reporting the capability as absent are all things this has to do on
an instance with no KiCad at all, and they are tested there.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from continuity.api.app import app
from continuity.api.store import Store
from continuity.kicad import runner

DB_URL = os.environ.get("CONTINUITY_TEST_DB")
HAS_KICAD = bool(os.environ.get("CONTINUITY_KICAD")) and runner.available()

pytestmark = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")

needs_kicad = pytest.mark.skipif(
    not HAS_KICAD, reason="set CONTINUITY_KICAD=docker to run against real KiCad"
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "kicad" / "propico"


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


@asynccontextmanager
async def a_line(email: str = "board@example.com"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=300.0
    ) as http:
        await http.post("/auth/register", json={"email": email, "password": "a-good-password"})
        line = (await http.post("/lines", json={"name": "Gateway"})).json()
        yield http, line["id"]


def a_bundle(*, prefix: str = "ProPico") -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(FIXTURE.glob("ProPico.*")):
            archive.write(path, f"{prefix}/{path.name}")
    return base64.b64encode(buffer.getvalue()).decode()


def upload(bundle: str, **extra) -> dict:
    return {"filename": "ProPico.zip", "bundle": bundle, **extra}


# ── with no KiCad in sight ────────────────────────────────────────────────────


def test_uploading_a_board_needs_an_account():
    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                return await http.put("/lines/x/board", json=upload("eA=="))

    assert run(go()).status_code == 401


def test_a_board_belongs_to_the_line_it_was_uploaded_to():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                put = await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                got = await http.get(f"/lines/{line_id}/board")
                return put, got

    put, got = run(go())

    assert put.status_code == 200, put.text
    assert put.json()["project"] == "ProPico"
    assert got.json()["board"]["filename"] == "ProPico.zip"
    assert got.json()["board"]["bytes"] > 100_000


def test_a_second_upload_replaces_the_first():
    """A product line is one design. Two boards would leave every later question with two
    answers and no way to choose."""

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                await http.put(
                    f"/lines/{line_id}/board",
                    json={"filename": "second.zip", "bundle": a_bundle()},
                )
                return await http.get(f"/lines/{line_id}/board")

    assert run(go()).json()["board"]["filename"] == "second.zip"


def test_a_line_with_no_board_says_so_rather_than_failing():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                return await http.get(f"/lines/{line_id}/board")

    response = run(go())

    assert response.status_code == 200
    assert response.json()["board"] is None


def test_a_bundle_that_is_not_a_project_is_refused_with_the_reason():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                return await http.put(
                    f"/lines/{line_id}/board",
                    json=upload(base64.b64encode(buffer.getvalue()).decode()),
                )

    response = run(go())

    assert response.status_code == 422
    assert "kicad_pro" in response.json()["detail"]


def test_a_bundle_that_would_write_outside_its_directory_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.kicad_pro", "(project)")

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                return await http.put(
                    f"/lines/{line_id}/board",
                    json=upload(base64.b64encode(buffer.getvalue()).decode()),
                )

    response = run(go())

    assert response.status_code == 422
    assert "unsafe path" in response.json()["detail"]


def test_a_board_on_another_organisation_s_line_is_not_found():
    async def go():
        async with a_store():
            async with a_line("mine@example.com") as (mine, line_id):
                await mine.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                async with a_line("theirs@example.com") as (theirs, _):
                    return await theirs.get(f"/lines/{line_id}/board")

    assert run(go()).status_code == 404


def test_a_consequence_without_a_board_is_a_404():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "NCP1117ST33T3G"},
                )

    assert run(go()).status_code == 404


def test_a_streamed_consequence_refuses_before_it_starts():
    """**The refusals are statuses, not frames.** The whole reason these two checks happen
    before the response begins is that a status can still be sent then; once the stream is
    open the only thing left is a frame, and a client that asked for a board would get a
    200 it then has to read a sentence out of.
    """
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                return await http.post(
                    f"/lines/{line_id}/board/consequence/stream",
                    json={"retiring": "AMS1117-3.3", "candidate": "NCP1117ST33T3G"},
                )

    response = run(go())

    assert response.status_code == 404
    assert "no board is stored" in response.json()["detail"]


@pytest.mark.skipif(HAS_KICAD, reason="this is the no-KiCad answer")
def test_without_kicad_the_capability_is_reported_absent_rather_than_guessed():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                put = await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                consequence = await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "NCP1117ST33T3G"},
                )
                return put, consequence

    put, consequence = run(go())

    assert put.status_code == 200, "the project is still stored"
    assert put.json()["kicad"] is False
    assert consequence.status_code == 503
    assert "no KiCad is configured" in consequence.json()["detail"]


# ── with KiCad ────────────────────────────────────────────────────────────────


@needs_kicad
def test_the_upload_adopts_the_bill_of_materials_the_design_states():
    """The ingestion the whole item exists for: the parts under review are the parts on
    the board, because KiCad read them off it."""

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                put = await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                bom = await http.get(f"/lines/{line_id}/bom")
                return put, bom.json()

    put, bom = run(go())

    assert put.json()["adopted"] is True
    assert put.json()["mpn_field"] == "P/N"
    assert len(bom) > 40
    assert [row["refdes"] for row in bom if row["mpn"] == "AMS1117-3.3"] == ["U3"]


@needs_kicad
def test_a_bill_somebody_entered_is_not_overwritten_without_being_asked():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(
                    f"/lines/{line_id}/bom",
                    json={"rows": [{"refdes": "U1", "mpn": "HAND-ENTERED"}]},
                )
                put = await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                bom = await http.get(f"/lines/{line_id}/bom")
                return put, bom.json()

    put, bom = run(go())

    assert put.json()["adopted"] is False
    assert [row["mpn"] for row in bom] == ["HAND-ENTERED"]


@needs_kicad
def test_a_board_being_placed_says_what_it_is_doing_as_it_does_it():
    """Ten seconds of nothing and then everything is a jump, not a wait.

    A cold board takes that long, and the pane sat on *PLACING…* for all of it. The five
    operations were already timed for the WHAT RAN block; this asserts the same list is sent
    as each one finishes, and that the list on the streamed frames is **the same list** the
    finished payload carries rather than a second measurement of the same work.
    """

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                frames = []
                async with http.stream(
                    "POST",
                    f"/lines/{line_id}/board/consequence/stream",
                    json={"retiring": "AMS1117-3.3", "candidate": "NCP1117ST33T3G"},
                ) as response:
                    assert response.status_code == 200, await response.aread()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            frames.append(json.loads(line[6:]))
                return frames

    frames = run(go())

    streamed = [frame for frame in frames if frame["type"] == "step"]
    assert len(streamed) == 5, [frame["name"] for frame in streamed]
    assert [frame["name"] for frame in streamed] == [
        "read the board's placements",
        "place the part and carry its nets by function",
        "refill the zones on both copies",
        "run DRC before and after",
        "render both pictures",
    ]

    assert frames[-1]["type"] == "done", "the stream ends with the whole answer"
    decided = frames[-1]["consequence"]
    assert [(step["name"], step["ms"]) for step in decided["steps"]] == [
        (frame["name"], frame["ms"]) for frame in streamed
    ], "one measurement reported twice, not two measurements of the same work"
    assert decided["broke_connections"] is False


@needs_kicad
def test_a_drop_in_substitute_breaks_nothing_and_kicad_is_what_says_so():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "NCP1117ST33T3G"},
                )

    response = run(go())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refdes"] == "U3"
    assert body["package"] == {"from": "SOT-223", "to": "SOT-223"}
    assert body["broke_connections"] is False
    assert body["before_svg"].startswith("<?xml")
    assert body["crop"] == "98.2416 46.4878 12.0000 12.0000"


@needs_kicad
def test_a_smaller_package_breaks_connections_on_this_board():
    """The answer no parametric search reaches: the cheaper part costs a layout revision."""

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "ME6211C33M5G-N"},
                )

    body = run(go()).json()

    assert body["package"] == {"from": "SOT-223", "to": "SOT-23-5"}
    assert body["broke_connections"] is True
    assert body["counts"]["unconnected_items"]["after"] > body["counts"]["unconnected_items"]["before"]
    assert body["wiring"]["unwired_pads"] == ["3", "4"], "enable and no-connect stay bare"
    assert "ME6211" in body["pinout_source"]
    assert body["before_svg"] != body["after_svg"]


@needs_kicad
def test_a_candidate_with_no_pinout_on_file_is_refused_by_name():
    """LD1117 publishes its pin connections as a figure, so there is nothing to read."""

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "LD1117S33TR"},
                )

    response = run(go())

    assert response.status_code == 422
    assert "LD1117S33TR" in response.json()["detail"]


@needs_kicad
def test_a_part_the_board_does_not_carry_is_a_409():
    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(f"/lines/{line_id}/board", json=upload(a_bundle()))
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "TLV1117LV33DCYR", "candidate": "NCP1117ST33T3G"},
                )

    response = run(go())

    assert response.status_code == 409
    assert "does not carry" in response.json()["detail"]


def any_bundle(folder: str) -> str:
    """One of the other vendored projects, zipped the way an upload arrives."""
    source = FIXTURE.parent / folder
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.iterdir()):
            if path.is_file():
                archive.write(path, f"{folder}/{path.name}")
    return base64.b64encode(buffer.getvalue()).decode()


@needs_kicad
def test_a_board_full_of_copper_zones_reports_no_break_we_did_not_cause():
    """Zones are derived geometry and go stale the moment a footprint moves.

    A zone's fill is computed against the pads that were there when it was last filled.
    Remove a footprint, add another, and pads that reach each other *through* copper read
    as unconnected, so DRC reports a broken connection our change did not cause. KiCad's
    own DRC dialog warns about this.

    Found on OpenJBOD, which carries 687 copper zones. A same-package drop-in at U2
    reported a missing connection at **J1, on a different net, at the other end of the
    board**. ProPico has twenty zones and never showed it, which is the argument for
    checking against boards somebody else drew.

    Both boards are refilled now, not only the modified one, so the two DRC runs are
    computed the same way.
    """

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(
                    f"/lines/{line_id}/board",
                    json={"filename": "OpenJBOD.zip", "bundle": any_bundle("openjbod")},
                )
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "NCP1117ST33T3G"},
                )

    response = run(go())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refdes"] == "U2", "this board puts its regulator somewhere else again"
    assert body["package"] == {"from": "SOT-223", "to": "SOT-223"}
    assert body["broke_connections"] is False, body["added"]
    assert body["added"] == [], "a drop-in adds nothing"


@needs_kicad
def test_a_smaller_package_still_breaks_a_board_full_of_zones():
    """The other direction of the net-keyed comparison, and the reason it exists.

    Keying unconnected findings on the net rather than the witness pads makes a break
    *harder* to see, and everything verified when that landed was that false alarms
    stopped. This is the test that it still catches a true one, on the board that forced
    the change: OpenJBOD, 687 copper zones, where a same-package drop-in is clean.

    Measured 9 Sep: seven added findings, including a GND pad shorting the `/+3.3vSB`
    track and a dangling `/+5vSB` track, and pads 3 and 4 reported unwired because a
    SOT-23-5 has five pads and a three-pin part wires three.
    """

    async def go():
        async with a_store():
            async with a_line() as (http, line_id):
                await http.put(
                    f"/lines/{line_id}/board",
                    json={"filename": "OpenJBOD.zip", "bundle": any_bundle("openjbod")},
                )
                return await http.post(
                    f"/lines/{line_id}/board/consequence",
                    json={"retiring": "AMS1117-3.3", "candidate": "ME6211C33M5G-N"},
                )

    response = run(go())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["package"] == {"from": "SOT-223", "to": "SOT-23-5"}
    assert body["broke_connections"] is True, "a five-pad part on a three-pad land pattern"
    assert body["added"], "the delta has to name what it found"
    assert body["wiring"]["unwired_pads"] == ["3", "4"], "reported, never guessed at"
