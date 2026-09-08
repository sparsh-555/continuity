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
from continuity import review
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
async def a_company(store, *, qualified=QUALIFIED, vendors=("JLCPCB",)):
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
        for vendor in vendors:
            await store.approve_vendor(me["org_id"], vendor, by=me["id"])
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
    for frame in frames[1:]:
        assert "line_id" in frame, "every frame says whose it is, or that it is nobody's"
    assert any(frame.get("line_id") is None for frame in frames), (
        "discovery happens once for the whole review, not once per product line"
    )
    assert any(frame.get("line_id") for frame in frames), "and the work is per line"


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

    # Which unqualified part wins is the catalogue's business and changes with it. What is
    # under test is where the decision goes.
    assert gateway["proposal"] not in (None, NCP1117.mpn)
    assert gateway["conditional"] is True
    assert "quality" in gateway["roles"], "qualification is not engineering's to grant"

    question = next(
        frame for frame in frames
        if frame["type"] == "question" and frame["line_id"] == gateway["line_id"]
    )
    assert "quality" in question["roles"]
    assert gateway["proposal"] in question["text"]
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


def test_the_catalogue_is_searched_and_what_it_found_is_said():
    """The leg that lets a part nobody here has ever bought be considered at all."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id)

    review_wide = [
        frame["text"]
        for frame in run(go())
        if frame["type"] == "reasoning" and frame.get("line_id") is None
    ]
    said = " ".join(review_wide)

    # Not the sentence that says it is *about* to search — that one is emitted whether or
    # not the search returns anything, and this test passed with the catalogue leg removed
    # entirely before it asserted on the origin instead.
    assert review.CATALOGUE_ORIGIN in said, (
        "a candidate the distributor's catalogue produced, not just the promise of one"
    )
    assert "Trying" in said, "the shortlist is named before any board is touched"


def test_a_distributor_that_cannot_be_reached_is_said_out_loud(monkeypatch):
    """"We could not look" and "there was nothing there" are different answers, and only
    one of them is worth retrying. A dead network already turned a whole review into three
    silent "could not be sourced" columns once."""
    from continuity.api import review as review_api

    async def unreachable(_query, **_kwargs):
        raise RuntimeError("jlc_search: unreachable after 3 attempts")

    monkeypatch.setattr(review_api.sourcing, "find", unreachable)

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                return await frames_of(http, notice_id)

    frames = run(go())
    said = " ".join(
        frame["text"] for frame in frames
        if frame["type"] == "reasoning" and frame.get("line_id") is None
    )

    assert "could not be searched" in said
    assert any(frame["type"] == "line_done" for frame in frames), (
        "the review still finishes on what it has"
    )


# ── answering a decision ──────────────────────────────────────────────────────


async def a_pending_decision(store, http, notice_id, org_id, **body):
    await frames_of(http, notice_id, **body)
    decisions = await store.decisions_for_notice(notice_id, org_id)
    return {row["line_name"]: row for row in decisions}


def test_approving_puts_the_part_on_the_product_line():
    """The step the flow stopped at. A change request that never changes anything is a
    document, not a tool."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                answered = await http.post(
                    f"/decisions/{gateway['id']}",
                    json={"approve": True, "rationale": "Same package, 35 °C of headroom."},
                )
                bom = (await http.get(f"/lines/{gateway['line_id']}/bom")).json()
                line = (await http.get(f"/lines/{gateway['line_id']}")).json()
                return gateway, answered.json(), bom, line

    gateway, answered, bom, line = run(go())

    assert answered["state"] == "approved"
    fitted = {row["refdes"]: row["mpn"] for row in bom}
    assert fitted["u1"] == gateway["proposal"], "the substitute is on the board"
    assert line["revision"] == "Rev D", "a released design does not change under one revision"


def test_approving_records_who_signed_it_and_why():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                await http.post(
                    f"/decisions/{gateway['id']}",
                    json={"approve": True, "rationale": "Approved on the 2025 audit."},
                )
                return await store.approvals_for_line(gateway["line_id"], me["org_id"])

    approvals = run(go())

    assert len(approvals) == 1
    assert approvals[0]["user_email"] == "run@example.com"
    assert approvals[0]["rationale"] == "Approved on the 2025 audit."
    assert approvals[0]["revision"] == "Rev D"


