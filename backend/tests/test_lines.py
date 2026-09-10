"""Ownership: whose lines, whose threads, whose board.

Skipped unless `CONTINUITY_TEST_DB` is set.

Two groups of tests here, and they fail very differently.

**The ownership ones fail silently in production.** `/resume` and `/export` used to take
a thread id and trust it. With one user that is indistinguishable from correct; with two
it hands over someone else's board. Every one of these asserts a 404 rather than a 403,
because a 403 confirms the thread exists.

**The restart one fails invisibly on the client.** A resumed stream that starts its
numbering again is not rejected — the client drops every frame at or below its high-water
mark, so the run renders as a hang with nothing in the log. `test_resume_survives_a_restart`
is the reason `last_seq` is persisted at all.
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
from continuity.api import events
from continuity.api.store import Store

DB_URL = os.environ.get("CONTINUITY_TEST_DB")

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="set CONTINUITY_TEST_DB to run the ownership tests"
)

UNRESOLVED = "solar powered weather station with a sensor"
"""Interrupts on the supply question, so a run can be paused and resumed."""

DEMO = "temp and humidity sensor, wifi and ble, usb-c powered with li-ion backup, small oled"


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
            await conn.execute("TRUNCATE users, organisations, sessions, product_lines, threads CASCADE")

        previous = app.state.store
        app.state.store = store
        app_module.STREAMS.clear()
        app_module.BOMS.clear()
        try:
            yield store
        finally:
            app.state.store = previous


def a_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
    )


@asynccontextmanager
async def signed_in(email: str = "sparsh@example.com"):
    """A client with an account and its session cookie already held."""
    async with a_client() as http:
        await http.post("/auth/register", json={"email": email, "password": "a-good-password"})
        yield http


async def frames_of(http: httpx.AsyncClient, path: str, payload: dict) -> list[dict]:
    async with http.stream("POST", path, json=payload) as response:
        assert response.status_code == 200, await response.aread()
        return [
            json.loads(line[6:])
            async for line in response.aiter_lines()
            if line.startswith("data: ")
        ]


# ── the routes need an account ────────────────────────────────────────────────


def test_lines_need_an_account():
    async def go():
        async with a_store():
            async with a_client() as http:
                return await http.get("/lines")

    assert run(go()).status_code == 401


def test_designing_needs_an_account():
    async def go():
        async with a_store():
            async with a_client() as http:
                return await http.post("/design", json={"prompt": DEMO, "line_id": "x"})

    assert run(go()).status_code == 401


# ── lines ──────────────────────────────────────────────────────────────────


def test_a_created_line_is_listed():
    async def go():
        async with a_store():
            async with signed_in() as http:
                created = await http.post("/lines", json={"name": "Weather station"})
                return created, await http.get("/lines")

    created, listed = run(go())
    assert created.status_code == 201
    assert [p["name"] for p in listed.json()] == ["Weather station"]


def test_lines_list_for_their_owner_only():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                await mine.post("/lines", json={"name": "Mine"})
            async with signed_in("theirs@example.com") as theirs:
                await theirs.post("/lines", json={"name": "Theirs"})
                return await theirs.get("/lines")

    assert [p["name"] for p in run(go()).json()] == ["Theirs"]


def test_another_users_line_is_a_404():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
            async with signed_in("theirs@example.com") as theirs:
                return await theirs.get(f"/lines/{line['id']}")

    assert run(go()).status_code == 404


def test_a_line_cannot_be_deleted_by_someone_else():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
                async with signed_in("theirs@example.com") as theirs:
                    stolen = await theirs.delete(f"/lines/{line['id']}")
                return stolen, await mine.get("/lines")

    stolen, still_mine = run(go())
    assert stolen.status_code == 404
    assert len(still_mine.json()) == 1


# ── a run belongs to a line, and to a person ───────────────────────────────


def test_a_run_records_a_thread_against_its_line():
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(http, "/design", {"prompt": DEMO, "line_id": line["id"]})
                me = (await http.get("/auth/me")).json()
                return await store.thread_for_user(frames[0]["thread_id"], me["org_id"])

    thread = run(go())
    assert thread is not None
    assert thread.prompt == DEMO
    assert thread.status == "done"
    assert thread.bom, "the finished board should have been recorded"


def test_designing_without_a_line_uses_one_owned_scratch_line():
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                me = (await http.get("/auth/me")).json()
                first = await frames_of(http, "/design", {"prompt": DEMO})
                second = await frames_of(http, "/design", {"prompt": DEMO})
                lines = (await http.get("/lines")).json()
                scratch = [line for line in lines if line["name"] == "Scratch designs"]
                threads = await store.threads_for_line(scratch[0]["id"], me["org_id"])
                return first, second, scratch, threads, me

    first, second, scratch, threads, me = run(go())
    assert len(scratch) == 1, "a second call must not create a second scratch line"
    assert {thread.id for thread in threads} == {first[0]["thread_id"], second[0]["thread_id"]}
    assert all(thread.user_id == me["id"] for thread in threads)
    assert all(thread.line_id == scratch[0]["id"] for thread in threads)


def test_designing_into_another_users_line_is_a_404():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
            async with signed_in("theirs@example.com") as theirs:
                return await theirs.post(
                    "/design", json={"prompt": DEMO, "line_id": line["id"]}
                )

    assert run(go()).status_code == 404


def test_another_users_thread_cannot_be_resumed():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
                frames = await frames_of(
                    mine, "/design", {"prompt": UNRESOLVED, "line_id": line["id"]}
                )
                thread_id = frames[0]["thread_id"]
            async with signed_in("theirs@example.com") as theirs:
                return await theirs.post(
                    "/resume", json={"thread_id": thread_id, "answer": "USB-C 5V"}
                )

    assert run(go()).status_code == 404


def test_another_users_board_cannot_be_exported():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
                frames = await frames_of(
                    mine, "/design", {"prompt": DEMO, "line_id": line["id"]}
                )
                thread_id = frames[0]["thread_id"]
                mine_export = await mine.get(f"/export/{thread_id}.csv")
            async with signed_in("theirs@example.com") as theirs:
                return mine_export, await theirs.get(f"/export/{thread_id}.csv")

    owned, stolen = run(go())
    assert owned.status_code == 200
    assert stolen.status_code == 404


# ── the point of persisting anything ──────────────────────────────────────────


def test_resume_survives_a_restart():
    """Clearing STREAMS is what a process restart looks like from the database's side."""

    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                first = await frames_of(
                    http, "/design", {"prompt": UNRESOLVED, "line_id": line["id"]}
                )
                thread_id = first[0]["thread_id"]

                app_module.STREAMS.clear()  # the process died here

                second = await frames_of(
                    http, "/resume", {"thread_id": thread_id, "answer": "USB-C 5V"}
                )
                return first, second

    first, second = run(go())
    assert first[-1]["type"] == "question"
    assert second[0]["seq"] == first[-1]["seq"] + 1, "the client drops anything it has seen"
    assert len({f["seq"] for f in first + second}) == len(first + second)
    assert second[-1]["type"] == "done"


