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
from continuity.api import store as store_module
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
async def a_company(store, *, qualified=QUALIFIED, vendors=("JLCPCB",), roles=None):
    """Three products carrying the retired part, and the two standing lists."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120.0
    ) as http:
        await http.post(
            "/auth/register", json={"email": "run@example.com", "password": "a-good-password"}
        )
        me = (await http.get("/auth/me")).json()
        # Every desk, on one person. A substitution now needs a signature from each
        # department that examined it, and these tests are about the substitution rather
        # than about the routing — which has its own tests below, with one desk each.
        await store.add_user_to_organisation(
            me["id"], me["org_id"], list(roles or store_module.ROLES)
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
        # `qualified=None` means the company keeps no approved-manufacturer list at all, so
        # `part_qualification` never runs and quality never looks at the change. Different
        # from an empty list, which keeps one and approves nobody.
        await store.keep_lists(me["org_id"], aml=qualified is not None, avl=True)
        for mpn in qualified or ():
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
    assert set(gateway["roles"]) >= {"engineering", "procurement", "production"}, (
        "nothing failed, and every department that examined the change still signs it"
    )


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


def test_an_engineer_cannot_apply_a_change_procurement_has_not_signed():
    """The whole point of routing a decision. Who we buy from is procurement's alone, and
    an engineer has no standing to approve a source however good the part is.

    **Changed 10 Sep, and the guarantee got stronger.** This used to assert a 403: the
    decision belonged to procurement and an engineer could not touch it. Now every
    department that examined the change signs it, so an engineer *can* sign — for
    engineering — and the change still does not happen, because the desk that owns the
    failure has not signed. The protection moved from *you may not answer* to *your answer
    is not enough*, which is what a change board actually does.

    Qualification is deliberately not the case used here: `roles.py` addresses it to
    engineering *and* quality, and both signing it is exactly the point of the test below.
    """

    async def go():
        async with a_store() as store:
            # A kept vendor list that approves nobody. Every part is then fine and from a
            # source procurement has not signed off.
            async with a_company(store, vendors=[], roles=["engineering"]) as (
                http, me, notice_id,
            ):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                assert gateway["gate_rule"] == "source_approval", "precondition"
                assert "procurement" in gateway["roles"]
                answered = await http.post(
                    f"/decisions/{gateway['id']}", json={"approve": True}
                )
                bom = (await http.get(f"/lines/{gateway['line_id']}/bom")).json()
                line = (await http.get(f"/lines/{gateway['line_id']}")).json()
                return gateway, answered.json(), bom, line

    gateway, answered, bom, line = run(go())

    assert answered["state"] == "pending", "signed, and not enough"
    assert answered["signed"] == ["engineering"]
    assert "procurement" in answered["outstanding"]

    fitted = {row["refdes"]: row["mpn"] for row in bom}
    assert fitted["u1"] != gateway["proposal"], "the board did not change"
    assert line["revision"] == "Rev C", "and neither did the revision"


def test_a_desk_that_examined_nothing_is_refused_outright():
    """The 403 still exists, for somebody with no standing at all.

    A company that keeps no approved-manufacturer list never runs `part_qualification`, so
    quality never looked at this change and has nothing to sign. 403 and not 404, because
    the caller can already see the decision.
    """

    async def go():
        async with a_store() as store:
            async with a_company(store, qualified=None, roles=["quality"]) as (
                http, me, notice_id,
            ):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                assert "quality" not in gateway["roles"], "precondition: quality did not look"
                return await http.post(
                    f"/decisions/{gateway['id']}", json={"approve": True}
                )

    response = run(go())

    assert response.status_code == 403
    assert "quality" in response.json()["detail"], "name what they hold"


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


# ── one product line, on its own page ─────────────────────────────────────────


def test_a_review_can_be_narrowed_to_one_product_line():
    """The product line page runs the same review about itself.

    Same endpoint, same engine, same frames — the page just says which board it is asking
    about. A second endpoint for one line would be a second place for the review to mean
    something slightly different, and the two would drift.
    """

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                every = await frames_of(http, notice_id)
                gateway = next(
                    line["line_id"]
                    for line in every[0]["lines"]
                    if line["name"] == "Gateway"
                )
                return gateway, await frames_of(http, notice_id, line_id=gateway)

    gateway, frames = run(go())

    started = frames[0]
    assert [line["name"] for line in started["lines"]] == ["Gateway"]
    # `review_started` carries no `line_id` at all: it is about the review, not a board.
    assert {frame["line_id"] for frame in frames if frame.get("line_id")} == {gateway}
    # It still ends, and it still ends with an answer rather than merely stopping.
    assert [frame for frame in frames if frame["type"] == "line_done"]


def test_narrowing_to_a_line_the_notice_does_not_reach_is_refused():
    """Silently checking every line instead would be the worst of the three answers: the
    page would fill with two other products' traces and read as though it were its own."""

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, notice_id):
                spare = (await http.post("/lines", json={"name": "Nothing fitted"})).json()
                return await http.post(
                    f"/notices/{notice_id}/review/run",
                    json={"candidates": [], "line_id": spare["id"]},
                )

    response = run(go())

    assert response.status_code == 409
    assert "this product line" in response.json()["detail"]


