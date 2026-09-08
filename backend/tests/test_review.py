"""One substitution on one board, and who is asked about it.

The distinction this module exists for: a part that fails a *department's* rule is not
unviable, it is somebody else's decision. Everything else here is the engine, already tested
elsewhere — what these tests hold is the routing.
"""

from __future__ import annotations

import pytest

from continuity import review
from continuity.engine.models import ApprovedLists
from dataclasses import replace

from tools.eol_differential import (
    AMS1117,
    LD1117,
    LINE_B,
    NCP1117,
    OUTPUT_CAPACITOR,
    TLV1117,
    make_board,
)


def gateway(*, approved: ApprovedLists | None = None):
    """The 45 °C, 5 V, 420 mA board. NCP1117 cooks it; LD1117 holds it and is unqualified."""
    board = make_board(LINE_B, AMS1117)
    return replace(board, approved=approved) if approved is not None else board


QUALIFIED = ApprovedLists(
    parts=frozenset(
        {AMS1117.mpn, NCP1117.mpn, TLV1117.mpn, LINE_B.load_part.mpn, OUTPUT_CAPACITOR.mpn}
    ),
    vendors=frozenset({"JLCPCB"}),
)
"""Everything the seeded company ships, which is what an approved list is.

**Including the module and the capacitor**, which is not a detail: a list holding only the
regulators makes every board fail qualification for parts nobody proposed to change, and the
seed found that the hard way. LD1117 is absent because nothing ships with it, which is the
reason it is the interesting candidate."""


def attempts_on(board, candidates):
    return [review.attempt(board, "u1", part) for part in candidates]


# ── what the engine said ──────────────────────────────────────────────────────


def test_the_manufacturers_own_recommendation_is_blocked_on_physics():
    made = review.attempt(gateway(), "u1", NCP1117)

    assert not made.clear
    assert made.physical, "159 °C against a 150 °C limit is not a signature away"
    assert not made.gated
    assert "150" in made.blocking[0].detail


def test_a_part_that_is_only_unqualified_is_gated_rather_than_blocked():
    """The finding the change request could not express: electrically perfect, and not
    ours to approve."""
    made = review.attempt(gateway(approved=QUALIFIED), "u1", LD1117)

    assert not made.clear
    assert made.gated, "nothing physical failed"
    assert [verdict.rule for verdict in made.gates] == ["part_qualification"]


def test_a_qualified_part_that_clears_everything_is_clear():
    made = review.attempt(gateway(approved=QUALIFIED), "u1", TLV1117)

    assert made.clear
    assert made.blocking == ()


# ── who is asked ──────────────────────────────────────────────────────────────


def test_a_clear_part_is_proposed_and_engineering_signs_it():
    """Approved before implementation, never after — a released design is not changed by
    a tool on its own."""
    proposal = review.choose(attempts_on(gateway(approved=QUALIFIED), [TLV1117]))

    assert proposal.mpn == TLV1117.mpn
    assert proposal.roles == ("engineering",)
    assert proposal.gate_rule is None
    assert not proposal.conditional


def test_the_decision_leaves_engineering_when_only_a_department_rule_stands():
    proposal = review.choose(attempts_on(gateway(approved=QUALIFIED), [NCP1117, LD1117]))

    assert proposal.mpn == LD1117.mpn, "the one that works is the one to ask about"
    assert proposal.conditional
    assert proposal.gate_rule == "part_qualification"
    assert "quality" in proposal.roles, "qualification is not engineering's to grant"


def test_a_clear_part_is_preferred_over_one_that_needs_a_signature():
    """Cheapest first: an already-approved part resolves for roughly a twelfth of what
    qualifying one costs, so it is not a tie break."""
    proposal = review.choose(attempts_on(gateway(approved=QUALIFIED), [LD1117, TLV1117]))

    assert proposal.mpn == TLV1117.mpn
    assert not proposal.conditional


def test_the_caller_s_order_decides_between_two_clear_parts():
    board = gateway(
        approved=ApprovedLists(
            parts=frozenset(
                {TLV1117.mpn, LD1117.mpn, LINE_B.load_part.mpn, OUTPUT_CAPACITOR.mpn}
            )
        )
    )

    first = review.choose(attempts_on(board, [LD1117, TLV1117]))
    second = review.choose(attempts_on(board, [TLV1117, LD1117]))

    assert (first.mpn, second.mpn) == (LD1117.mpn, TLV1117.mpn)


def test_nothing_is_proposed_when_everything_fails_on_physics():
    """The finding, rather than the absence of one."""
    assert review.choose(attempts_on(gateway(approved=QUALIFIED), [NCP1117])) is None


def test_a_part_this_board_already_ruled_out_is_never_proposed_again():
    """The entire point of remembering a rejection."""
    board = gateway(approved=QUALIFIED)

    proposal = review.choose(
        attempts_on(board, [TLV1117]),
        excluded={TLV1117.mpn: "Rejected on the 2025 audit for this product."},
    )

    assert proposal is None


# ── what it says ──────────────────────────────────────────────────────────────


def test_a_blocked_candidate_is_narrated_in_the_rule_s_own_words():
    made = review.attempt(gateway(), "u1", NCP1117)

    said = review.narrate(made)

    assert made.blocking[0].detail in said, "the arithmetic is the rule's, not ours"


def test_a_gated_candidate_says_it_works_before_it_says_who_must_sign():
    made = review.attempt(gateway(approved=QUALIFIED), "u1", LD1117)

    said = review.narrate(made)

    assert "electrically fine" in said
    assert "approved manufacturer list" in said


def test_a_clear_candidate_carries_its_margin():
    made = review.attempt(gateway(approved=QUALIFIED), "u1", TLV1117)

    assert "to spare" in review.narrate(made)


@pytest.mark.parametrize("candidate", [NCP1117, LD1117, TLV1117])
def test_the_part_reported_is_the_part_evaluated(candidate):
    """Read back off the board rather than copied from the argument, as the matrix does."""
    assert review.attempt(gateway(), "u1", candidate).mpn == candidate.mpn