def test_a_paused_run_is_recorded_as_awaiting():
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(
                    http, "/design", {"prompt": UNRESOLVED, "line_id": line["id"]}
                )
                me = (await http.get("/auth/me")).json()
                return await store.thread_for_user(frames[0]["thread_id"], me["org_id"])

    thread = run(go())
    assert thread.status == "awaiting"
    assert thread.last_seq >= 0


# ── onboarding ────────────────────────────────────────────────────────────────


def test_a_finished_run_records_the_engines_own_summary():
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(
                    http, "/design", {"prompt": DEMO, "line_id": line["id"]}
                )
                me = (await http.get("/auth/me")).json()
                thread = await store.thread_for_user(frames[0]["thread_id"], me["org_id"])
                done = next(f for f in frames if f["type"] == "done")
                return thread.summary, done["summary"]

    stored, emitted = run(go())
    assert stored == emitted, "stored verbatim, never recomputed"
    assert stored["slots"] == stored["placed"], "the demo board is complete"


def test_the_threads_endpoint_exposes_the_summary():
    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                await frames_of(http, "/design", {"prompt": DEMO, "line_id": line["id"]})
                return await http.get(f"/lines/{line['id']}/threads")

    threads = run(go()).json()
    assert len(threads) == 1
    assert threads[0]["summary"]["conflicts_resolved"] >= 0
    assert threads[0]["status"] == "done"


def test_a_paused_run_has_no_summary_to_report():
    """A summary appears only when the engine has actually finished a board."""

    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                await frames_of(
                    http, "/design", {"prompt": UNRESOLVED, "line_id": line["id"]}
                )
                return await http.get(f"/lines/{line['id']}/threads")

    threads = run(go()).json()
    assert threads[0]["status"] == "awaiting"
    assert threads[0]["summary"] is None