# ── a finished review, read back ──────────────────────────────────────────────


def test_a_finished_review_can_be_replayed_from_what_it_recorded():
    """A design run is replayable and a review was not.

    Every frame a design run emits is stored; a review streamed its reasoning and kept only
    its conclusions, so reopening the product line afterwards showed a part number and a
    date. `decisions.document` already holds every candidate and the sentence that settled
    it — this is the same account, in the frames the client renders.
    """

    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, me, notice_id):
                await frames_of(http, notice_id)
                gateway = next(
                    row for row in await store.decisions_for_notice(notice_id, me["org_id"])
                    if row["line_name"] == "Gateway"
                )
                line_id = gateway["line_id"]
                return (await http.get(f"/lines/{line_id}/reviews")).json()

    reviews = run(go())

    assert len(reviews) == 1
    frames = reviews[0]["frames"]
    said = [frame["text"] for frame in frames if frame["type"] == "reasoning"]
    checks = [frame for frame in frames if frame["type"] == "check"]

    assert said[0] == f"{AMS1117.mpn} is going end of life."
    assert any("sits at U1" in line for line in said)
    # The candidate that lost, with the sentence that killed it, is the whole point.
    assert any(NCP1117.mpn in line for line in said)
    assert checks, "the winner's verdicts travel with the trace"
    assert all(check["status"] for check in checks)

    # A finished run ends with its answer. Without this frame the replay reached `done`
    # carrying no proposal, and a board that shipped rendered as NO VIABLE PART.
    ending = frames[-1]
    assert ending["type"] == "line_done"
    assert ending["proposal"] == reviews[0]["proposal"]
    assert ending["reason"]
    # The incumbent is a baseline, not something the run considered fitting.
    assert not any(line == f"Trying {AMS1117.mpn}." for line in said)


def test_a_line_that_has_never_been_reviewed_replays_nothing():
    async def go():
        async with a_store() as store:
            async with a_company(store) as (http, _me, _notice_id):
                spare = (await http.post("/lines", json={"name": "Never reviewed"})).json()
                return (await http.get(f"/lines/{spare['id']}/reviews")).json()

    assert run(go()) == []


def test_a_decision_waits_until_every_department_has_signed():
    """The change board, in one test.

    Each desk signs for itself and the bill does not move until the last one does. Until
    10 September this was first-response: `roles.py` addresses `part_qualification` to
    engineering *and* quality with the words *"it needs both"*, and whoever answered first
    settled it.
    """

    async def go():
        async with a_store() as store:
            async with a_company(store, roles=["engineering"]) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                required = list(gateway["roles"])

                first = (
                    await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                ).json()
                mid_bom = (await http.get(f"/lines/{gateway['line_id']}/bom")).json()

                # The same person, now holding the rest. In the demo world these are four
                # people; here it is one client, and the endpoint only ever sees the desks
                # a caller holds.
                await store.add_user_to_organisation(
                    me["id"], me["org_id"], list(store_module.ROLES)
                )
                last = (
                    await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                ).json()
                bom = (await http.get(f"/lines/{gateway['line_id']}/bom")).json()
                line = (await http.get(f"/lines/{gateway['line_id']}")).json()
                signatures = await store.approvals_for_decision(gateway["id"], me["org_id"])
                return required, first, mid_bom, last, bom, line, signatures, gateway

    required, first, mid_bom, last, bom, line, signatures, gateway = run(go())

    assert len(required) > 1, "precondition: more than one desk examined this change"

    assert first["state"] == "pending"
    assert first["signed"] == ["engineering"]
    assert set(first["outstanding"]) == set(required) - {"engineering"}
    assert {row["refdes"]: row["mpn"] for row in mid_bom}["u1"] != gateway["proposal"], (
        "one signature does not change a released design"
    )

    assert last["state"] == "approved"
    assert last["outstanding"] == []
    assert {row["refdes"]: row["mpn"] for row in bom}["u1"] == gateway["proposal"]
    assert line["revision"] == "Rev D"

    # Two rows, and both name the revision the change produced rather than the one it left.
    assert len(signatures) == 2
    assert all(row["roles"] for row in signatures)
    assert {role for row in signatures for role in row["roles"]} == set(required)


