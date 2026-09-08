"""Memory read off the company's record rather than off a design run.

`memory_for_user` was built when a product line *was* a thread: parts came out of
`threads.bom` and every finding joined through `threads`. That is no longer where a
company's knowledge lives. A product line carries a bill of materials in `line_parts`
whether or not anyone ever ran a design in this tool, a notice retires a part, a decision
settles a substitution, an approval names who signed it, and a precedent records what was
already ruled out. None of that reaches the screen through a thread.

These tests are written against the record, so a company that has never opened the design
side still has a memory.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api.app import app
from continuity.api.store import Store
from continuity.notices import Notice

DB_URL = os.environ.get("CONTINUITY_TEST_DB")
database = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB to run memory tests")


@asynccontextmanager
async def a_store():
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=2, open=False) as pool:
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


async def _signed_in(email: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    await client.post("/auth/register", json={"email": email, "password": "a-good-password"})
    return client


def _part(memory: dict, mpn: str) -> dict:
    found = next((part for part in memory["parts"] if part["mpn"] == mpn), None)
    assert found is not None, f"{mpn} is not in memory: {[p['mpn'] for p in memory['parts']]}"
    return found


@database
def test_a_product_line_that_never_ran_a_design_still_has_a_memory():
    """The bill of materials is the company's record. A thread is not."""

    async def go():
        async with a_store() as store:
            client = await _signed_in("engineer@example.com")
            me = (await client.get("/auth/me")).json()
            line = await store.create_line(me["id"], me["org_id"], "Gateway")
            await store.save_bom_rows(
                line.id, me["id"], me["org_id"],
                [{"refdes": "U3", "mpn": "AMS1117-3.3", "manufacturer": "Advanced Monolithic"}],
            )
            return (await client.get("/memory")).json()

    memory = asyncio.run(go())
    part = _part(memory, "AMS1117-3.3")
    assert part["manufacturer"] == "Advanced Monolithic"
    assert [use["line_name"] for use in part["used_in"]] == ["Gateway"]


@database
def test_a_part_is_remembered_at_the_designator_it_sits_at():
    """"Where did I use this" is a reference designator, not just a product name."""

    async def go():
        async with a_store() as store:
            client = await _signed_in("engineer@example.com")
            me = (await client.get("/auth/me")).json()
            line = await store.create_line(me["id"], me["org_id"], "Gateway")
            await store.save_bom_rows(
                line.id, me["id"], me["org_id"],
                [
                    {"refdes": "U3", "mpn": "AMS1117-3.3"},
                    {"refdes": "U7", "mpn": "AMS1117-3.3"},
                ],
            )
            return (await client.get("/memory")).json()

    memory = asyncio.run(go())
    assert _part(memory, "AMS1117-3.3")["used_in"][0]["refdes"] == ["U3", "U7"]


@database
def test_one_part_across_three_boards_is_one_node_with_three_edges():
    async def go():
        async with a_store() as store:
            client = await _signed_in("engineer@example.com")
            me = (await client.get("/auth/me")).json()
            for name in ("Gateway", "Cabinet controller", "Sensor node"):
                line = await store.create_line(me["id"], me["org_id"], name)
                await store.save_bom_rows(
                    line.id, me["id"], me["org_id"], [{"refdes": "U3", "mpn": "AMS1117-3.3"}]
                )
            return (await client.get("/memory")).json()

    memory = asyncio.run(go())
    assert len(_part(memory, "AMS1117-3.3")["used_in"]) == 3


@database
def test_a_retired_part_carries_the_notice_that_retired_it_and_the_line_it_was_read_from():
    """A notice is evidence. Remembering that a part is going away without remembering
    which document said so, in its own words, is remembering a rumour."""

    async def go():
        async with a_store() as store:
            client = await _signed_in("engineer@example.com")
            me = (await client.get("/auth/me")).json()
            line = await store.create_line(me["id"], me["org_id"], "Gateway")
            await store.save_bom_rows(
                line.id, me["id"], me["org_id"], [{"refdes": "U3", "mpn": "AMS1117-3.3"}]
            )
            await store.save_notice(
                me["org_id"], me["id"],
                Notice(
                    mpn="AMS1117-3.3",
                    mpn_line="Affected part: AMS1117-3.3 (SOT-223)",
                    manufacturer="Advanced Monolithic Systems",
                    effective_date="2027-03-31",
                    effective_date_line="Last order date: 31 March 2027",
                    replacement_mpn="NCP1117ST33T3G",
                    replacement_line="Recommended replacement: NCP1117ST33T3G",
                    reason="End of life",
                ),
                source="PCN-2026-114.pdf",
            )
            return (await client.get("/memory")).json()

    memory = asyncio.run(go())
    part = _part(memory, "AMS1117-3.3")
    assert part["retirement"], "the part a notice named is retired in memory"
    assert part["retirement"]["mpn_line"] == "Affected part: AMS1117-3.3 (SOT-223)"
    assert part["retirement"]["replacement_mpn"] == "NCP1117ST33T3G"
    assert part["retirement"]["source"] == "PCN-2026-114.pdf"