# ── reopening a completed board ──────────────────────────────────────────────


def test_a_finished_thread_hydrates_its_checkpointed_board():
    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(
                    http, "/design", {"prompt": DEMO, "line_id": line["id"]}
                )
                board = await http.get(f"/threads/{frames[0]['thread_id']}/board")
                return board, frames

    board, frames = run(go())
    body = board.json()

    assert board.status_code == 200
    assert body["status"] == "done"
    assert body["checkpoint"] == "available"
    assert len(body["slots"]) == 4
    assert all(slot["part"] is not None for slot in body["slots"])
    assert body["edges"]
    assert all(edge["status"] in {"pass", "conflict", "unchecked"} for edge in body["edges"])
    # Restored with the board, not only announced during the run: without it the client has
    # no node for a supply edge to start from and drops every one of them, so a reopened
    # line would show its regulator floating again.
    assert body["supply"]["id"] == "__supply"
    assert body["supply"]["voltage"] > 0
    assert {edge["from"] for edge in body["edges"]} & {"__supply"}
    assert body["bom"]["rows"] == next(frame["rows"] for frame in frames if frame["type"] == "bom")
    assert body["summary"] == next(frame["summary"] for frame in frames if frame["type"] == "done")


def test_a_finished_thread_hydrates_its_trace_in_order_without_bom_frames():
    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(http, "/design", {"prompt": DEMO, "line_id": line["id"]})
                board = await http.get(f"/threads/{frames[0]['thread_id']}/board")
                return board, frames

    board, frames = run(go())
    assert [event["seq"] for event in board.json()["trace"]] == sorted(
        event["seq"] for event in board.json()["trace"]
    )
    assert not [event for event in board.json()["trace"] if event["type"] == "bom"]
    assert board.json()["trace"] == [event for event in frames if event["type"] != "bom"]


def test_an_awaiting_thread_hydrates_its_board_trace_and_real_pending_question():
    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(
                    http, "/design", {"prompt": UNRESOLVED, "line_id": line["id"]}
                )
                board = await http.get(f"/threads/{frames[0]['thread_id']}/board")
                return board, frames

    board, frames = run(go())
    body = board.json()
    question = frames[-1]
    assert body["status"] == "awaiting"
    assert body["resumable"] is True

    # `UNRESOLVED` stops at `clarify`, which runs *before* `plan` — so there is no board
    # yet, and saying so is different from saying the board could not be read. What has to
    # survive is the question, because it is the only thing the user can act on.
    assert body["checkpoint"] == "not_planned"
    assert body["slots"] == []
    assert body["trace"][-1] == question
    assert body["question"] == question


def test_an_abandoned_thread_hydrates_its_board_trace_and_is_resumable():
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(http, "/design", {"prompt": DEMO, "line_id": line["id"]})
                me = (await http.get("/auth/me")).json()
                thread = await store.thread_for_user(frames[0]["thread_id"], me["org_id"])
                await store.save_progress(thread.id, thread.last_seq, "abandoned")
                return await http.get(f"/threads/{thread.id}/board")

    body = run(go()).json()
    assert body["status"] == "abandoned"
    assert body["slots"]
    assert body["trace"]
    assert body["resumable"] is True


def test_hydrated_parts_use_the_event_part_serialiser():
    async def go():
        async with a_store():
            async with signed_in() as http:
                line = (await http.post("/lines", json={"name": "P"})).json()
                frames = await frames_of(
                    http, "/design", {"prompt": DEMO, "line_id": line["id"]}
                )
                board = await http.get(f"/threads/{frames[0]['thread_id']}/board")
                checkpoint = await app.state.graph.aget_state(
                    {"configurable": {"thread_id": frames[0]["thread_id"]}}
                )
                return board, checkpoint.values["slots"]

    board, slots = run(go())
    expected = {
        slot_id: events._part(slot.part)
        for slot_id, slot in slots.items()
        if slot.part is not None
    }

    assert board.status_code == 200
    assert {slot["id"]: slot["part"] for slot in board.json()["slots"]} == expected


def test_another_users_thread_board_is_a_404():
    async def go():
        async with a_store():
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
                frames = await frames_of(
                    mine, "/design", {"prompt": DEMO, "line_id": line["id"]}
                )
            async with signed_in("theirs@example.com") as theirs:
                return await theirs.get(f"/threads/{frames[0]['thread_id']}/board")

    assert run(go()).status_code == 404