def test_approving_writes_the_successful_precedent_that_was_never_written():
    """Open since precedents were built: rejections were recorded and successes were not,
    because a success needs the moment a substitution is *accepted* rather than proposed."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                return await store.worked_anywhere(
                    me["org_id"], f"eol|{AMS1117.mpn}|u1"
                )

    worked = run(go())

    assert [row["mpn"] for row in worked] == [TLV1117.mpn]


def test_a_desk_that_does_not_own_the_decision_is_refused():
    """The whole point of routing a decision. Who we buy from is procurement's alone, and
    an engineer has no standing to approve a source however good the part is.

    Qualification is deliberately not the case used here: `roles.py` addresses it to
    engineering *and* quality, so an engineer can answer it — see DEFERRED on whether that
    should need two signatures rather than either one.
    """

    async def go():
        async with a_store() as store:
            # A kept vendor list that approves nobody. Every part is then fine and from a
            # source procurement has not signed off.
            async with a_company(store, vendors=[]) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                assert gateway["gate_rule"] == "source_approval", "precondition"
                assert gateway["roles"] == ["procurement"]
                return await http.post(
                    f"/decisions/{gateway['id']}", json={"approve": True}
                )

    response = run(go())

    assert response.status_code == 403
    assert "procurement" in response.json()["detail"]


def test_a_decision_can_only_be_answered_once():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                first = await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                second = await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                return first, second

    first, second = run(go())

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already approved" in second.json()["detail"]


def test_declining_changes_nothing_on_the_board():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                answered = await http.post(
                    f"/decisions/{gateway['id']}",
                    json={"approve": False, "rationale": "Waiting for the second source."},
                )
                bom = (await http.get(f"/lines/{gateway['line_id']}/bom")).json()
                return answered.json(), bom

    answered, bom = run(go())

    assert answered["state"] == "declined"
    assert {row["refdes"]: row["mpn"] for row in bom}["u1"] == AMS1117.mpn


def test_another_organisations_decision_is_not_found():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
            ) as other:
                await other.post(
                    "/auth/register",
                    json={"email": "stranger@example.com", "password": "a-good-password"},
                )
                return await other.post(
                    f"/decisions/{gateway['id']}", json={"approve": True}
                )

    assert run(go()).status_code == 404


def test_the_run_writes_the_change_request_it_produced():
    """The packet is the deliverable. It used to be produced by a second pass over work the
    run had already done, and a run that stops at a decision would leave nothing to sign."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                await frames_of(http, notice_id, annual_volume=20_000)
                return (await http.get(f"/notices/{notice_id}/review")).json()

    requests = run(go())

    assert {request["line_name"] for request in requests} == {
        "Sensor node", "Gateway", "Cabinet controller"
    }
    gateway = next(r for r in requests if r["line_name"] == "Gateway")
    assert gateway["baseline_mpn"] == AMS1117.mpn, "what is fitted today"
    assert gateway["proposal"], "and what to do about it"
    assert any(
        alternative["rejected_because"] and "150" in alternative["rejected_because"]
        for alternative in gateway["alternatives"]
    ), "the sentence that killed the manufacturer's own recommendation"
    assert gateway["cost"]["annual_volume"] == 20_000
    assert gateway["approvals_required"], "and who has to sign it"


def test_the_applied_part_keeps_the_manufacturer_it_was_evaluated_as():
    """Applying used to resolve the proposal by part number alone, which is ambiguous —
    two manufacturers list TLV1117LV33DCYR — so the substitute landed on the bill with no
    manufacturer at all. The part that was evaluated is the part being applied."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                return (await http.get(f"/lines/{gateway['line_id']}/bom")).json()

    bom = run(go())
    fitted = {row["refdes"]: row for row in bom}

    assert fitted["u1"]["manufacturer"], "a bill row with no manufacturer is a row nobody can buy"
    assert fitted["u1"]["footprint"], "and production needs the land pattern"
