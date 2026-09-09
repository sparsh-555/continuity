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
from continuity.notices import Notice
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


def test_reset_survives_a_world_that_has_actually_been_used():
    """Reset after a demo run, which is the only time anybody runs it.

    An empty world resets cleanly, and `test_reset_replaces_the_world_and_leaves_one_company`
    passed for weeks on that alone. The demo database did not: `decisions.decided_by` is
    ON DELETE SET NULL while `decisions.line_id` cascades, so deleting the users made
    PostgreSQL update a decision row whose product line the same statement had already
    cascaded away, and that update re-checked `line_id` against a row that was gone.

    **This test does not reproduce that failure, and saying so is the point.** Whether the
    update or the cascade reaches a given row first depends on the order rows come off
    disk, so the same shape raises `ForeignKeyViolation` on the demo database and passes
    here. The failure was reproduced against a `pg_dump` copy of the demo world, and it
    goes away there under `UPDATE decisions SET decided_by = NULL`. What this test holds
    is the shape and the outcome: a used world resets, and nothing it owned survives.
    """

    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            line_id = world["lines"][0][0]
            others = [row[0] for row in world["lines"][1:3]]
            notice_id = await store.save_notice(
                world["org_id"], world["engineer"].id,
                Notice(mpn="AMS1117-3.3", mpn_line="Affected part: AMS1117-3.3"),
                source="test",
            )
            # One decision per affected line, which is what a review produces. The demo
            # leaves three, and one answered among several is what makes PostgreSQL
            # update a row it is also cascading away.
            for other in others:
                await store.save_decision(
                    org_id=world["org_id"], line_id=other, notice_id=notice_id,
                    user_id=world["engineer"].id, slot_id="U3", retiring="AMS1117-3.3",
                    proposal="NCP1117ST33T3G", gate_rule="part_qualification",
                    roles=["engineering"], detail="Clears here.", document={},
                )
            decision_id = await store.save_decision(
                org_id=world["org_id"],
                line_id=line_id,
                notice_id=notice_id,
                user_id=world["engineer"].id,
                slot_id="U3",
                retiring="AMS1117-3.3",
                proposal="TLV1117LV33DCYR",
                gate_rule="part_qualification",
                roles=["engineering"],
                detail="35 °C of margin.",
                document={},
            )
            # Answered by the other account. That is the shape the demo leaves behind, and
            # it is what makes the deletion order matter: the line belongs to one user and
            # the decision points at two.
            await store.settle_decision(
                decision_id, world["org_id"], state="approved",
                by=world["engineer"].id, rationale="Fine here.",
            )
            # And the signature it produced, which points at both the decision and the
            # line. This is what makes the deletion order matter rather than merely
            # untidy: `approvals.decision_id` nulls when the decision goes, and
            # `decisions.decided_by` nulls when the user goes, so PostgreSQL updates rows
            # whose `line_id` has already been cascaded away underneath them.
            async with store.pool.connection() as conn:
                cursor = await conn.execute(
                    "SELECT decided_by FROM decisions WHERE id = %s", (decision_id,)
                )
                assert (await cursor.fetchone())[0], "the decision has to be answered"
            await store.record_approval(
                org_id=world["org_id"],
                decision_id=decision_id,
                line_id=line_id,
                user_id=world["engineer"].id,
                user_email="engineer@northwind.example",
                roles=["engineering"],
                rule="part_qualification",
                subject="U3",
                mpn="TLV1117LV33DCYR",
                revision="Rev D",
                rationale="35 °C of margin.",
            )
            await seed_world.seed(store, reset=True)
            async with store.pool.connection() as conn:
                cursor = await conn.execute("SELECT count(*) FROM decisions")
                (decisions,) = await cursor.fetchone()
                cursor = await conn.execute("SELECT count(*) FROM product_lines")
                (lines,) = await cursor.fetchone()
            return decisions, lines

    decisions, lines = run(go())

    assert decisions == 0, "the old world's decisions go with it"
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
                # The concurrent run, which is what the app does. The one-shot endpoint
                # beside it takes a single position and applies it to every line, and
                # since one of these products is a real board that puts its regulator at
                # U3 while the others say u1, it now refuses rather than guessing. That
                # refusal is right, and it is why this test moved: it was driving an
                # endpoint the demo never touches.
                async with http.stream(
                    "POST", f"/notices/{notice['id']}/review/run",
                    json={
                        "candidates": [NCP1117.mpn, LD1117.mpn, TLV1117.mpn],
                        "annual_volume": 20_000,
                    },
                ) as stream:
                    assert stream.status_code == 200, await stream.aread()
                    async for _ in stream.aiter_lines():
                        pass
                stored = await http.get(f"/notices/{notice['id']}/review")
                return notice, stored

    notice, stored = run(go())

    assert {row["name"] for row in notice["affected"]} == {
        "Sensor node", "Gateway", "Cabinet controller"
    }, "the notice reaches three of five products"

    assert stored.status_code == 200, stored.text
    requests = {r["line_name"]: r for r in stored.json()}
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


# ── the board the company already has ─────────────────────────────────────────