def test_an_unknown_thread_board_is_a_404():
    async def go():
        async with a_store():
            async with signed_in() as http:
                return await http.get("/threads/does-not-exist/board")

    assert run(go()).status_code == 404


def test_a_running_thread_is_not_hydrated():
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                me = (await http.get("/auth/me")).json()
                line = await store.create_line(me["id"], me["org_id"], "P")
                await store.create_thread("still-running", line.id, me["id"], me["org_id"], "A board")
                return await http.get("/threads/still-running/board")

    response = run(go())

    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "summary": None,
        "slots": [],
        "edges": [],
        "bom": None,
        "checkpoint": "not_loaded",
        "trace": [],
        "question": None,
        "resumable": False,
    }


def test_another_users_thread_cannot_be_continued():
    async def go():
        async with a_store() as store:
            async with signed_in("mine@example.com") as mine:
                line = (await mine.post("/lines", json={"name": "Mine"})).json()
                frames = await frames_of(mine, "/design", {"prompt": DEMO, "line_id": line["id"]})
                me = (await mine.get("/auth/me")).json()
                thread = await store.thread_for_user(frames[0]["thread_id"], me["org_id"])
                await store.save_progress(thread.id, thread.last_seq, "abandoned")
            async with signed_in("theirs@example.com") as theirs:
                return await theirs.post(f"/threads/{thread.id}/continue")

    assert run(go()).status_code == 404


@pytest.mark.parametrize("status", ("running", "awaiting"))
def test_continue_refuses_non_continuable_statuses(status):
    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                me = (await http.get("/auth/me")).json()
                line = await store.create_line(me["id"], me["org_id"], "P")
                await store.create_thread("cannot-continue", line.id, me["id"], me["org_id"], "A board")
                await store.save_progress("cannot-continue", 4, status)
                return await http.post("/threads/cannot-continue/continue")

    assert run(go()).status_code == 409


def test_continue_reenters_with_none_and_keeps_the_persisted_sequence():
    class ContinuationGraph:
        def __init__(self):
            self.payloads = []

        async def astream(self, payload, config, stream_mode):
            self.payloads.append(payload)
            yield "custom", config["configurable"]["events"].reasoning(None, "continued")

    async def go():
        async with a_store() as store:
            async with signed_in() as http:
                me = (await http.get("/auth/me")).json()
                line = await store.create_line(me["id"], me["org_id"], "P")
                await store.create_thread("continue-me", line.id, me["id"], me["org_id"], "A board")
                await store.save_progress("continue-me", 41, "abandoned")
                graph = ContinuationGraph()
                previous = app.state.graph
                app.state.graph = graph
                try:
                    frames = await frames_of(http, "/threads/continue-me/continue", {})
                finally:
                    app.state.graph = previous
                return frames, graph.payloads

    frames, payloads = run(go())
    assert payloads == [None]
    assert frames[0]["seq"] == 42




@asynccontextmanager
async def _colleagues(store):
    """An engineer and a buyer in one company, each with their own signed-in client.

    Organisation membership is what lets the buyer see the engineer's run at all — item
    11a. Whether they may *answer* it is a separate question, which is the point below.
    """
    async with a_client() as engineer, a_client() as buyer:
        await engineer.post("/auth/register", json={"email": "eng@example.com", "password": "a-good-password"})
        await buyer.post("/auth/register", json={"email": "proc@example.com", "password": "a-good-password"})

        them = (await buyer.get("/auth/me")).json()
        us = (await engineer.get("/auth/me")).json()
        await store.add_user_to_organisation(them["id"], us["org_id"], ["procurement"])

        yield engineer, buyer


def test_a_colleague_is_refused_at_a_gate_that_is_not_theirs_to_answer():
    """BUILD's test, over HTTP, against a run actually paused by the graph.

    The buyer can reach this thread — same company — and that is exactly why membership
    alone cannot be the authorisation. The supply question is a circuit question, and
    "procurement signed off the input voltage" is a worse outcome than the 404 that
    per-user ownership used to give.
    """
    async def go():
        async with a_store() as store:
            async with _colleagues(store) as (engineer, buyer):
                frames = await frames_of(engineer, "/design", {"prompt": UNRESOLVED})
                thread_id = frames[0]["thread_id"]
                question = [f for f in frames if f["type"] == "question"][-1]

                refused = await buyer.post(
                    "/resume", json={"thread_id": thread_id, "answer": "USB-C"}
                )
                return question, refused

    question, refused = run(go())

    assert question["roles"] == ["engineering"], "the frame says whose decision this is"
    assert refused.status_code == 403, "membership is not permission"
    assert "engineering" in refused.json()["detail"], "name the desk it belongs to"


