"""Who may answer an open decision, and what a waiver actually covers.

Two properties carry this file. **A decision names the roles qualified to answer it**, and
`/resume` enforces that at the HTTP boundary rather than inside a graph node — LangGraph
re-executes an interrupting node from the top on resume and matches resume values to
`interrupt()` calls by index, so a refusal raised inside the node would already have re-run
that node's work and would consume or misalign the pending interrupt.

And **a waiver is scoped to the candidate and revision it was granted for.** Accepting a
thermal failure on one regulator must not silently cover the next regulator a repair drops
into that slot — a part nobody looked at, carrying a temperature nobody approved.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from continuity.api import app as app_module
from continuity.engine import rules
from continuity.engine.models import Verdict
from continuity import roles as roles_module
from continuity.api import store
from continuity.roles import DEFAULT_DECISION_ROLES, ROLES_BY_RULE
from continuity.graph import nodes


def person(*roles: str):
    return SimpleNamespace(id="u", org_id="o", roles=roles)


# ── which roles a decision names ──────────────────────────────────────────────


def test_every_rule_the_engine_can_emit_names_a_role():
    """A rule added later must not quietly inherit the fallback.

    The fallback exists so an unmapped rule cannot reach *procurement* — engineering is the
    safe direction to be wrong in — but relying on it would route real circuit questions by
    accident. This is the guard that makes the map's completeness a build-time fact.

    Read from the *source* rather than from evaluating a board. A board exercises only the
    rules its own parts trigger: the obvious version of this test ran one board, covered
    nine rules of twelve, and would have passed while `energy_budget`, `footprint` and
    `rail_coverage` went unmapped.
    """
    import re

    from continuity.engine.models import RULE_NAMES

    source = (pathlib.Path(rules.__file__)).read_text()
    declared = set(re.findall(r'rule="([a-z_]+)"', source))
    declared |= set(RULE_NAMES)

    assert len(declared) >= 12, "the scan stopped finding rules; fix the scan, not the map"
    missing = sorted(declared - set(roles_module.ROLES_BY_RULE))
    assert not missing, f"no role named for {missing}"


def test_sourcing_goes_to_procurement_and_the_circuit_goes_to_engineering():
    """The split the whole mechanism exists for, asserted rather than described."""
    availability = Verdict(rule="availability", status="failed", detail="", subject="u1")
    thermal = Verdict(rule="thermal_dissipation", status="failed", detail="", subject="u1")

    assert roles_module.decision_roles(availability) == ("procurement",)
    assert roles_module.decision_roles(thermal) == ("engineering",)


def test_an_unmapped_rule_falls_back_to_engineering_not_procurement():
    unknown = Verdict(rule="a_rule_from_the_future", status="failed", detail="", subject="u1")

    assert roles_module.decision_roles(unknown) == ("engineering",)
    assert roles_module.decision_roles(None) == ("engineering",)


# ── the authorisation itself ──────────────────────────────────────────────────


def test_procurement_may_answer_a_procurement_gate():
    app_module._authorise_answer(["procurement"], person("procurement"))


def test_procurement_is_refused_at_an_engineering_gate_and_told_who_to_fetch():
    with pytest.raises(HTTPException) as refusal:
        app_module._authorise_answer(["engineering"], person("procurement"))

    assert refusal.value.status_code == 403, "the caller can already see this run"
    assert "engineering" in refusal.value.detail, "name the role they need to fetch"


def test_one_matching_role_out_of_several_is_enough():
    """A person wearing two hats answers with whichever one the question wants."""
    app_module._authorise_answer(["quality"], person("engineering", "quality"))


def test_a_question_with_no_roles_stays_answerable_by_anyone_in_the_organisation():
    """Runs paused before decisions carried roles must not become unanswerable."""
    app_module._authorise_answer([], person("procurement"))


def test_a_user_with_no_roles_at_all_is_refused_rather_than_waved_through():
    with pytest.raises(HTTPException):
        app_module._authorise_answer(["engineering"], SimpleNamespace(id="u", org_id="o"))


# ── what a waiver covers ──────────────────────────────────────────────────────


def _thermal_board():
    from tests import parts
    from tests.boards import usb_board

    return usb_board(
        regulator=parts.ldo_1a(),
        loads={"mcu": parts.esp32s3(), "display": parts.oled()},
        pinned=("mcu",),
    )


def _failure(subject: str = "regulator", rule: str = "thermal_dissipation") -> Verdict:
    return Verdict(rule=rule, status="failed", detail="159 °C junction.", subject=subject)


def test_a_waiver_holds_while_the_part_and_the_revision_stand():
    board = _thermal_board()
    waiver = nodes._waiver_key(board.slots, "thermal_dissipation", "regulator", "Rev C")

    [verdict] = nodes._apply_waivers([_failure()], [waiver], board.slots, "Rev C")

    assert verdict.status == "failed", "a waiver never repaints the verdict"
    assert verdict.accepted
    assert verdict.detail == "159 °C junction.", "the evidence the person read stays put"


def test_an_approval_for_one_candidate_does_not_carry_to_the_next():
    """BUILD's own test. This is the reason the waiver was too wide before.

    A repair swaps the regulator; the approval was for the part that was there when it was
    given, and the new one has been looked at by nobody.
    """
    from tests import parts

    board = _thermal_board()
    waiver = nodes._waiver_key(board.slots, "thermal_dissipation", "regulator", "Rev C")

    repaired = replace(
        board,
        slots={**board.slots, "regulator": board.slots["regulator"].with_part(parts.buck_3v3())},
    )
    [verdict] = nodes._apply_waivers([_failure()], [waiver], repaired.slots, "Rev C")

    assert not verdict.accepted, "the new candidate inherited an approval nobody gave it"


def test_a_change_of_revision_drops_the_waiver():
    """New operating conditions, so the approval given under the old ones is asked again."""
    board = _thermal_board()
    waiver = nodes._waiver_key(board.slots, "thermal_dissipation", "regulator", "Rev C")

    [verdict] = nodes._apply_waivers([_failure()], [waiver], board.slots, "Rev D")

    assert not verdict.accepted


def test_a_waiver_written_before_scoping_still_covers_its_finding():
    """A two-element entry sits in live checkpoints, and must keep meaning what it meant.

    A deployment must not silently widen or narrow a decision a person already made, so the
    old form covers any candidate and any revision — which is exactly what it meant when it
    was written.
    """
    board = _thermal_board()

    [verdict] = nodes._apply_waivers(
        [_failure()], [("thermal_dissipation", "regulator")], board.slots, "Rev C"
    )

    assert verdict.accepted


def test_a_waiver_does_not_leak_to_another_rule_or_another_slot():
    board = _thermal_board()
    waiver = nodes._waiver_key(board.slots, "thermal_dissipation", "regulator", "Rev C")

    other_rule = nodes._apply_waivers(
        [_failure(rule="current_budget")], [waiver], board.slots, "Rev C"
    )[0]
    other_slot = nodes._apply_waivers(
        [_failure(subject="display")], [waiver], board.slots, "Rev C"
    )[0]

    assert not other_rule.accepted
    assert not other_slot.accepted


def test_a_waived_failure_no_longer_blocks_but_is_still_reported():
    """`rules.blocking` is what the graph routes on; `rules.failures` is what a person is owed."""
    board = _thermal_board()
    waiver = nodes._waiver_key(board.slots, "thermal_dissipation", "regulator", "Rev C")

    verdicts = nodes._apply_waivers([_failure()], [waiver], board.slots, "Rev C")

    assert rules.blocking(verdicts) == []
    assert len(rules.failures(verdicts)) == 1


def test_every_desk_the_routing_table_names_is_a_role_the_product_has():
    """The reverse of the completeness test above, and it catches the other mistake.

    `ROLES_BY_RULE` named `production` for a rule while `store.ROLES` did not have it, so a
    failure could route to a department nobody could hold and nobody could answer. One
    direction asserts every rule has a desk; this one asserts every desk exists.
    """
    named = {role for roles in ROLES_BY_RULE.values() for role in roles}
    named |= set(DEFAULT_DECISION_ROLES)
    unknown = sorted(named - set(store.ROLES))
    assert not unknown, f"routed to departments the product cannot grant: {unknown}"


def test_assembly_compatibility_belongs_to_production():
    """Scenario B assigns *production confirms assembly compatibility* to these two rules.

    They answered to engineering until 10 September, which left the scenario's third
    department owning nothing at all.
    """
    assert ROLES_BY_RULE["footprint"] == ("production",)
    assert ROLES_BY_RULE["footprint_compatibility"] == ("production",)


def test_every_rule_a_desk_can_answer_has_a_desk_to_answer_it():
    """`ANSWERABLE_RULES` and `ROLES_BY_RULE` are two halves of one statement.

    A rule that a signature can clear, routed to nobody, is a decision that reaches the
    default desk and lands on engineering — which is exactly how `footprint` spent six days
    belonging to the wrong department.
    """
    for rule in sorted(roles_module.ANSWERABLE_RULES):
        assert rule in ROLES_BY_RULE, f"{rule} can be answered by nobody in particular"


def test_physics_is_not_answerable():
    """The guard the widening needs. These are arithmetic and published limits, and a
    signature against one of them would be somebody approving a calculation."""
    walls = {
        "thermal_dissipation",
        "voltage_overlap",
        "current_budget",
        "pin_budget",
        "temperature_rating",
        "energy_budget",
        "rail_coverage",
        "capacitor_requirements",
    }
    assert not (walls & roles_module.ANSWERABLE_RULES)


# ── several desks in one browser ──────────────────────────────────────────────


def test_a_browser_holds_a_session_per_desk_and_switches_between_them():
    """Walking a four-signature change on stage meant signing out three times.

    The pattern is a principal switcher holding several genuine sessions, and the
    distinction that matters is the one the *view as role* literature draws: a simulation
    is visual only and cannot act, while switching accounts can. A desk has to sign, so
    these are real sessions and the 403s still fire exactly as they did.
    """
    import asyncio

    import httpx

    from continuity.api.app import app
    from continuity.api.store import Store

    from psycopg_pool import AsyncConnectionPool

    async def go():
        url = os.environ["CONTINUITY_TEST_DB"]
        async with AsyncConnectionPool(url, min_size=1, max_size=3, open=False) as pool:
            await pool.open()
            store = Store(pool)
            await store.setup()
            async with pool.connection() as conn:
                await conn.execute(
                    "TRUNCATE users, organisations, sessions, product_lines, threads CASCADE"
                )
            previous, app.state.store = app.state.store, store
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as http:
                    await http.post(
                        "/auth/register",
                        json={"email": "one@example.com", "password": "a-good-password"},
                    )
                    first = (await http.get("/auth/me")).json()
                    await http.post(
                        "/auth/register",
                        json={"email": "two@example.com", "password": "a-good-password"},
                    )
                    second = (await http.get("/auth/me")).json()

                    held = (await http.get("/auth/sessions")).json()
                    back = await http.post(
                        "/auth/switch", json={"email": "one@example.com"}
                    )
                    now = (await http.get("/auth/me")).json()
                    stranger = await http.post(
                        "/auth/switch", json={"email": "nobody@example.com"}
                    )
                    return first, second, held, back.json(), now, stranger
            finally:
                app.state.store = previous

    first, second, held, back, now, stranger = asyncio.run(go())

    assert first["email"] == "one@example.com"
    assert second["email"] == "two@example.com", "the second sign-in is the active one"

    emails = {row["email"]: row for row in held}
    assert emails.keys() == {"one@example.com", "two@example.com"}, "both sessions are live"
    assert emails["two@example.com"]["active"] is True
    assert emails["one@example.com"]["active"] is False
    assert all("token" not in row for row in held), "a token readable by a script is not a token"

    assert back["email"] == "one@example.com"
    assert now["email"] == "one@example.com", "switching changes who /auth/me is"

    assert stranger.status_code == 403, "no path to a session this browser did not sign into"


test_a_browser_holds_a_session_per_desk_and_switches_between_them = pytest.mark.skipif(
    not os.environ.get("CONTINUITY_TEST_DB"), reason="needs a database"
)(test_a_browser_holds_a_session_per_desk_and_switches_between_them)