def test_a_seeded_line_already_carries_its_kicad_project():
    """The demo does not open by zipping a fixture and uploading it.

    A company that ships a product has its CAD; making the attach a demo step was an
    accident of item 16 landing before item 18 and nobody joining them.
    """

    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            board = await store.board_for(world["board_line_id"], world["org_id"])
            bill = await store.bom_for_line(world["board_line_id"], world["org_id"])
            return board, bill

    board, bill = run(go())

    assert board is not None, "the line the board belongs to has it at seed time"
    assert board["project"] == "ProPico"
    assert board["bytes"] > 0

    # The bill is unchanged by attaching a design. Continuity validates at block level and
    # the board carries thirty-eight passives it has no business checking.
    at = {row["refdes"]: row["mpn"] for row in bill}
    assert at["u1"] == "AMS1117-3.3", "the block-level bill, not the board's forty-one rows"


def test_attaching_a_design_does_not_replace_the_bill():
    """A board is a design. A bill is what Continuity validates, and they are not the same.

    The Singapore proposal draws the boundary at block-level validation because *"synthesis
    requires pin-level connectivity, a substantially larger data problem"*, and the planner's
    own prompt calls passives an implementation detail. Importing ProPico's forty-one rows
    would put thirty-eight decoupling capacitors, pull-ups and a crystal in front of rules
    that would each report evidence missing, which is scope creep wearing honesty as a
    costume.
    """

    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            return await store.bom_for_line(world["board_line_id"], world["org_id"])

    bill = run(go())

    assert len(bill) == 3, "the regulator, what it feeds, and the output capacitor"


def test_every_affected_line_has_its_own_board_and_no_two_are_the_same():
    """Three real projects, not one file attached three times.

    One file on three products claims they are the same board, which anybody can check by
    opening two of them. These were found by searching GitHub for KiCad schematics carrying
    an AMS1117-3.3, and each puts it at a different reference designator, which is what the
    world looks like and what a uniform fixture was hiding.
    """

    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            boards = {}
            for line_id, label, _ in world["lines"]:
                board = await store.board_for(line_id, world["org_id"])
                boards[label] = board
            return boards

    boards = run(go())

    affected = {"Sensor node", "Gateway", "Cabinet controller"}
    assert {name for name, board in boards.items() if board} == affected

    projects = {boards[name]["project"] for name in affected}
    assert len(projects) == 3, f"three different designs, got {projects}"

    # The two that ship a part nobody is retiring have no project, which is an ordinary
    # state for a company and better said than pretended.
    assert boards["Bench supply"] is None and boards["Handheld meter"] is None


def test_every_seeded_line_arrives_already_described():
    """A product that ships did not arrive by somebody asking what to build.

    `/design/:lineId` opened the brief screen — *"What are you building?"* — for a product
    line with a revision, a bill of materials and a KiCad project, because no run had ever
    been recorded against it. Seeding a *synthesis* would be inventing work that never
    happened; this records the work the seed is actually doing, and every check in it is
    `rules.evaluate` on the board the stored bill and profile make.
    """

    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            found = {}
            for line_id, label, _mpn in world["lines"]:
                threads = await store.threads_for_line(line_id, world["org_id"])
                assert len(threads) == 1, f"{label} has {len(threads)} runs"
                found[label] = (threads[0], await store.run_events(threads[0].id))
            return found

    described = run(go())

    assert len(described) == 5
    for label, (thread, frames) in described.items():
        assert thread.status == "done", label
        assert thread.summary["placed"] == 3, label
        kinds = [frame["type"] for frame in frames]
        assert kinds.count("plan") == 1, label
        assert kinds.count("selection") == 3, label
        # The checks are real, so there are as many as the engine produced.
        assert kinds.count("check") >= 20, f"{label} recorded {kinds.count('check')} checks"
        assert kinds[-1] == "done", label


def test_a_seeded_run_restores_its_board_without_a_checkpoint():
    """The trace is the record; the checkpoint is a cache.

    Restoring a run reads LangGraph's checkpointer, and a seeded run has no entry in it —
    nor does any run whose checkpoint was lost, which this codebase already has three
    fallbacks for. Every frame the client draws the board from is in `run_events`.
    """
    from continuity.api.app import _board_from_frames

    async def go():
        async with empty() as store:
            world = await seed_world.seed(store)
            line_id = world["lines"][0][0]
            threads = await store.threads_for_line(line_id, world["org_id"])
            return await store.run_events(threads[0].id)

    frames = run(go())
    rebuilt = _board_from_frames(frames)

    assert rebuilt is not None
    assert [slot["id"] for slot in rebuilt["slots"]] == ["u1", "u2", "c1"]
    assert all(slot["part"] is not None for slot in rebuilt["slots"])
    assert all(slot["status"] == "pass" for slot in rebuilt["slots"])
    assert rebuilt["supply"] is not None, "the input rail travels with the board"
    assert rebuilt["edges"], "a power tree with no edges is three floating parts"

    # Without a `plan` frame there is no board, and saying so is what lets the caller
    # report an unrestorable run rather than an empty one.
    assert _board_from_frames([f for f in frames if f["type"] != "plan"]) is None