def test_the_person_whose_decision_it_is_may_answer_it():
    async def go():
        async with a_store() as store:
            async with _colleagues(store) as (engineer, buyer):
                frames = await frames_of(engineer, "/design", {"prompt": UNRESOLVED})
                thread_id = frames[0]["thread_id"]
                async with engineer.stream(
                    "POST", "/resume", json={"thread_id": thread_id, "answer": "USB-C"}
                ) as response:
                    await response.aread()
                    return response.status_code

    assert run(go()) == 200


def test_a_thread_in_another_company_is_still_a_404_and_never_a_403():
    """A 403 would confirm the thread exists to someone with no business knowing."""
    async def go():
        async with a_store() as store:
            async with signed_in("mine@example.com") as mine:
                frames = await frames_of(mine, "/design", {"prompt": UNRESOLVED})
                thread_id = frames[0]["thread_id"]
            async with signed_in("stranger@example.com") as stranger:
                return await stranger.post(
                    "/resume", json={"thread_id": thread_id, "answer": "USB-C"}
                )

    assert run(go()).status_code == 404


# ── the gates, end to end ─────────────────────────────────────────────────────


def test_an_approval_records_the_person_who_gave_it():
    """A waiver that cannot name its author is a setting, not a decision.

    Driven through the AML gate on purpose: an organisation whose list approves nothing
    fails qualification on a board with nothing electrically wrong, which is item 13's own
    test, and accepting it is what writes the ledger row. The answering user reaches the
    run through `Command(update=...)` on `/resume`, because only that request knows who is
    at the keyboard — the graph is resumed by whichever process serves the call.
    """
    async def go():
        async with a_store() as store:
            async with signed_in("engineer@example.com") as http:
                me = (await http.get("/auth/me")).json()
                await store.keep_lists(me["org_id"], aml=True)

                frames = await frames_of(http, "/design", {"prompt": DEMO})
                thread_id = frames[0]["thread_id"]
                question = [f for f in frames if f["type"] == "question"]
                if not question:
                    return None, [], me, frames

                resumed = await frames_of(
                    http,
                    "/resume",
                    {
                        "thread_id": thread_id,
                        "answer": "Qualify this part for use",
                        "rationale": "Qualified on the 2025 audit; paperwork is in QMS-4417.",
                    },
                )
                return (
                    question[-1],
                    await store.approvals_for_thread(thread_id, me["org_id"]),
                    me,
                    resumed,
                )

    question, recorded, me, frames = run(go())

    assert question is not None, "an empty AML must stop the run for a decision"
    assert set(question["roles"]) == {"engineering", "quality"}, (
        "qualifying a part is engineering's call and quality's record"
    )

    emitted = [f for f in frames if f["type"] == "approval"]
    assert emitted, "accepting produced no approval frame"
    assert emitted[0]["by"]["email"] == "engineer@example.com"

    assert recorded, "the approval never reached the durable record"
    assert recorded[0]["user_email"] == "engineer@example.com"
    assert "QMS-4417" in recorded[0]["rationale"], "the words they used, not a summary"
    assert recorded[0]["rule"] == emitted[0]["rule"]
    assert recorded[0]["created_at"] is not None


def test_a_run_is_checked_against_its_organisations_lists():
    """The gates fire on a real run, not only in a unit test."""
    async def go():
        async with a_store() as store:
            async with signed_in("eng@example.com") as http:
                me = (await http.get("/auth/me")).json()
                # An AML that approves nothing: every part on the board is unqualified.
                await store.keep_lists(me["org_id"], aml=True)
                frames = await frames_of(http, "/design", {"prompt": DEMO})
                return [
                    f for f in frames
                    if f["type"] == "check" and f["rule"] == "part_qualification"
                ]

    checks = run(go())

    assert checks, "the gate never ran on a live board"
    assert any(check["status"] == "failed" for check in checks)
    assert all(check["status"] != "not_applicable" for check in checks)


def test_a_run_without_any_list_is_not_told_every_part_is_unqualified():
    async def go():
        async with a_store():
            async with signed_in("nolist@example.com") as http:
                frames = await frames_of(http, "/design", {"prompt": DEMO})
                return [
                    f for f in frames
                    if f["type"] == "check" and f["rule"] == "part_qualification"
                ]

    checks = run(go())

    assert all(check["status"] == "not_applicable" for check in checks)