def test_a_desk_cannot_sign_the_same_decision_twice():
    """**Replaces the old `a decision can only be answered once`**, which asserted that the
    second answer of any kind was refused. A decision now takes several answers on purpose;
    what it must not take is the same desk answering twice, which would let one person
    complete a set on their own."""

    async def go():
        async with a_store() as store:
            async with a_company(store, roles=["engineering"]) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                first = await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                second = await http.post(f"/decisions/{gateway['id']}", json={"approve": True})
                return first, second

    first, second = run(go())

    assert first.json()["state"] == "pending"
    assert second.status_code == 409
    assert "already signed" in second.json()["detail"]
    assert "waiting on" in second.json()["detail"], "and say who it is waiting for"


def test_one_desk_declining_stops_the_change_without_waiting_for_the_others():
    """A rejection is decisive where an approval is not. A change board does not hold a
    refusal open until everybody else has agreed with it."""

    async def go():
        async with a_store() as store:
            async with a_company(store, roles=["engineering"]) as (http, me, notice_id):
                pending = await a_pending_decision(store, http, notice_id, me["org_id"])
                gateway = pending["Gateway"]
                answered = await http.post(
                    f"/decisions/{gateway['id']}",
                    json={"approve": False, "rationale": "Not this quarter."},
                )
                bom = (await http.get(f"/lines/{gateway['line_id']}/bom")).json()
                return gateway, answered.json(), bom

    gateway, answered, bom = run(go())

    assert answered["state"] == "declined"
    assert {row["refdes"]: row["mpn"] for row in bom}["u1"] != gateway["proposal"]


def test_every_desk_can_see_what_is_waiting_on_it():
    """The queue that did not exist. Three of the four desks that must sign a substitution
    had no way to find it: the decision lived on a product line's page, and a person at the
    procurement desk would have had to know which product line to open."""

    async def go():
        async with a_store() as store:
            async with a_company(store, roles=["procurement"]) as (http, me, notice_id):
                await a_pending_decision(store, http, notice_id, me["org_id"])
                mine = (await http.get("/decisions")).json()

                # Sign one of them, and it stops being outstanding for this desk.
                signed = await http.post(
                    f"/decisions/{mine[0]['id']}", json={"approve": True}
                )
                after = (await http.get("/decisions")).json()
                return mine, signed.json(), after

    mine, signed, after = run(go())

    assert len(mine) == 3, "three affected product lines, three decisions"
    first = mine[0]
    assert first["line_name"] and first["proposal"] and first["retiring"]
    assert "procurement" in first["roles"]
    assert first["mine"] == ["procurement"], "what this reader still owes"
    assert first["signed"] == []

    assert signed["state"] == "pending"
    stayed = {row["id"]: row for row in after}
    assert stayed[first["id"]]["signed"] == ["procurement"]
    assert stayed[first["id"]]["mine"] == [], "signed, so nothing left for this desk"


def test_a_desk_with_nothing_waiting_gets_an_empty_list_rather_than_a_refusal():
    """A company that keeps no approved-manufacturer list never runs `part_qualification`,
    so quality has nothing to sign. Nothing waiting is not an error."""

    async def go():
        async with a_store() as store:
            async with a_company(store, qualified=None, roles=["quality"]) as (
                http, me, notice_id,
            ):
                await a_pending_decision(store, http, notice_id, me["org_id"])
                return await http.get("/decisions")

    response = run(go())

    assert response.status_code == 200
    assert response.json() == []