@database
def test_a_rejection_is_remembered_against_the_board_it_happened_on():
    """The asymmetry `precedents` was built with has to survive the read.

    NCP1117 cooking the gateway says nothing about a board running 20 °C cooler, so the
    rejection names its board and stays there.
    """

    async def go():
        async with a_store() as store:
            client = await _signed_in("engineer@example.com")
            me = (await client.get("/auth/me")).json()
            gateway = await store.create_line(me["id"], me["org_id"], "Gateway")
            sensor = await store.create_line(me["id"], me["org_id"], "Sensor node")
            for line in (gateway, sensor):
                await store.save_bom_rows(
                    line.id, me["id"], me["org_id"], [{"refdes": "U3", "mpn": "NCP1117ST33T3G"}]
                )
            await store.record_precedents(
                me["org_id"], gateway.id,
                [{
                    "signature": "thermal:junction",
                    "mpn": "NCP1117ST33T3G",
                    "outcome": "rejected",
                    "detail": "159 °C against a 150 °C limit",
                }],
            )
            return (await client.get("/memory")).json()

    memory = asyncio.run(go())
    history = _part(memory, "NCP1117ST33T3G")["history"]
    rejections = [item for item in history if item["kind"] == "rejected"]
    assert len(rejections) == 1, "one board rejected it, not both"
    assert rejections[0]["line_name"] == "Gateway"
    assert rejections[0]["detail"] == "159 °C against a 150 °C limit"


@database
def test_an_approved_substitution_is_remembered_with_who_signed_it():
    async def go():
        async with a_store() as store:
            client = await _signed_in("engineer@example.com")
            me = (await client.get("/auth/me")).json()
            line = await store.create_line(me["id"], me["org_id"], "Gateway")
            await store.save_bom_rows(
                line.id, me["id"], me["org_id"], [{"refdes": "U3", "mpn": "TLV1117LV33DCYR"}]
            )
            await store.record_approval(
                org_id=me["org_id"],
                line_id=line.id,
                user_id=me["id"],
                user_email="engineer@example.com",
                roles=["engineering"],
                rule="part_qualification",
                subject="U3",
                mpn="TLV1117LV33DCYR",
                revision="Rev D",
                rationale="35 °C of thermal margin on this board.",
            )
            return (await client.get("/memory")).json()

    memory = asyncio.run(go())
    history = _part(memory, "TLV1117LV33DCYR")["history"]
    approvals = [item for item in history if item["kind"] == "approved"]
    assert len(approvals) == 1
    assert approvals[0]["by"] == "engineer@example.com"
    assert approvals[0]["rationale"] == "35 °C of thermal margin on this board."


@database
def test_another_company_sees_none_of_it():
    async def go():
        async with a_store() as store:
            mine = await _signed_in("mine@example.com")
            theirs = await _signed_in("theirs@example.com")
            me = (await mine.get("/auth/me")).json()
            line = await store.create_line(me["id"], me["org_id"], "Gateway")
            await store.save_bom_rows(
                line.id, me["id"], me["org_id"], [{"refdes": "U3", "mpn": "AMS1117-3.3"}]
            )
            return (await theirs.get("/memory")).json()

    assert asyncio.run(go())["parts"] == []


# ── what a notice makes of a part's lifecycle ────────────────────────────────
#
# Pure, so these need no database. The distinction is the one a buyer acts on: a part
# whose last order date has passed cannot be bought at any price, and one whose date is
# still ahead can be bought today and must not go into anything new.


def test_a_last_order_date_still_ahead_makes_a_part_not_recommended():
    from datetime import date

    from continuity.api.recall import lifecycle_from

    assert lifecycle_from({"effective_date": "2027-03-31"}, date(2026, 9, 8)) == "nrnd"


def test_a_last_order_date_already_passed_makes_a_part_obsolete():
    from datetime import date

    from continuity.api.recall import lifecycle_from

    assert lifecycle_from({"effective_date": date(2026, 3, 31)}, date(2026, 9, 8)) == "obsolete"


def test_a_notice_that_withholds_its_date_still_retires_the_part():
    """`PRELIMINARY` notices state no date. That is not a reason to call the part active."""
    from datetime import date

    from continuity.api.recall import lifecycle_from

    assert lifecycle_from({"effective_date": None}, date(2026, 9, 8)) == "nrnd"