# ── what a product line is ────────────────────────────────────────────────────

GATEWAY_PROFILE = {
    "ambient_c": 45,
    "ambient_source": "gateway operating profile Rev C",
    "rails": {
        "3v3": {"source": "u1", "members": ["u2", "c1"], "i_load": 0.42},
        "vin": {"source": None, "members": ["u1"], "voltage": 5.0, "basis": "USB Type-C"},
    },
}

GATEWAY_BOM = [
    {"refdes": "u1", "mpn": "AMS1117-3.3", "manufacturer": "AMS", "footprint": "SOT-223"},
    {"refdes": "u2", "mpn": "ESP32-C3-MINI-1-N4", "manufacturer": "Espressif"},
    {"refdes": "c1", "mpn": "CL31A226KAHNNNE", "manufacturer": "Samsung"},
]


class _Notice:
    """The fields `save_notice` reads. The reader itself is tested in `test_notices.py`."""

    mpn = "AMS1117-3.3"
    mpn_line = "Affected part: AMS1117-3.3 (SOT-223)"
    reference = "AMS-PCN-2026-114"
    reference_line = "AMS-PCN-2026-114 · Advanced Monolithic Systems"
    manufacturer = "Advanced Monolithic Systems"
    effective_date = "2027-03-31"
    effective_date_line = "Last time buy: 2027-03-31"
    replacement_mpn = "NCP1117ST33T3G"
    replacement_line = "Recommended replacement: NCP1117ST33T3G."
    reason = "Wafer fabrication line closure."


async def a_described_line(http, name: str = "Gateway") -> str:
    line = (await http.post("/lines", json={"name": name})).json()
    await http.put(f"/lines/{line['id']}/bom", json={"rows": GATEWAY_BOM})
    await http.put(
        f"/lines/{line['id']}/profile",
        json={"profile": GATEWAY_PROFILE, "revision": "Rev C"},
    )
    return line["id"]


def test_a_product_line_shows_what_it_is_without_any_run():
    """The page that did not exist. A product with parts, a profile and a revision used to
    open the brief entry and ask what you were building."""

    async def go():
        async with a_store():
            async with signed_in("overview@example.com") as http:
                line_id = await a_described_line(http)
                return (await http.get(f"/lines/{line_id}/overview")).json()

    body = run(go())

    assert body["line"]["name"] == "Gateway"
    assert body["line"]["revision"] == "Rev C"
    assert [part["refdes"] for part in body["parts"]] == ["c1", "u1", "u2"]
    assert body["board"] is None
    assert body["notices"] == []


def test_the_power_tree_comes_out_of_the_stored_profile():
    async def go():
        async with a_store():
            async with signed_in("tree@example.com") as http:
                line_id = await a_described_line(http)
                return (await http.get(f"/lines/{line_id}/overview")).json()["graph"]

    graph = run(go())

    assert {(edge["from"], edge["to"]) for edge in graph["edges"]} == {
        ("__supply", "u1"),
        ("u1", "u2"),
        ("u1", "c1"),
    }
    assert graph["supply"]["voltage"] == 5.0
    assert {slot["status"] for slot in graph["slots"]} == {"unchecked"}


def test_a_notice_against_a_fitted_part_reaches_the_product_line_page():
    """The question this page asks that no other screen does: not what a notice reaches,
    but what is coming for this product."""

    async def go():
        async with a_store() as store:
            async with signed_in("exposed@example.com") as http:
                line_id = await a_described_line(http)
                user = (await http.get("/auth/me")).json()
                await store.save_notice(user["org_id"], user["id"], _Notice(), source="test")
                overview = (await http.get(f"/lines/{line_id}/overview")).json()
                listed = (await http.get("/lines")).json()
                return overview, listed

    overview, listed = run(go())

    assert [notice["mpn"] for notice in overview["notices"]] == ["AMS1117-3.3"]
    assert overview["notices"][0]["refdes"] == ["u1"]
    assert [line["exposed_count"] for line in listed] == [1], (
        "the dashboard counts exposure beside the row rather than fetching per line"
    )


def test_another_organisation_s_product_line_is_not_found():
    async def go():
        async with a_store():
            async with signed_in("owner@example.com") as mine:
                line_id = await a_described_line(mine)
            async with signed_in("stranger@example.com") as theirs:
                return await theirs.get(f"/lines/{line_id}/overview")

    assert run(go()).status_code == 404
