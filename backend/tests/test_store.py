"""The application tables: ownership, sessions, and what has to survive a restart.

Skipped unless `CONTINUITY_TEST_DB` points at a database, so the default suite stays
offline and under a second. Same idiom as `CONTINUITY_LIVE` and `CONTINUITY_FIXTURES`.

    createdb continuity_test
    CONTINUITY_TEST_DB=postgresql:///continuity_test pytest tests/test_store.py

Two properties carry most of the weight here. **A lookup scoped to a user must return
nothing for anyone else** — `/resume` and `/export` authorise on exactly these queries,
and a missing WHERE clause is an IDOR rather than a failing assertion. And **`last_seq`
must round-trip**, because a resumed stream that restarts its numbering is discarded
silently by the client.
"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from contextlib import asynccontextmanager

import pytest

from continuity.api.store import (
    SCHEMA,
    SESSION_IDLE_SECONDS,
    SESSION_TTL_SECONDS,
    EmailTaken,
    Store,
    UnknownRole,
)
from continuity.api.findings import Finding

DB_URL = os.environ.get("CONTINUITY_TEST_DB")

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="set CONTINUITY_TEST_DB to run the store tests"
)


def run(coro):
    return asyncio.run(coro)


def test_the_project_to_product_line_migration_preserves_rows_and_is_idempotent():
    """A restart after migration must be as safe as the first boot that performs it.

    This deliberately creates the pre-7-Sep shape in an isolated schema rather than
    deriving it from the current DDL. The migration is needed precisely because the
    current schema cannot prove that a live `projects` table and its `threads.project_id`
    values survive the rename. Rolling the transaction back removes only this test's
    temporary schema; it never drops a table from the shared test database.
    """

    async def go():
        from psycopg_pool import AsyncConnectionPool

        schema_name = f"migration_{os.urandom(8).hex()}"
        async with AsyncConnectionPool(DB_URL, min_size=1, max_size=1, open=False) as pool:
            await pool.open()
            async with pool.connection() as conn:
                await conn.execute("BEGIN")
                try:
                    await conn.execute(f'CREATE SCHEMA "{schema_name}"')
                    await conn.execute(f'SET LOCAL search_path TO "{schema_name}"')
                    await conn.execute(
                        "CREATE TABLE users (id text PRIMARY KEY, email text NOT NULL UNIQUE, "
                        "password_hash text NOT NULL, onboarded_at timestamptz, "
                        "created_at timestamptz NOT NULL DEFAULT now())"
                    )
                    await conn.execute(
                        "CREATE TABLE projects (id text PRIMARY KEY, user_id text NOT NULL "
                        "REFERENCES users(id) ON DELETE CASCADE, name text NOT NULL, "
                        "created_at timestamptz NOT NULL DEFAULT now(), "
                        "updated_at timestamptz NOT NULL DEFAULT now())"
                    )
                    await conn.execute(
                        "CREATE INDEX projects_user_idx ON projects(user_id, updated_at DESC)"
                    )
                    await conn.execute(
                        "CREATE TABLE threads (id text PRIMARY KEY, project_id text NOT NULL "
                        "REFERENCES projects(id) ON DELETE CASCADE, user_id text NOT NULL "
                        "REFERENCES users(id) ON DELETE CASCADE, prompt text NOT NULL, "
                        "status text NOT NULL DEFAULT 'running', last_seq integer NOT NULL DEFAULT -1, "
                        "bom jsonb, created_at timestamptz NOT NULL DEFAULT now(), "
                        "updated_at timestamptz NOT NULL DEFAULT now())"
                    )
                    await conn.execute(
                        "CREATE INDEX threads_project_idx ON threads(project_id, created_at DESC)"
                    )
                    await conn.execute(
                        "INSERT INTO users (id, email, password_hash) VALUES ('u', 'u@example.com', 'h')"
                    )
                    await conn.execute(
                        "INSERT INTO projects (id, user_id, name) VALUES ('line', 'u', 'Power supplies')"
                    )
                    await conn.execute(
                        "INSERT INTO threads (id, project_id, user_id, prompt) "
                        "VALUES ('thread', 'line', 'u', 'Review the regulator')"
                    )

                    await conn.execute(SCHEMA.read_text())
                    first = await conn.execute(
                        "SELECT p.name, t.line_id FROM product_lines p "
                        "JOIN threads t ON t.line_id = p.id WHERE p.id = 'line'"
                    )
                    survived = await first.fetchone()

                    # Schema setup runs at every boot. The second execution is the
                    # production failure mode this regression protects against.
                    await conn.execute(SCHEMA.read_text())
                    second = await conn.execute(
                        "SELECT p.name, t.line_id FROM product_lines p "
                        "JOIN threads t ON t.line_id = p.id WHERE p.id = 'line'"
                    )
                    survived_after_restart = await second.fetchone()
                finally:
                    await conn.rollback()
        return survived, survived_after_restart

    assert run(go()) == (("Power supplies", "line"), ("Power supplies", "line"))


@asynccontextmanager
async def fresh():
    """A store on an empty schema. Truncates rather than dropping, so `setup` runs once."""
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=2, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE users, organisations, sessions, product_lines, threads, part_facts CASCADE")
        yield store


async def a_user(store: Store, email: str = "sparsh@example.com"):
    return await store.create_user(email, "argon2-hash-goes-here")


# ── users ─────────────────────────────────────────────────────────────────────


def test_a_registered_user_is_found_by_email():
    async def go():
        async with fresh() as store:
            created = await a_user(store)
            return created, await store.user_by_email("sparsh@example.com")

    created, found = run(go())
    assert found is not None
    assert found.id == created.id
    assert found.password_hash == "argon2-hash-goes-here"


def test_email_is_folded_so_case_cannot_split_an_account():
    async def go():
        async with fresh() as store:
            await store.create_user("Sparsh@Example.COM", "h")
            return await store.user_by_email("sparsh@example.com")

    assert run(go()) is not None


def test_a_duplicate_email_is_refused():
    async def go():
        async with fresh() as store:
            await a_user(store)
            try:
                await a_user(store)
            except EmailTaken:
                return "refused"
            return "accepted"

    assert run(go()) == "refused"


def test_a_duplicate_is_refused_across_case_too():
    async def go():
        async with fresh() as store:
            await store.create_user("sparsh@example.com", "h")
            try:
                await store.create_user("SPARSH@EXAMPLE.COM", "h")
            except EmailTaken:
                return "refused"
            return "accepted"

    assert run(go()) == "refused"


def test_onboarding_starts_unrecorded_and_is_recorded_once():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            before = (await store.user_by_id(user.id)).onboarded_at
            await store.mark_onboarded(user.id)
            return before, (await store.user_by_id(user.id)).onboarded_at

    before, after = run(go())
    assert before is None
    assert after is not None


# ── sessions ──────────────────────────────────────────────────────────────────


def test_a_session_resolves_to_its_user():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=3600)
            return user, await store.user_for_token(token)

    user, resolved = run(go())
    assert resolved is not None
    assert resolved.id == user.id


def test_the_raw_token_never_reaches_the_database():
    """A dump of `sessions` must not be a set of usable cookies."""

    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=3600)
            async with store.pool.connection() as conn:
                cursor = await conn.execute("SELECT token_hash FROM sessions")
                rows = await cursor.fetchall()
            return token, [row[0] for row in rows]

    token, stored = run(go())
    assert token not in stored
    assert len(stored) == 1


def test_an_expired_session_resolves_to_nobody():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=-1)
            return await store.user_for_token(token)

    assert run(go()) is None


def test_using_a_session_slides_its_idle_window_forward():
    """The whole point of an idle timeout: activity is what keeps you signed in."""

    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=60)
            async with store.pool.connection() as conn:
                cursor = await conn.execute("SELECT expires_at FROM sessions")
                before = (await cursor.fetchone())[0]

            resolved = await store.user_for_token(token)

            async with store.pool.connection() as conn:
                cursor = await conn.execute("SELECT expires_at FROM sessions")
                after = (await cursor.fetchone())[0]
            return resolved, before, after

    resolved, before, after = run(go())
    assert resolved is not None
    # A minute was granted, the full idle window is now in front of it.
    assert (after - before).total_seconds() > SESSION_IDLE_SECONDS - 120


def test_the_absolute_ceiling_survives_being_slid_against():
    """Otherwise a cookie used once every twenty minutes never expires at all."""

    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=60)
            # Backdate creation to just inside the ceiling: the renewal must clamp to it
            # rather than granting another full idle window past it.
            async with store.pool.connection() as conn:
                await conn.execute(
                    "UPDATE sessions SET created_at = now() - %s + interval '2 minutes'",
                    (timedelta(seconds=SESSION_TTL_SECONDS),),
                )
            resolved = await store.user_for_token(token)
            async with store.pool.connection() as conn:
                cursor = await conn.execute(
                    "SELECT expires_at - now() FROM sessions"
                )
                remaining = (await cursor.fetchone())[0]
            return resolved, remaining

    resolved, remaining = run(go())
    assert resolved is not None
    assert remaining.total_seconds() < 3 * 60, "clamped to the ceiling, not extended past it"


def test_a_session_past_the_absolute_ceiling_resolves_to_nobody():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=3600)
            async with store.pool.connection() as conn:
                await conn.execute(
                    "UPDATE sessions SET created_at = now() - %s",
                    (timedelta(seconds=SESSION_TTL_SECONDS + 60),),
                )
            return await store.user_for_token(token)

    assert run(go()) is None, "still inside its idle window, but too old to renew"


def test_a_deleted_session_resolves_to_nobody():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            token = await store.create_session(user.id, ttl_seconds=3600)
            await store.delete_session(token)
            return await store.user_for_token(token)

    assert run(go()) is None


def test_an_unknown_token_resolves_to_nobody():
    async def go():
        async with fresh() as store:
            await a_user(store)
            return await store.user_for_token("not-a-real-token")

    assert run(go()) is None


# ── lines and threads: ownership ───────────────────────────────────────────


def test_lines_list_for_their_owner_only():
    async def go():
        async with fresh() as store:
            mine = await a_user(store, "mine@example.com")
            theirs = await a_user(store, "theirs@example.com")
            await store.create_line(mine.id, mine.org_id, "My board")
            await store.create_line(theirs.id, theirs.org_id, "Their board")
            return (
                await store.lines_for_user(mine.org_id, mine.id),
                await store.lines_for_user(theirs.org_id, theirs.id),
            )

    ours, others = run(go())
    assert [p.name for p in ours] == ["My board"]
    assert [p.name for p in others] == ["Their board"]


def test_a_line_is_invisible_to_another_user():
    async def go():
        async with fresh() as store:
            mine = await a_user(store, "mine@example.com")
            theirs = await a_user(store, "theirs@example.com")
            line = await store.create_line(mine.id, mine.org_id, "My board")
            return (
                await store.line_for_user(line.id, mine.org_id, mine.id),
                await store.line_for_user(line.id, theirs.org_id, theirs.id),
            )

    owned, stolen = run(go())
    assert owned is not None
    assert stolen is None


def test_exposure_returns_populated_mpn_across_lines_but_not_dnp():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            lines = [await store.create_line(user.id, user.org_id, name) for name in "ABCDE"]
            rows = [{"refdes": "U1", "mpn": "TARGET", "populated": True}]
            for line in lines[:3]:
                await store.save_bom_rows(line.id, user.id, user.org_id, rows)
            await store.save_bom_rows(
                lines[3].id, user.id, user.org_id,
                [{"refdes": "U1", "mpn": "TARGET", "populated": False}],
            )
            await store.save_bom_rows(
                lines[4].id, user.id, user.org_id,
                [{"refdes": "U1", "mpn": "OTHER", "populated": True}],
            )
            return lines, await store.lines_exposed_to(user.org_id, "TARGET", user.id)

    lines, exposed = run(go())
    assert [row["line_id"] for row in exposed] == [line.id for line in lines[:3]]
    assert all(row["refdes"] == ["U1"] for row in exposed)


def test_exposure_never_crosses_accounts():
    async def go():
        async with fresh() as store:
            mine = await a_user(store, "mine@example.com")
            theirs = await a_user(store, "theirs@example.com")
            mine_line = await store.create_line(mine.id, mine.org_id, "Mine")
            theirs_line = await store.create_line(theirs.id, theirs.org_id, "Theirs")
            rows = [{"refdes": "U1", "mpn": "TARGET"}]
            await store.save_bom_rows(mine_line.id, mine.id, mine.org_id, rows)
            await store.save_bom_rows(theirs_line.id, theirs.id, theirs.org_id, rows)
            return (
                await store.lines_exposed_to(mine.org_id, "TARGET", mine.id),
                await store.lines_exposed_to(theirs.org_id, "TARGET", theirs.id),
            )

    mine, theirs = run(go())
    assert [row["name"] for row in mine] == ["Mine"]
    assert [row["name"] for row in theirs] == ["Theirs"]


def test_reuploading_a_bom_replaces_the_document():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "Board")
            await store.save_bom_rows(line.id, user.id, user.org_id, [{"refdes": "C1", "mpn": "OLD"}])
            await store.save_bom_rows(line.id, user.id, user.org_id, [{"refdes": "R1", "mpn": "NEW"}])
            return await store.bom_for_line(line.id, user.org_id)

    assert run(go()) == [
        {"refdes": "R1", "mpn": "NEW", "manufacturer": None, "footprint": None, "populated": True}
    ]


def test_a_thread_is_invisible_to_another_user():
    """This lookup is what stands between `/resume` and an IDOR."""

    async def go():
        async with fresh() as store:
            mine = await a_user(store, "mine@example.com")
            theirs = await a_user(store, "theirs@example.com")
            line = await store.create_line(mine.id, mine.org_id, "My board")
            await store.create_thread("thread-1", line.id, mine.id, mine.org_id, "a brief")
            return (
                await store.thread_for_user("thread-1", mine.org_id),
                await store.thread_for_user("thread-1", theirs.org_id),
            )

    owned, stolen = run(go())
    assert owned is not None
    assert owned.prompt == "a brief"
    assert stolen is None


# ── what has to survive a restart ─────────────────────────────────────────────


def test_a_new_thread_starts_at_minus_one():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            return await store.thread_for_user("thread-1", user.org_id)

    thread = run(go())
    assert thread.last_seq == -1
    assert thread.status == "running"


def test_progress_round_trips():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            await store.save_progress("thread-1", last_seq=41, status="awaiting")
            return await store.thread_for_user("thread-1", user.org_id)

    thread = run(go())
    assert thread.last_seq == 41
    assert thread.status == "awaiting"


def test_abandoned_is_an_accepted_terminal_status():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            await store.save_progress("thread-1", last_seq=0, status="abandoned")
            return await store.thread_for_user("thread-1", user.org_id)

    assert run(go()).status == "abandoned"


def test_the_bom_round_trips():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            rows = [{"slot": "reg", "mpn": "AMS1117-3.3", "qty": 1, "unit_price": 0.12}]
            await store.save_bom("thread-1", rows)
            return await store.thread_for_user("thread-1", user.org_id)

    thread = run(go())
    assert thread.bom == [{"slot": "reg", "mpn": "AMS1117-3.3", "qty": 1, "unit_price": 0.12}]


def test_run_events_round_trip_in_sequence_without_duplicates():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            await store.save_run_events(
                "thread-1",
                [
                    {"type": "reasoning", "seq": 2, "thread_id": "thread-1", "text": "later"},
                    {"type": "reasoning", "seq": 1, "thread_id": "thread-1", "text": "first"},
                ],
            )
            await store.save_run_events(
                "thread-1",
                [{"type": "reasoning", "seq": 1, "thread_id": "thread-1", "text": "duplicate"}],
            )
            return await store.run_events("thread-1")

    assert [event["text"] for event in run(go())] == ["first", "later"]


def test_part_facts_upsert_in_place_and_return_by_mpn():
    async def go():
        async with fresh() as store:
            await store.save_part_facts([("TPS54331DR", "theta_ja", "116.3", "TI datasheet")])
            await store.save_part_facts([("TPS54331DR", "theta_ja", "62.0", "newer TI datasheet")])
            return await store.part_facts(["TPS54331DR"])

    assert run(go()) == {
        "TPS54331DR": [
            {"field": "theta_ja", "value": "62.0", "source": "newer TI datasheet"}
        ]
    }


def test_an_empty_part_facts_lookup_does_not_open_a_connection():
    class NoQueryPool:
        def connection(self):
            raise AssertionError("an empty MPN list must not query the database")

    assert run(Store(NoQueryPool()).part_facts([])) == {}


def test_memory_includes_stable_facts_and_empty_lists_for_unknown_parts():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            await store.save_bom(
                "thread-1",
                [
                    {"slot": "reg", "mpn": "TPS54331DR", "qty": 1},
                    {"slot": "sensor", "mpn": "SHT40", "qty": 1},
                ],
            )
            await store.save_part_facts([("TPS54331DR", "theta_ja", "62.0", "TI datasheet")])
            return await store.memory_for_user(user.org_id, part_limit=100)

    parts = {part["mpn"]: part for part in run(go())["parts"]}
    # `source` is split into what the reading is and what it quoted. "TI datasheet" is not
    # written with the verified marker, so it stays as it is and claims no datasheet line.
    assert parts["TPS54331DR"]["facts"] == [
        {"field": "theta_ja", "value": "62.0", "verified": False, "quote": "TI datasheet"}
    ]
    assert parts["SHT40"]["facts"] == []


def test_an_unknown_status_is_refused_by_the_database():
    """The status vocabulary is fixed, the same way every other vocabulary here is."""

    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            try:
                await store.save_progress("thread-1", last_seq=0, status="banana")
            except Exception as exc:
                return type(exc).__name__
            return "accepted"

    assert run(go()) != "accepted"


# ── what the engine reported ──────────────────────────────────────────────────


def test_a_thread_that_has_not_finished_has_no_summary():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            return await store.thread_for_user("thread-1", user.org_id)

    assert run(go()).summary is None


def test_the_summary_round_trips_verbatim():
    """Stored as the engine emitted it — this is a record, not a recomputation."""

    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("thread-1", line.id, user.id, user.org_id, "a brief")
            await store.save_summary(
                "thread-1",
                {"slots": 4, "placed": 4, "conflicts_resolved": 3, "elapsed_s": 12.4},
            )
            return await store.thread_for_user("thread-1", user.org_id)

    thread = run(go())
    assert thread.summary == {
        "slots": 4,
        "placed": 4,
        "conflicts_resolved": 3,
        "elapsed_s": 12.4,
    }


def test_precedents_are_scoped_to_successful_other_user_threads():
    async def go():
        async with fresh() as store:
            mine = await a_user(store, "mine@example.com")
            theirs = await a_user(store, "theirs@example.com")
            first = await store.create_line(mine.id, mine.org_id, "First")
            second = await store.create_line(mine.id, mine.org_id, "Second")
            signature = "thermal_dissipation|regulator|linear|pkg:SOT|drop:>=8V|load:100-500mA"
            for thread_id, line, worked in (
                ("thread-one", first, True),
                ("thread-two", second, True),
                ("thread-false", first, False),
            ):
                await store.create_thread(thread_id, line.id, mine.id, mine.org_id, "brief")
                await store.save_findings(
                    thread_id,
                    [
                        Finding(
                            "thermal_dissipation",
                            "regulator",
                            "BAD-LDO",
                            "Too hot.",
                            outcome="repaired",
                            action="change_topology",
                            signature=signature,
                            worked=worked,
                        )
                    ],
                )
            return (
                await store.precedents_for_user(mine.org_id, signature, exclude_thread="thread-two"),
                await store.precedents_for_user(mine.org_id, signature, exclude_thread="thread-one"),
                await store.precedents_for_user(theirs.org_id, signature, exclude_thread="thread-one"),
            )

    from_first, from_second, other_user = run(go())
    assert from_first == [
        {
            "rule": "thermal_dissipation",
            "action": "change_topology",
            "signature": "thermal_dissipation|regulator|linear|pkg:SOT|drop:>=8V|load:100-500mA",
            "line_name": "First",
        }
    ]
    assert from_second == [
        {
            "rule": "thermal_dissipation",
            "action": "change_topology",
            "signature": "thermal_dissipation|regulator|linear|pkg:SOT|drop:>=8V|load:100-500mA",
            "line_name": "Second",
        }
    ]
    assert other_user == []


def test_a_phantom_thread_never_masks_the_run_that_did_the_work():
    """React's double-invoke starts two runs; only one of them ever emits anything.

    Found live: a line waiting on a question opened to "this run has no board to
    restore", because the caller took the newest thread and the newest was the cancelled
    twin — `abandoned`, `last_seq = -1`, no checkpoint, no frames.
    """

    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("real", line.id, user.id, user.org_id, "a brief")
            await store.create_thread("phantom", line.id, user.id, user.org_id, "a brief")
            await store.save_progress("real", 75, "awaiting")
            await store.save_progress("phantom", -1, "abandoned")
            return await store.threads_for_line(line.id, user.org_id)

    assert [thread.id for thread in run(go())][0] == "real"


def test_a_live_run_outranks_a_finished_one():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "P")
            await store.create_thread("older-live", line.id, user.id, user.org_id, "a brief")
            await store.create_thread("newer-done", line.id, user.id, user.org_id, "a brief")
            await store.save_progress("older-live", 4, "running")
            await store.save_progress("newer-done", 90, "done")
            return await store.threads_for_line(line.id, user.org_id)

    assert [thread.id for thread in run(go())][0] == "older-live"


# ── organisations ─────────────────────────────────────────────────────────────


def test_two_organisations_are_invisible_to_each_other_across_every_listing():
    """The test that matters in the ownership move.

    Widening authorisation from the person to the company is the change most able to leak
    one customer's board to another, and a single method left on the wrong column would do
    it silently — the reader sees a dashboard and has no way to know a row on it is not
    theirs. So this walks every listing method from both sides rather than sampling one.
    """
    async def go():
        async with fresh() as store:
            ours = await a_user(store, "ours@example.com")
            theirs = await a_user(store, "theirs@example.com")

            for who, name, mpn in ((ours, "Gateway", "AMS1117-3.3"), (theirs, "Rival", "AMS1117-3.3")):
                line = await store.create_line(who.id, who.org_id, name)
                await store.save_bom_rows(
                    line.id, who.id, who.org_id, [{"refdes": "U1", "mpn": mpn}]
                )
                await store.create_thread(f"t-{who.id}", line.id, who.id, who.org_id, "brief")
                await store.save_findings(
                    f"t-{who.id}",
                    [Finding("availability", "u1", mpn, "No stock.", "unresolved")],
                )

            ours_lines = await store.lines_for_user(ours.org_id, ours.id)
            theirs_lines = await store.lines_for_user(theirs.org_id, theirs.id)
            return {
                "ours": [line.name for line in ours_lines],
                "theirs": [line.name for line in theirs_lines],
                # Their line, asked for with our organisation.
                "cross_line": await store.line_for_user(theirs_lines[0].id, ours.org_id, ours.id),
                "cross_thread": await store.thread_for_user(f"t-{theirs.id}", ours.org_id),
                "cross_threads": await store.threads_for_line(theirs_lines[0].id, ours.org_id),
                "cross_bom": await store.bom_for_line(theirs_lines[0].id, ours.org_id),
                "cross_rename": await store.rename_line(theirs_lines[0].id, ours.org_id, "Mine now"),
                "cross_delete": await store.delete_line(theirs_lines[0].id, ours.org_id),
                # The same MPN sits on both boards; exposure must return only ours.
                "exposure": await store.lines_exposed_to(ours.org_id, "AMS1117-3.3", ours.id),
                "memory": await store.memory_for_user(ours.org_id, part_limit=100),
            }

    seen = run(go())

    assert seen["ours"] == ["Gateway"]
    assert seen["theirs"] == ["Rival"]
    assert seen["cross_line"] is None
    assert seen["cross_thread"] is None
    assert seen["cross_threads"] == []
    assert seen["cross_bom"] == []
    assert seen["cross_rename"] is False, "a rename must not reach another organisation's line"
    assert seen["cross_delete"] is False, "a delete must not reach another organisation's line"
    assert [row["name"] for row in seen["exposure"]] == ["Gateway"]
    assert [line["name"] for line in seen["memory"]["lines"]] == ["Gateway"]


def test_joining_a_company_is_not_the_same_as_being_brought_in_on_a_project():
    """Two rules, and they arrived a month apart.

    The first was that a colleague can open the run you started, because under per-user
    ownership the second person got `None` and an end-of-life review involving three
    departments could not be told at all. The second, on 11 September, is that *in the
    company* and *on this project* are different questions: an invitation names the projects
    it brings somebody in on, and an unticked project is not visible.

    Both are asserted here, in the order they happen, because a fix to one that broke the
    other would pass a test of either alone.
    """
    async def go():
        async with fresh() as store:
            engineer = await a_user(store, "eng@example.com")
            buyer = await a_user(store, "buy@example.com")
            await store.add_user_to_organisation(buyer.id, engineer.org_id, ["procurement"])
            buyer = await store.user_by_id(buyer.id)

            line = await store.create_line(engineer.id, engineer.org_id, "Gateway")
            await store.create_thread("shared", line.id, engineer.id, engineer.org_id, "brief")

            joined = [line.name for line in await store.lines_for_user(buyer.org_id, buyer.id)]
            await store.grant_lines([line.id], buyer.id, buyer.org_id)
            brought_in = [line.name for line in await store.lines_for_user(buyer.org_id, buyer.id)]

            return (
                joined,
                brought_in,
                await store.thread_for_user("shared", buyer.org_id),
                buyer.roles,
            )

    joined, brought_in, thread, roles = run(go())

    assert joined == [], "a colleague is not on the project until somebody brings them in"
    assert brought_in == ["Gateway"]
    assert thread is not None and thread.prompt == "brief"
    # Authorship survives the move: the run is still the engineer's doing.
    assert thread.user_id != thread.org_id
    assert roles == ("procurement",)


def test_moving_someone_brings_their_work_with_them():
    """Leaving rows behind in the old organisation would strand them where nobody looks."""
    async def go():
        async with fresh() as store:
            person = await a_user(store, "mover@example.com")
            line = await store.create_line(person.id, person.org_id, "Their board")
            await store.save_bom_rows(line.id, person.id, person.org_id, [{"refdes": "U1", "mpn": "X"}])
            company = await store.create_organisation("Acme")
            await store.add_user_to_organisation(person.id, company.id, ["engineering", "quality"])

            moved = await store.user_by_id(person.id)
            return (
                moved.roles,
                [line.name for line in await store.lines_for_user(company.id, person.id)],
                await store.bom_for_line(line.id, company.id),
                [line.name for line in await store.lines_for_user(person.org_id, person.id)],
            )

    roles, here, bom, left_behind = run(go())

    assert roles == ("engineering", "quality")
    assert here == ["Their board"]
    assert len(bom) == 1
    assert left_behind == [], "nothing may be stranded in the organisation they came from"


def test_an_unknown_role_is_refused():
    """A role nobody validates is a permission that silently never applies."""
    async def go():
        async with fresh() as store:
            person = await a_user(store, "typo@example.com")
            company = await store.create_organisation("Acme")
            refused = None
            try:
                await store.add_user_to_organisation(person.id, company.id, ["enginering"])
            except UnknownRole as exc:
                refused = str(exc)
            empty = None
            try:
                await store.add_user_to_organisation(person.id, company.id, [])
            except UnknownRole as exc:
                empty = str(exc)
            return refused, empty, (await store.user_by_id(person.id)).roles

    refused, empty, roles = run(go())

    assert refused is not None and "enginering" in refused
    assert empty is not None
    assert roles == ("engineering",), "a refused write must not have moved them"


def test_a_new_account_is_an_organisation_of_one_that_can_reach_its_own_board():
    async def go():
        async with fresh() as store:
            person = await a_user(store, "solo@example.com")
            line = await store.create_line(person.id, person.org_id, "Solo")
            return person, await store.line_for_user(line.id, person.org_id, person.id)

    person, line = run(go())

    assert person.org_id
    assert person.roles == ("engineering",)
    assert line is not None


def test_the_organisation_backfill_reaches_every_row_and_is_idempotent():
    """A database written before organisations existed must come through whole.

    Built from the pre-migration DDL in an isolated schema rather than from the current
    one, for the same reason the product-line migration test is: the current schema
    cannot demonstrate that rows which predate a column survive gaining it.

    The **second** application is the one that matters. This file runs at every boot, and
    a back-fill that works once and throws on the next start takes the deployed app down
    at the worst possible moment — which is exactly what an unguarded `SET NOT NULL`
    would do here.
    """

    async def go():
        from psycopg_pool import AsyncConnectionPool

        schema_name = f"orgs_{os.urandom(8).hex()}"
        async with AsyncConnectionPool(DB_URL, min_size=1, max_size=1, open=False) as pool:
            await pool.open()
            async with pool.connection() as conn:
                await conn.execute("BEGIN")
                try:
                    await conn.execute(f'CREATE SCHEMA "{schema_name}"')
                    await conn.execute(f'SET LOCAL search_path TO "{schema_name}"')
                    await conn.execute(
                        "CREATE TABLE users (id text PRIMARY KEY, email text NOT NULL UNIQUE, "
                        "password_hash text NOT NULL, onboarded_at timestamptz, "
                        "created_at timestamptz NOT NULL DEFAULT now())"
                    )
                    await conn.execute(
                        "CREATE TABLE product_lines (id text PRIMARY KEY, user_id text NOT NULL "
                        "REFERENCES users(id) ON DELETE CASCADE, name text NOT NULL, "
                        "created_at timestamptz NOT NULL DEFAULT now(), "
                        "updated_at timestamptz NOT NULL DEFAULT now())"
                    )
                    await conn.execute(
                        "CREATE TABLE threads (id text PRIMARY KEY, line_id text NOT NULL "
                        "REFERENCES product_lines(id) ON DELETE CASCADE, user_id text NOT NULL "
                        "REFERENCES users(id) ON DELETE CASCADE, prompt text NOT NULL, "
                        "status text NOT NULL DEFAULT 'running', last_seq integer NOT NULL DEFAULT -1, "
                        "bom jsonb, created_at timestamptz NOT NULL DEFAULT now(), "
                        "updated_at timestamptz NOT NULL DEFAULT now())"
                    )
                    for statement in (
                        "INSERT INTO users (id, email, password_hash) VALUES "
                        "('u1','a@example.com','h'), ('u2','b@example.com','h')",
                        "INSERT INTO product_lines (id, user_id, name) VALUES "
                        "('l1','u1','Gateway'), ('l2','u2','Rival')",
                        "INSERT INTO threads (id, line_id, user_id, prompt) VALUES "
                        "('t1','l1','u1','brief'), ('t2','l2','u2','brief')",
                    ):
                        await conn.execute(statement)

                    async def state():
                        cursor = await conn.execute(
                            """
                            SELECT (SELECT count(*) FROM organisations),
                                   (SELECT count(*) FROM users WHERE org_id IS NULL),
                                   (SELECT count(*) FROM product_lines WHERE org_id IS NULL),
                                   (SELECT count(*) FROM threads WHERE org_id IS NULL),
                                   (SELECT count(*) FROM product_lines p JOIN users u
                                      ON u.id = p.user_id WHERE p.org_id <> u.org_id),
                                   (SELECT array_agg(DISTINCT roles::text) FROM users)
                            """
                        )
                        return await cursor.fetchone()

                    await conn.execute(SCHEMA.read_text())
                    first = await state()
                    await conn.execute(SCHEMA.read_text())
                    second = await state()
                finally:
                    await conn.rollback()
        return first, second

    first, second = run(go())

    orgs, users_without, lines_without, threads_without, mismatched, roles = first
    assert orgs == 2, "every account becomes an organisation of one"
    assert (users_without, lines_without, threads_without) == (0, 0, 0)
    assert mismatched == 0, "a row must never end up in an organisation other than its owner's"
    assert roles == ["{engineering}"], "the default keeps every existing account working"

    assert second == first, "the second boot must change nothing"


# ── the standing lists ────────────────────────────────────────────────────────


def test_no_list_and_an_empty_list_are_different_answers():
    """The distinction cannot be derived from the table, which is why the flags exist.

    An organisation that has never set an AML has not asked the question; one that has set
    an empty AML has approved nothing. Both produce zero rows, and reporting them alike
    would tell the first that every part on every board is unqualified.
    """
    async def go():
        async with fresh() as store:
            never = await a_user(store, "never@example.com")
            empty = await a_user(store, "empty@example.com")
            await store.keep_lists(empty.org_id, aml=True)

            stocked = await a_user(store, "stocked@example.com")
            await store.keep_lists(stocked.org_id, aml=True, avl=True)
            await store.qualify_part(stocked.org_id, "AMS1117-3.3", manufacturer="AMS")
            await store.approve_vendor(stocked.org_id, "JLCPCB")

            return (
                await store.approved_lists(never.org_id),
                await store.approved_lists(empty.org_id),
                await store.approved_lists(stocked.org_id),
            )

    never, empty, stocked = run(go())

    assert never.parts is None and never.vendors is None, "no list is not an empty list"
    assert empty.parts == frozenset(), "a list that approves nothing is still a list"
    assert empty.vendors is None, "keeping an AML says nothing about keeping an AVL"
    assert stocked.parts == frozenset({"AMS1117-3.3"})
    assert stocked.vendors == frozenset({"JLCPCB"})


def test_the_lists_are_matched_case_insensitively_but_stored_as_written():
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            await store.keep_lists(user.org_id, aml=True)
            await store.qualify_part(user.org_id, "ams1117-3.3")
            return await store.approved_lists(user.org_id)

    assert run(go()).parts == frozenset({"AMS1117-3.3"})


def test_one_organisations_lists_are_invisible_to_another():
    async def go():
        async with fresh() as store:
            ours = await a_user(store, "ours@example.com")
            theirs = await a_user(store, "theirs@example.com")
            for who in (ours, theirs):
                await store.keep_lists(who.org_id, aml=True)
            await store.qualify_part(ours.org_id, "OURS-ONLY")
            return await store.approved_lists(theirs.org_id)

    assert run(go()).parts == frozenset()


# ── the approvals ledger ──────────────────────────────────────────────────────


def test_an_approval_records_who_when_which_rule_and_why():
    """The four things a waiver has to carry to be a decision rather than a setting."""
    async def go():
        async with fresh() as store:
            user = await a_user(store, "engineer@example.com")
            line = await store.create_line(user.id, user.org_id, "Gateway")
            await store.create_thread("t-1", line.id, user.id, user.org_id, "brief")
            await store.record_approval(
                org_id=user.org_id,
                thread_id="t-1",
                user_id=user.id,
                user_email=user.email,
                roles=["engineering", "quality"],
                rule="part_qualification",
                subject="u1",
                mpn="NCP1117ST33T3G",
                revision="Rev C",
                rationale="Qualified on the 2025 audit; paperwork is in QMS-4417.",
            )
            return await store.approvals_for_thread("t-1", user.org_id)

    [approval] = run(go())

    assert approval["user_email"] == "engineer@example.com"
    assert approval["roles"] == ["engineering", "quality"]
    assert approval["rule"] == "part_qualification"
    assert approval["mpn"] == "NCP1117ST33T3G"
    assert approval["revision"] == "Rev C", "an approval is given under stated conditions"
    assert "QMS-4417" in approval["rationale"]
    assert approval["created_at"] is not None


def test_an_approval_survives_the_person_leaving():
    """A decision that vanishes with the account takes the audit trail with it."""
    async def go():
        async with fresh() as store:
            owner = await a_user(store, "owner@example.com")
            leaver = await a_user(store, "leaver@example.com")
            await store.add_user_to_organisation(leaver.id, owner.org_id, ["quality"])

            line = await store.create_line(owner.id, owner.org_id, "Gateway")
            await store.create_thread("t-2", line.id, owner.id, owner.org_id, "brief")
            await store.record_approval(
                org_id=owner.org_id, thread_id="t-2", user_id=leaver.id,
                user_email=leaver.email, roles=["quality"], rule="part_qualification",
                subject="u1", mpn="X", revision=None, rationale="Signed off.",
            )

            async with store.pool.connection() as conn:
                await conn.execute("DELETE FROM users WHERE id = %s", (leaver.id,))

            return await store.approvals_for_thread("t-2", owner.org_id)

    [approval] = run(go())

    assert approval["user_email"] == "leaver@example.com", "the record still names them"
    assert "Signed off." in approval["rationale"]


def test_approvals_do_not_cross_organisations():
    async def go():
        async with fresh() as store:
            ours = await a_user(store, "ours@example.com")
            theirs = await a_user(store, "theirs@example.com")
            line = await store.create_line(ours.id, ours.org_id, "Gateway")
            await store.create_thread("t-3", line.id, ours.id, ours.org_id, "brief")
            await store.record_approval(
                org_id=ours.org_id, thread_id="t-3", user_id=ours.id,
                user_email=ours.email, roles=["engineering"], rule="availability",
                subject="u1", mpn="X", revision=None, rationale="Fine.",
            )
            return await store.approvals_for_thread("t-3", theirs.org_id)

    assert run(go()) == []


# ── precedents ────────────────────────────────────────────────────────────────


def test_a_rejection_is_scoped_to_its_board_and_a_success_is_not():
    """BUILD item 15a's asymmetry, and it is physical rather than a convention.

    A part that cooks the gateway says nothing about a line running 20 °C cooler on half
    the current, so a rejection blocks only the board it happened on. A part that *worked*
    is evidence anywhere in the company — already qualified on one product is the cheap
    answer on the next, which is the whole distance between roughly $1,281 a resolution and
    $15,656.
    """
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            gateway = await store.create_line(user.id, user.org_id, "Gateway")
            sensor = await store.create_line(user.id, user.org_id, "Sensor node")

            await store.record_precedents(user.org_id, gateway.id, [
                {"signature": "thermal:ldo", "mpn": "NCP1117", "outcome": "rejected",
                 "detail": "159 °C against a 150 °C limit."},
                {"signature": "thermal:ldo", "mpn": "LD1117", "outcome": "worked"},
            ])

            return (
                await store.rejected_on(user.org_id, gateway.id),
                await store.rejected_on(user.org_id, sensor.id),
                await store.worked_anywhere(user.org_id, "thermal:ldo"),
            )

    on_gateway, on_sensor, worked = run(go())

    assert "NCP1117" in on_gateway and "159 °C" in on_gateway["NCP1117"]
    assert on_sensor == {}, "a rejection must not reach a board it never happened on"

    assert [row["mpn"] for row in worked] == ["LD1117"]
    assert worked[0]["line_name"] == "Gateway", "and it says which board earned it"


def test_a_precedent_is_one_current_fact_rather_than_a_history():
    """Upserted: what the next notice needs is the answer, not a record of it changing."""
    async def go():
        async with fresh() as store:
            user = await a_user(store)
            line = await store.create_line(user.id, user.org_id, "Gateway")
            for detail in ("first look", "second look, still no"):
                await store.record_precedents(user.org_id, line.id, [
                    {"signature": "thermal:ldo", "mpn": "NCP1117",
                     "outcome": "rejected", "detail": detail},
                ])
            return await store.rejected_on(user.org_id, line.id)

    rejected = run(go())

    assert rejected == {"NCP1117": "second look, still no"}


def test_precedents_do_not_cross_organisations():
    async def go():
        async with fresh() as store:
            ours = await a_user(store, "ours@example.com")
            theirs = await a_user(store, "theirs@example.com")
            line = await store.create_line(ours.id, ours.org_id, "Gateway")
            await store.record_precedents(ours.org_id, line.id, [
                {"signature": "thermal:ldo", "mpn": "NCP1117", "outcome": "worked"},
            ])
            return await store.worked_anywhere(theirs.org_id, "thermal:ldo")

    assert run(go()) == []


def test_joining_a_company_does_not_leave_an_empty_one_behind():
    """Signing up creates a company of one, so joining a real one abandons it.

    Found by the seed, which left three organisations behind for two people — one per join,
    empty, owned by nobody, and visible to no query anyone would think to run.
    """
    async def go():
        async with fresh() as store:
            owner = await a_user(store, "owner@example.com")
            joiner = await a_user(store, "joiner@example.com")
            vacated = joiner.org_id

            await store.add_user_to_organisation(joiner.id, owner.org_id, ["quality"])

            async with store.pool.connection() as conn:
                cursor = await conn.execute("SELECT count(*) FROM organisations")
                (total,) = await cursor.fetchone()
                cursor = await conn.execute(
                    "SELECT count(*) FROM organisations WHERE id = %s", (vacated,)
                )
                (left_behind,) = await cursor.fetchone()
            return total, left_behind

    total, left_behind = run(go())

    assert left_behind == 0, "the organisation they arrived with was abandoned"
    assert total == 1, "one company, one row"


def test_an_organisation_someone_still_belongs_to_is_never_dropped():
    """The check is explicit because most references cascade: a wrong guess deletes work."""
    async def go():
        async with fresh() as store:
            first = await a_user(store, "first@example.com")
            second = await a_user(store, "second@example.com")
            third = await a_user(store, "third@example.com")
            shared = second.org_id

            await store.add_user_to_organisation(third.id, shared, ["quality"])
            # `second` still belongs to it, so moving `third` on must not take it away.
            await store.add_user_to_organisation(third.id, first.org_id, ["engineering"])

            async with store.pool.connection() as conn:
                cursor = await conn.execute(
                    "SELECT count(*) FROM organisations WHERE id = %s", (shared,)
                )
                (survives,) = await cursor.fetchone()
            return survives, await store.user_by_id(second.id)

    survives, still_there = run(go())

    assert survives == 1
    assert still_there.org_id is not None


def test_an_organisation_holding_work_is_never_dropped_even_with_nobody_in_it():
    """Defence in depth, and deliberately not reachable through the API today.

    Moving somebody brings their lines with them, so the organisation they leave really is
    empty and is correctly removed. This exercises the guard against the state it exists
    for anyway: every reference is checked explicitly because most of them *cascade*, so a
    delete that guessed wrong would take the lines, threads, decisions and notices with it
    rather than being refused by a foreign key.
    """
    async def go():
        async with fresh() as store:
            owner = await a_user(store, "owner@example.com")
            other = await a_user(store, "other@example.com")
            holding = other.org_id
            # A line that belongs to the organisation but not to the person leaving it.
            await store.create_line(owner.id, holding, "Not theirs to take")

            async with store.pool.connection() as conn:
                await conn.execute("UPDATE users SET org_id = %s WHERE id = %s",
                                   (owner.org_id, other.id))
                await store._drop_if_vacated(conn, holding)
                cursor = await conn.execute(
                    "SELECT count(*) FROM organisations WHERE id = %s", (holding,)
                )
                (survives,) = await cursor.fetchone()
            return survives

    assert run(go()) == 1, "an organisation still holding a line was deleted"


def test_the_grant_backfill_reaches_a_world_that_predates_grants():
    """A deployed database has lines, users, and no grants, and it must come back whole.

    Since 11 September a product line is visible because there is a `line_access` row for it.
    Every database written before that table existed has none, so without a back-fill the
    deployed app returns an empty product list, a 404 for every line, and a notice that
    reaches nothing, while holding all of the data.
    """
    async def go():
        async with fresh() as store:
            eng = await a_user(store, "eng@example.com")
            await store.add_user_to_organisation(
                (await a_user(store, "buy@example.com")).id, eng.org_id, ["procurement"]
            )
            # Re-read, because moving a person does not rewrite the object that moved them.
            buyer = await store.user_by_email("buy@example.com")
            await store.create_line(eng.id, eng.org_id, "Gateway")

            # As a database from before the table came into force.
            async with store.pool.connection() as conn:
                await conn.execute("DELETE FROM line_access")

            await store.setup()
            return [
                [row.name for row in await store.lines_for_user(eng.org_id, eng.id)],
                [row.name for row in await store.lines_for_user(buyer.org_id, buyer.id)],
            ]

    assert run(go()) == [["Gateway"], ["Gateway"]], "the world comes back whole"


def test_the_grant_backfill_does_not_widen_a_later_arrangement():
    """The guard is the whole safety of it, and a per-pair guard would get this wrong.

    A company with three lines brings somebody in on two. The insert is conditional on the
    table being **empty** rather than on each pair being absent, because this file runs at
    every boot: a per-pair guard is idempotent and would hand over the third line on the next
    restart, quietly undoing the invitation.
    """
    async def go():
        async with fresh() as store:
            eng = await a_user(store, "eng@example.com")

            lines = [
                await store.create_line(eng.id, eng.org_id, name)
                for name in ("Gateway", "Sensor node", "Cabinet controller")
            ]
            await store.add_user_to_organisation(
                (await a_user(store, "new@example.com")).id, eng.org_id, ["quality"]
            )
            newcomer = await store.user_by_email("new@example.com")
            await store.grant_lines([lines[0].id, lines[1].id], newcomer.id, eng.org_id)

            # Two more boots, which is all it takes for a wrong guard to show itself.
            await store.setup()
            await store.setup()
            return [
                row.name
                for row in await store.lines_for_user(newcomer.org_id, newcomer.id)
            ]

    # Sorted, because the list comes back newest first and the order is not what this is about.
    assert sorted(run(go())) == ["Gateway", "Sensor node"], (
        "the two they were brought in on, and no more"
    )
