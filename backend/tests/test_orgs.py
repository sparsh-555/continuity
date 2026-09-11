"""Who is in the company, and which projects each of them was brought in on.

Scenario B is a cross-team response and every surface in this product showed the work while
saying nothing about the team. These are the two questions a judge asks first: who else is
on this, and what can they see.

**The rule under test is two rules.** Membership says somebody is in the company — they can
be asked to sign, their desk counts, their name appears in the roster. Access says which
projects they can open, and it is a grant per project. Before 11 September the company was
the unit of sharing and the two were the same question; they are not any more, and a fix to
one that broke the other is exactly what these tests are for.

Skipped unless `CONTINUITY_TEST_DB` is set.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity.api.app import app
from continuity.api.store import Store

DB_URL = os.environ.get("CONTINUITY_TEST_DB")

pytestmark = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")


def run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def a_world():
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=3, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE users, organisations, sessions, product_lines, threads CASCADE")
        previous = app.state.store
        app.state.store = store
        try:
            yield store
        finally:
            app.state.store = previous


@asynccontextmanager
async def a_client(email: str, password: str = "a-good-password"):
    """One signed-in browser, which is what a person is here."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
    ) as http:
        response = await http.post(
            "/auth/register", json={"email": email, "password": password}
        )
        assert response.status_code == 201, response.text
        yield http, (await http.get("/auth/me")).json()


@asynccontextmanager
async def a_company():
    """An engineer with three projects, and a second account that has not been invited yet."""
    async with a_world() as store:
        async with a_client("eng@example.com") as (engineer, me):
            lines = {}
            for name in ("Gateway", "Sensor node", "Cabinet controller"):
                created = (await engineer.post("/lines", json={"name": name})).json()
                lines[name] = created["id"]
            async with a_client("priya@example.com") as (priya, them):
                yield store, engineer, me, priya, them, lines


def test_a_person_who_has_just_signed_up_is_a_company_of_one():
    """She is not in anybody else's company until somebody invites her, and her own is hers."""
    async def go():
        async with a_company() as (store, _engineer, me, priya, them, _lines):
            return (
                (await priya.get("/lines")).json(),
                me["org_id"] == them["org_id"],
            )

    hers, same_company = run(go())

    assert hers == []
    assert not same_company, "an account is not in the engineer's company until it is invited"


def test_the_roster_names_everyone_and_what_each_of_them_holds():
    async def go():
        async with a_company() as (store, engineer, _me, _priya, _them, lines):
            await engineer.post(
                "/orgs/invites",
                json={
                    "email": "priya@example.com",
                    "roles": ["procurement"],
                    "line_ids": [lines["Gateway"], lines["Sensor node"]],
                },
            )
            return (await engineer.get("/orgs/members")).json()

    roster = run(go())
    by_email = {row["email"]: row for row in roster}

    assert set(by_email) == {"eng@example.com", "priya@example.com"}
    assert by_email["eng@example.com"]["roles"] == ["engineering"]
    assert len(by_email["eng@example.com"]["line_ids"]) == 3
    # Every account starts holding engineering — signing up makes you an engineer — and an
    # invitation adds to that rather than replacing it.
    assert by_email["priya@example.com"]["roles"] == ["engineering", "procurement"]
    assert len(by_email["priya@example.com"]["line_ids"]) == 2


def test_an_invitation_brings_somebody_in_on_the_ticked_projects_and_no_others():
    """The checkbox has to mean something. This is the test that says it does."""
    async def go():
        async with a_company() as (store, engineer, _me, priya, _them, lines):
            await engineer.post(
                "/orgs/invites",
                json={
                    "email": "priya@example.com",
                    "roles": ["procurement"],
                    "line_ids": [lines["Gateway"], lines["Sensor node"]],
                },
            )
            mine = (await priya.get("/lines")).json()
            untitled = await priya.get(f"/lines/{lines['Cabinet controller']}")
            return mine, untitled

    visible, untitled = run(go())

    assert sorted(line["name"] for line in visible) == ["Gateway", "Sensor node"]
    assert untitled.status_code == 404, (
        "a project nobody brought her in on is not hers to know about"
    )