def test_a_stated_lifecycle_is_not_overwritten_by_a_notice():
    """The notice fills a gap. It does not argue with a source that already answered.

    Fed through `thread_parts`, which is where a stated lifecycle actually comes from.
    An earlier version of this test put one on a `bom` row, and `line_parts` has no
    lifecycle column, so it was asserting against a row shape the query cannot return.
    """
    from datetime import date

    from continuity.api.recall import compose

    composed = compose(
        lines=[],
        bom=[{"line_id": "l1", "line_name": "Gateway", "mpn": "PART", "manufacturer": None,
              "refdes": ["U1"]}],
        thread_parts=[{"line_id": "l1", "line_name": "Gateway", "mpn": "PART",
                       "manufacturer": None, "lifecycle": "active"}],
        notices=[{"mpn": "PART", "mpn_line": "Affected part: PART", "effective_date": None}],
        precedents=[], approvals=[], decisions=[], findings=[],
        facts={}, part_limit=10, today=date(2026, 9, 8),
    )
    assert composed["parts"][0]["lifecycle"] == "active"


# ── one event per thing that happened ─────────────────────────────────────────


def _composed(**overrides):
    from datetime import date

    from continuity.api.recall import compose

    payload = dict(
        lines=[], bom=[], notices=[], precedents=[], approvals=[], decisions=[],
        thread_parts=[], findings=[], facts={}, part_limit=10, today=date(2026, 9, 8),
    )
    payload.update(overrides)
    return compose(**payload)


APPROVED_DECISION = {
    "proposal": "NCP1117ST33T3G", "retiring": "AMS1117-3.3", "line_id": "l1",
    "line_name": "Cabinet controller", "state": "approved", "roles": ["engineering"],
    "gate_rule": "part_qualification", "slot_id": "u1",
    "detail": "Clears every check on this board, with 11 °C to spare.",
}
ITS_APPROVAL = {
    "mpn": "NCP1117ST33T3G", "line_id": "l1", "line_name": "Cabinet controller",
    "user_email": "engineer@northwind.example", "roles": ["engineering"],
    "rule": "part_qualification", "subject": "u1", "revision": "Rev D",
    "rationale": "Clears every check on this board, with 11 °C to spare.",
}


def test_an_approved_decision_is_remembered_once_not_twice():
    """Answering a decision writes both rows, and they are one event.

    `api/review.answer` settles the decision and records the approval in the same request,
    so a settled decision and its approval are two records of one signature. Memory showed
    both, which read on screen as the Cabinet controller having been approved twice by two
    different-looking authorities. The approval is the fuller record: it names the person.
    """
    composed = _composed(decisions=[APPROVED_DECISION], approvals=[ITS_APPROVAL])
    history = composed["parts"][0]["history"]
    approvals = [event for event in history if event["kind"] == "approved"]
    assert len(approvals) == 1, history
    assert approvals[0]["by"] == "engineer@northwind.example"


def test_a_decision_nobody_has_answered_is_still_waiting():
    composed = _composed(decisions=[{**APPROVED_DECISION, "state": "pending"}])
    assert [event["kind"] for event in composed["parts"][0]["history"]] == ["awaiting"]


def test_a_declined_decision_is_remembered_because_nothing_else_records_it():
    """A refusal writes no approval, so dropping it would lose the fact that someone said no."""
    composed = _composed(decisions=[{**APPROVED_DECISION, "state": "declined"}])
    events = composed["parts"][0]["history"]
    assert [event["kind"] for event in events] == ["declined"]
    assert events[0]["line_name"] == "Cabinet controller"


# ── a citation is a quotation, or it is not shown as one ──────────────────────


def test_a_fact_with_a_quoted_line_carries_it_as_a_quote():
    from continuity.api.recall import fact_from

    read = fact_from({
        "field": "theta_ja", "value": "60.0",
        "source": "datasheet — 1000 Sq. mm / 1000 Sq. mm / 1000 Sq. mm — 60 °C/W",
    })
    assert read["verified"] is True
    assert read["quote"] == "1000 Sq. mm / 1000 Sq. mm / 1000 Sq. mm — 60 °C/W"


def test_a_verified_fact_with_no_quotable_line_carries_no_quote():
    """`datasheet — source unavailable` is a marker, not a quotation.

    It was rendered on screen inside quotation marks, so ten of AMS1117-3.3's eleven facts
    appeared to be citing a datasheet line that said the source was unavailable. A reading
    without its line is still a verified reading, and it has to say so without dressing the
    marker up as evidence.
    """
    from continuity.api.recall import fact_from
    from continuity.parts import dossier

    read = fact_from({"field": "vmax", "value": "15.0", "source": dossier.verified_source(None)})
    assert read["verified"] is True
    assert read["quote"] is None


def test_an_unverified_facts_source_is_kept_as_it_is():
    from continuity.api.recall import fact_from

    read = fact_from({"field": "vmax", "value": "15.0", "source": "JLCPCB listing"})
    assert read["verified"] is False and read["quote"] == "JLCPCB listing"
