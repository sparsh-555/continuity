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


# ── where candidates come from ────────────────────────────────────────────────


CATALOGUE = {part.mpn: part for part in (AMS1117, NCP1117, LD1117, TLV1117, OUTPUT_CAPACITOR)}


async def catalogue(mpn):
    return CATALOGUE.get(mpn)


def found(**kwargs):
    import asyncio

    return asyncio.run(review.candidates_for(retiring=AMS1117, resolve=catalogue, **kwargs))


def test_the_manufacturers_recommendation_is_tried_first():
    """It is the answer the notice puts in front of everybody, and the first thing a reader
    asks about if it is missing."""
    candidates = found(
        notice_replacement=NCP1117.mpn, approved=[TLV1117.mpn], named=[LD1117.mpn]
    )

    assert [c.part.mpn for c in candidates] == [NCP1117.mpn, TLV1117.mpn, LD1117.mpn]
    assert candidates[0].origin == review.NOTICE_ORIGIN
    assert candidates[1].origin == review.APPROVED_ORIGIN
    assert candidates[2].origin == review.NAMED_ORIGIN


def test_the_part_being_retired_is_not_a_candidate_to_replace_itself():
    assert AMS1117.mpn not in [
        c.part.mpn for c in found(approved=[AMS1117.mpn, TLV1117.mpn])
    ]


def test_a_part_named_twice_is_tried_once():
    candidates = found(notice_replacement=NCP1117.mpn, approved=[NCP1117.mpn])

    assert [c.part.mpn for c in candidates] == [NCP1117.mpn]
    assert candidates[0].origin == review.NOTICE_ORIGIN, "the first claim on it wins"


def test_the_approved_list_is_filtered_by_category():
    """An approved list is a hundred parts of every kind. Offering a capacitor as a
    substitute for a regulator is noise."""
    assert [c.part.mpn for c in found(approved=[OUTPUT_CAPACITOR.mpn, TLV1117.mpn])] == [
        TLV1117.mpn
    ]


def test_a_part_somebody_named_is_not_second_guessed_on_category():
    """A person naming a part is a decision. Refusing it because our category strings
    disagree would be the tool overruling them."""
    assert [c.part.mpn for c in found(named=[OUTPUT_CAPACITOR.mpn])] == [OUTPUT_CAPACITOR.mpn]


def test_a_part_the_distributor_has_never_heard_of_is_dropped_rather_than_carried():
    assert found(named=["NOT-A-REAL-PART"]) == ()


def test_the_catalogue_is_searched_after_the_approved_list_and_before_anything_typed():
    """The order is the argument. The manufacturer's answer, then what we already ship,
    then what the distributor has, and a typed part last because nobody should have to."""
    import asyncio

    async def search(retiring):
        assert retiring.mpn == AMS1117.mpn
        return [LD1117]

    candidates = asyncio.run(
        review.candidates_for(
            retiring=AMS1117,
            resolve=catalogue,
            notice_replacement=NCP1117.mpn,
            approved=[TLV1117.mpn],
            search=search,
            named=[OUTPUT_CAPACITOR.mpn],
        )
    )

    assert [c.part.mpn for c in candidates] == [
        NCP1117.mpn, TLV1117.mpn, LD1117.mpn, OUTPUT_CAPACITOR.mpn
    ]
    assert candidates[2].origin == review.CATALOGUE_ORIGIN


def test_the_catalogue_is_trusted_rather_than_re_filtered_on_category():
    """The search was already constrained by the kind of part and the package. Comparing
    its results against the retiring part's category string compares two taxonomies that
    agree only by luck — JLCPCB writes "Voltage Regulators - Linear, Low Drop Out (LDO)
    Regulators" where another source writes "LDO Regulator" — and an exact match empties
    this leg without saying so. A wrong-kind part is caught by the engine, visibly.
    """
    import asyncio

    async def search(_retiring):
        return [LD1117]

    candidates = asyncio.run(
        review.candidates_for(retiring=AMS1117, resolve=catalogue, search=search)
    )

    assert [c.part.mpn for c in candidates] == [LD1117.mpn]


def test_the_approved_list_is_still_filtered_by_category():
    """It is an arbitrary list of the company's part numbers and it holds every kind."""
    import asyncio

    candidates = asyncio.run(
        review.candidates_for(
            retiring=AMS1117, resolve=catalogue, approved=[OUTPUT_CAPACITOR.mpn, TLV1117.mpn]
        )
    )

    assert [c.part.mpn for c in candidates] == [TLV1117.mpn]


def test_a_catalogue_hit_already_on_the_approved_list_keeps_the_cheaper_claim():
    """Being on the approved list is the more useful thing to know about a part, and it is
    the claim that arrived first."""
    import asyncio

    async def search(_retiring):
        return [TLV1117]

    candidates = asyncio.run(
        review.candidates_for(
            retiring=AMS1117, resolve=catalogue, approved=[TLV1117.mpn], search=search
        )
    )

    assert [c.origin for c in candidates] == [review.APPROVED_ORIGIN]


def test_a_qualitative_margin_is_not_reported_as_headroom():
    """`availability` reports "lifecycle concern", which is a real margin and reads as
    nonsense in a sentence about clearing checks. Seen live before it was caught."""
    from continuity.engine.models import Verdict

    made = review.Attempt(
        candidate=NCP1117,
        verdicts=(
            Verdict(rule="availability", status="satisfied", detail="in stock",
                    subject="u1", margin="lifecycle concern"),
        ),
    )

    assert made.margin is None
    assert "to spare" not in review.narrate(made)