def test_an_invitation_to_an_address_with_no_account_says_so():
    """Rather than pretending to send something. There is no token, no expiry and no
    acceptance route behind this, and a 201 here would be a lie the next screen repeats."""
    async def go():
        async with a_company() as (store, engineer, _me, _priya, _them, lines):
            return await engineer.post(
                "/orgs/invites",
                json={
                    "email": "nobody@example.com",
                    "roles": ["quality"],
                    "line_ids": [lines["Gateway"]],
                },
            )

    response = run(go())

    assert response.status_code == 404
    assert "no account uses nobody@example.com" in response.json()["detail"]


def test_an_invitation_adds_desks_and_never_takes_one_away():
    """*Bring this person in* and *take this away from this person* are different acts.

    Only the first is a thing this product claims to do, so inviting somebody who is already
    here must not quietly strip the desk they were holding — which is the failure a
    replacement would have had, and the one that would have broken the demonstration.
    """
    async def go():
        async with a_company() as (store, engineer, _me, _priya, _them, lines):
            await engineer.post(
                "/orgs/invites",
                json={"email": "priya@example.com", "roles": ["procurement"], "line_ids": []},
            )
            await engineer.post(
                "/orgs/invites",
                json={
                    "email": "priya@example.com",
                    "roles": ["quality"],
                    "line_ids": [lines["Gateway"]],
                },
            )
            return (await engineer.get("/orgs/members")).json()

    priya = next(row for row in run(go()) if row["email"] == "priya@example.com")

    assert priya["roles"] == ["engineering", "procurement", "quality"], (
        "engineering from signing up, and both invited desks on top of it"
    )


def test_re_inviting_somebody_to_a_project_they_hold_changes_nothing():
    """Two rows for one grant would make the roster count it twice."""
    async def go():
        async with a_company() as (store, engineer, _me, _priya, _them, lines):
            body = {
                "email": "priya@example.com",
                "roles": ["procurement"],
                "line_ids": [lines["Gateway"]],
            }
            first = (await engineer.post("/orgs/invites", json=body)).json()
            second = (await engineer.post("/orgs/invites", json=body)).json()
            return first, second, (await engineer.get("/orgs/members")).json()

    first, second, roster = run(go())

    assert first["granted"] == 1
    assert second["granted"] == 0, "the second invitation grants nothing new"
    priya = next(row for row in roster if row["email"] == "priya@example.com")
    assert len(priya["line_ids"]) == 1


def test_a_project_somebody_makes_is_one_they_can_open():
    """The grant is written with the line, in one transaction.

    Visibility is a grant now rather than a property of the company, so a line its own
    author cannot open is the failure this would have had — and it is invisible from the
    outside, because the row exists and the list simply does not show it.
    """
    async def go():
        async with a_company() as (store, engineer, _me, _priya, _them, _lines):
            made = (await engineer.post("/lines", json={"name": "Bench supply"})).json()
            return (
                [line["name"] for line in (await engineer.get("/lines")).json()],
                await engineer.get(f"/lines/{made['id']}"),
            )

    names, opened = run(go())

    assert "Bench supply" in names
    assert opened.status_code == 200


def test_the_notice_reaches_only_the_projects_the_reader_holds():
    """A banner announcing three affected products to somebody who can open two would be
    announcing work they cannot see, and the review would check boards that are not theirs."""
    async def go():
        async with a_company() as (store, engineer, me, priya, them, lines):
            await engineer.post(
                "/orgs/invites",
                json={
                    "email": "priya@example.com",
                    "roles": ["procurement"],
                    "line_ids": [lines["Gateway"]],
                },
            )
            for name, line_id in lines.items():
                await engineer.put(
                    f"/lines/{line_id}/bom",
                    json={"rows": [{"refdes": "U1", "mpn": "AMS1117-3.3", "populated": True}]},
                )
            theirs = (await engineer.get("/exposure?mpn=AMS1117-3.3")).json()
            mine = (await priya.get("/exposure?mpn=AMS1117-3.3")).json()
            return theirs, mine

    theirs, mine = run(go())

    assert len(theirs) == 3
    assert [row["name"] for row in mine] == ["Gateway"], (
        "the reach is narrowed to the reader's own projects"
    )
