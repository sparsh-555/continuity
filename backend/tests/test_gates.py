"""AML and AVL: the two questions a company asks that physics does not.

BUILD item 13's test is the one that shapes everything here — **the gate fires on an
unqualified part with no electrical failure**. A design that only asked about qualification
once something else had already gone wrong would clear an unqualified part every time it
happened to be electrically fine, which is most of the time. So these are their own rules,
and they run on every board like all the others.

The two lists are deliberately separate. A part can be qualified and only available from a
vendor nobody has approved; a vendor can be approved and stocking a part nobody has
qualified. One combined list makes both of those unsayable, and they are exactly the cases
an end-of-life substitution runs into.
"""

from __future__ import annotations

from dataclasses import replace

from continuity.engine import rules
from continuity.engine.models import ApprovedLists
from continuity.roles import decision_roles
from tests import parts
from tests.boards import usb_board


def board_with(approved: ApprovedLists, regulator=None):
    """A board that passes every electrical check, so only the gates can fail it."""
    board = usb_board(
        regulator=regulator if regulator is not None else parts.ldo_600ma(),
        loads={"mcu": parts.esp32s3()},
    )
    return replace(board, approved=approved)


def verdicts_for(board, rule: str):
    return [v for v in rules.evaluate(board) if v.rule == rule]


# ── the gate does not wait for something to break ─────────────────────────────


def test_an_unqualified_part_fails_on_a_board_with_nothing_electrically_wrong():
    """BUILD item 13's test, and the reason the gate is a rule rather than a consequence."""
    board = board_with(ApprovedLists(parts=frozenset({"SOMETHING-ELSE"})))

    electrical = [
        v for v in rules.failures(rules.evaluate(board))
        if v.rule not in {"part_qualification", "source_approval"}
    ]
    gate = [v for v in verdicts_for(board, "part_qualification") if v.status == "failed"]

    assert electrical == [], "the board has to be clean, or this proves nothing"
    assert gate, "an unqualified part passed because nothing else was broken"
    assert "not been qualified" in gate[0].detail


def test_a_qualified_part_satisfies_the_gate():
    board = board_with(ApprovedLists(parts=frozenset({"AP2114H-3.3TRG1", "ESP32-S3-WROOM-1-N8R2"})))

    assert all(v.status == "satisfied" for v in verdicts_for(board, "part_qualification"))


# ── no list is not an empty list ──────────────────────────────────────────────


def test_an_organisation_with_no_list_is_not_told_every_part_is_unqualified():
    """The distinction the five labels exist for.

    A company that has never set an AML has not asked this question, and answering it for
    them would report a policy breach on every part of every board.
    """
    board = board_with(ApprovedLists())

    [aml] = verdicts_for(board, "part_qualification")
    [avl] = verdicts_for(board, "source_approval")

    assert aml.status == "not_applicable" and avl.status == "not_applicable"
    assert "keeps no approved-manufacturer list" in aml.detail
    assert aml.subject == rules.BOARD_SUBJECT, "no component is at fault for an absent policy"


def test_an_empty_list_approves_nothing_and_says_so():
    """Set-and-empty is a real answer; it is *not* the same as never set."""
    board = board_with(ApprovedLists(parts=frozenset()))

    failures = [v for v in verdicts_for(board, "part_qualification") if v.status == "failed"]

    assert failures, "an empty list approves nothing, which is a decision somebody made"
    assert all(v.status != "not_applicable" for v in verdicts_for(board, "part_qualification"))


# ── the two lists are independent ─────────────────────────────────────────────


def test_a_qualified_part_from_an_unapproved_source_fails_only_the_vendor_gate():
    """The case one combined list could not express."""
    board = board_with(
        ApprovedLists(
            parts=frozenset({"AP2114H-3.3TRG1", "ESP32-S3-WROOM-1-N8R2"}),
            vendors=frozenset({"SOME-OTHER-DISTRIBUTOR"}),
        )
    )

    assert all(v.status == "satisfied" for v in verdicts_for(board, "part_qualification"))
    vendor = [v for v in verdicts_for(board, "source_approval") if v.status == "failed"]
    assert vendor, "an unapproved source passed"
    assert "approved-vendor list" in vendor[0].detail


def test_an_approved_vendor_does_not_qualify_an_unqualified_part():
    board = board_with(
        ApprovedLists(parts=frozenset(), vendors=frozenset({"JLCPCB"}))
    )

    assert all(v.status == "satisfied" for v in verdicts_for(board, "source_approval"))
    assert any(v.status == "failed" for v in verdicts_for(board, "part_qualification"))


def test_keeping_one_list_and_not_the_other_is_allowed():
    board = board_with(ApprovedLists(vendors=frozenset({"JLCPCB"})))

    [aml] = verdicts_for(board, "part_qualification")
    assert aml.status == "not_applicable"
    assert all(v.status == "satisfied" for v in verdicts_for(board, "source_approval"))


def test_a_part_with_no_recorded_source_is_a_gap_rather_than_a_breach():
    """Nobody said it comes from an unapproved vendor; we do not know where it comes from."""
    board = board_with(
        ApprovedLists(vendors=frozenset({"JLCPCB"})),
        regulator=replace(parts.ldo_600ma(), distributor=None),
    )

    regulator = [v for v in verdicts_for(board, "source_approval") if v.subject == "regulator"]

    assert regulator[0].status == "evidence_missing"


# ── who each gate belongs to ──────────────────────────────────────────────────


def test_qualification_goes_to_engineering_and_quality_and_sourcing_to_procurement():
    """Engineering says the part is right; quality says it is allowed. Both, not either."""
    from continuity.engine.models import Verdict

    qualification = Verdict(rule="part_qualification", status="failed", detail="", subject="u1")
    sourcing = Verdict(rule="source_approval", status="failed", detail="", subject="u1")

    assert decision_roles(qualification) == ("engineering", "quality")
    assert decision_roles(sourcing) == ("procurement",)
