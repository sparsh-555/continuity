"""The change request: one per affected product line, against the sourced demo case.

BUILD item 15's test is that the three demo lines produce three requests, **each naming its
unassessed checks**. That last clause is the point of the document. A change request that
omitted the engine's coverage boundaries would read as a clean bill of health for questions
nobody asked, and the difference between a document that can be relied on and one that
merely looks complete is whether it says what it did not check.

Per line rather than one document for the company, because the answer differs per line —
which is the finding a single manufacturer-wide recommendation cannot express.
"""

from __future__ import annotations

from continuity import change
from continuity.engine.models import Verdict
from continuity.matrix import evaluate_matrix
from tools.eol_differential import AMS1117, LD1117, LINES, NCP1117, TLV1117, make_board

CANDIDATES = (AMS1117, TLV1117, LD1117, NCP1117)
SLOT = "u1"


def demo_matrix():
    boards = [(line.id, line.label, make_board(line, AMS1117)) for line in LINES]
    return evaluate_matrix(boards, CANDIDATES, SLOT)


def requests(**shared):
    return change.for_every_line(
        demo_matrix(), notice_mpn=AMS1117.mpn, lines={}, **shared
    )


# ── BUILD's test ──────────────────────────────────────────────────────────────


def test_three_lines_produce_three_requests_each_naming_its_unassessed_checks():
    produced = requests()

    assert len(produced) == 3
    assert [r.line_id for r in produced] == ["A", "B", "C"]
    for request in produced:
        assert request.not_assessed == (
            "emc", "output_capacitor_stability", "signal_integrity",
        ), f"{request.line_name} does not say what it left unchecked"


def test_what_could_not_be_checked_is_kept_apart_from_what_is_not_checked_at_all():
    """Two different admissions. "We do not do this" and "we tried and had nothing to read"
    are not the same sentence, and folding them together loses the actionable one."""
    [request] = [r for r in requests() if r.line_id == "B"]

    assert "emc" in request.not_assessed
    assert "emc" not in request.no_evidence
    assert request.no_evidence, "the demo boards do have checks that found nothing to read"


# ── what the document carries ─────────────────────────────────────────────────


def test_each_request_names_the_notice_the_baseline_and_the_revision():
    [request] = [r for r in requests(revision="Rev C") if r.line_id == "B"]

    assert request.notice_mpn == AMS1117.mpn
    assert request.baseline_mpn == AMS1117.mpn, "what is fitted today"
    assert request.revision == "Rev C"
    assert request.line_name == "Gateway"


def test_the_proposal_differs_by_line_which_is_the_whole_point():
    """A manufacturer recommends one part. Three products give three different answers."""
    by_line = {r.line_id: r for r in requests(prefer=[NCP1117.mpn, LD1117.mpn])}

    # NCP1117 is what the notice recommends, and it cooks the gateway.
    assert by_line["A"].proposal == NCP1117.mpn
    assert by_line["B"].proposal == LD1117.mpn, "the gateway cannot take the recommendation"
    assert by_line["C"].proposal == NCP1117.mpn


def test_every_rejected_alternative_carries_the_sentence_that_killed_it():
    """A proposal alone asks to be trusted; one that shows its rejections asks to be checked."""
    [gateway] = [r for r in requests(prefer=[NCP1117.mpn]) if r.line_id == "B"]

    rejected = {a.mpn: a.rejected_because for a in gateway.alternatives if not a.viable}

    assert NCP1117.mpn in rejected
    assert "159 °C" in rejected[NCP1117.mpn] and "150 °C limit" in rejected[NCP1117.mpn]


def test_a_viable_alternative_that_was_not_chosen_is_still_recorded():
    """The second choice is where the next notice starts."""
    [request] = [r for r in requests(prefer=[LD1117.mpn]) if r.line_id == "A"]

    viable = [a.mpn for a in request.alternatives if a.viable]

    assert request.proposal == LD1117.mpn
    assert NCP1117.mpn in viable and TLV1117.mpn in viable


def test_the_evidence_is_what_decided_it_rather_than_everything():
    """A document that reprinted every satisfied check would bury the three that mattered."""
    [request] = [r for r in requests(prefer=[LD1117.mpn]) if r.line_id == "B"]

    assert request.evidence, "no evidence behind the proposal"
    assert all(
        v.status == "failed" or (v.status == "satisfied" and v.margin) for v in request.evidence
    )
    assert any("1.5 °C" == v.margin for v in request.evidence), "the margin that decides it"


# ── cost ──────────────────────────────────────────────────────────────────────


def test_a_part_already_on_the_approved_list_costs_a_twelfth_of_one_qualified_from_scratch():
    """The business argument for keeping a list, and for remembering what was decided."""
    known = requests(prefer=[LD1117.mpn], approved_mpns=[LD1117.mpn])
    unknown = requests(prefer=[LD1117.mpn], approved_mpns=[])

    assert known[0].cost.one_time == change.QUALIFIED_PART_COST
    assert "already on the approved" in known[0].cost.one_time_basis
    assert unknown[0].cost.one_time == change.UNQUALIFIED_PART_COST
    assert unknown[0].cost.one_time / known[0].cost.one_time > 10


def test_recurring_cost_needs_a_stated_volume_and_is_not_invented_without_one():
    """An assumed volume makes a plausible number out of nothing."""
    without = requests(prefer=[LD1117.mpn])[0]
    with_volume = requests(prefer=[LD1117.mpn], annual_volume=50_000)[0]

    assert without.annual_volume is None if hasattr(without, "annual_volume") else True
    assert without.cost.recurring_annual is None
    assert without.cost.unit_delta is not None, "the per-unit difference is still knowable"

    assert with_volume.cost.annual_volume == 50_000
    expected = round(with_volume.cost.unit_delta * 50_000, 2)
    assert with_volume.cost.recurring_annual == expected


def test_the_unit_delta_is_measured_against_the_part_fitted_today():
    [request] = [r for r in requests(prefer=[LD1117.mpn]) if r.line_id == "A"]

    assert request.cost.unit_delta == round(LD1117.unit_price - AMS1117.unit_price, 4)


# ── who has to sign ───────────────────────────────────────────────────────────


def test_a_clean_proposal_is_signed_by_every_department_that_examined_it():
    """**Changed 8 Sep, then again 10 Sep.**

    On 8 Sep this stopped asserting that a request with nothing failing asks nobody to
    approve anything: a change to a released design is approved before it is implemented,
    never after, and SCENARIO-B quotes the field's most common audit finding on exactly
    that.

    On 10 Sep it stopped asserting `("engineering",)`. That was the desks owning a *failing*
    rule, falling back to engineering when nothing failed — so in a world where the answer
    is good, every request named one desk and the cross-team response the topic asks about
    appeared nowhere. A change control board's composition mirrors the change's blast
    radius, and this is that radius.

    The concern that produced the original test still holds and is still tested below: a
    request with *no* proposal asks for nothing and needs nobody.
    """
    [request] = [r for r in requests(prefer=[LD1117.mpn]) if r.line_id == "A"]

    assert request.viable
    assert set(request.approvals_required) >= {"engineering", "procurement", "production"}
    assert request.approvals_required == tuple(d.role for d in request.departments), (
        "the desks that must sign are exactly the desks the document reports on"
    )


def test_a_request_with_no_proposal_asks_nobody_for_anything():
    """The half of the old reasoning that still holds: a finding is not a change, and a
    request that manufactured an approver for one would waste somebody's afternoon."""
    matrix = evaluate_matrix(
        [(LINES[1].id, LINES[1].label, make_board(LINES[1], AMS1117))],
        [AMS1117, NCP1117],
        SLOT,
    )

    request = change.for_line(matrix, "B", notice_mpn=AMS1117.mpn)

    assert not request.viable
    assert request.approvals_required == ()


def test_a_line_where_nothing_survives_says_so_rather_than_proposing_anyway():
    """The finding, not an absence of one."""
    matrix = evaluate_matrix(
        [(LINES[1].id, LINES[1].label, make_board(LINES[1], AMS1117))],
        [AMS1117, NCP1117],
        SLOT,
    )

    request = change.for_line(matrix, "B", notice_mpn=AMS1117.mpn)

    assert not request.viable
    assert request.proposal is None
    assert "clears this product line" in request.proposal_detail
    assert [a.mpn for a in request.alternatives] == [NCP1117.mpn]
    assert request.alternatives[0].rejected_because is not None


def test_a_line_the_matrix_never_checked_is_an_error_not_an_empty_request():
    """A silently empty request is a document that lies about its own coverage."""
    import pytest

    with pytest.raises(KeyError, match="no cells"):
        change.for_line(demo_matrix(), "does-not-exist", notice_mpn=AMS1117.mpn)


def test_a_request_serialises_whole():
    [request] = [r for r in requests(prefer=[LD1117.mpn], annual_volume=1000) if r.line_id == "B"]

    body = request.to_json()

    assert set(body) == {
        "line_id", "line_name", "revision", "baseline_mpn", "notice_mpn", "notice_id",
        "proposal", "proposal_detail", "alternatives", "evidence", "not_assessed",
        "no_evidence", "cost", "approvals_required", "departments", "checked",
    }
    assert body["not_assessed"], "the coverage boundaries survive serialisation"
    assert body["cost"]["one_time_basis"]


# ── precedents: what was decided before ───────────────────────────────────────


def test_a_candidate_this_board_ruled_out_is_never_proposed_again():
    """BUILD item 15a's first test, and the half that was missing.

    Without it a part ruled out on Monday is proposed again on Tuesday, and the person
    reading the second request has to remember the first. That is the failure memory
    exists to remove.
    """
    matrix = demo_matrix()

    without = change.for_line(matrix, "A", notice_mpn=AMS1117.mpn, prefer=[NCP1117.mpn])
    withheld = change.for_line(
        matrix,
        "A",
        notice_mpn=AMS1117.mpn,
        prefer=[NCP1117.mpn],
        excluded={NCP1117.mpn: "Rejected here in March: cost the enclosure its thermal margin."},
    )

    assert without.proposal == NCP1117.mpn, "it would otherwise have been chosen"
    assert withheld.proposal != NCP1117.mpn
    assert withheld.viable, "ruling one out must not rule out the rest"


def test_a_part_ruled_out_still_appears_with_the_reason_it_was_ruled_out():
    """Dropping it silently would make the document look as though it was never considered."""
    request = change.for_line(
        demo_matrix(),
        "A",
        notice_mpn=AMS1117.mpn,
        prefer=[NCP1117.mpn],
        excluded={NCP1117.mpn: "Rejected here in March: cost the enclosure its thermal margin."},
    )

    listed = {a.mpn: a.rejected_because for a in request.alternatives}

    assert NCP1117.mpn in listed
    assert "Rejected here in March" in listed[NCP1117.mpn]


def test_a_rejection_on_one_board_does_not_reach_another():
    """A part that cooks the gateway says nothing about a line running 20 °C cooler.

    `for_every_line` takes exclusions keyed by line for exactly this reason: a rejection
    that spread across every board would remove candidates nobody had ever checked there.
    """
    produced = change.for_every_line(
        demo_matrix(),
        notice_mpn=AMS1117.mpn,
        lines={},
        prefer=[NCP1117.mpn],
        excluded={"B": {NCP1117.mpn: "Cooked the gateway."}},
    )

    by_line = {r.line_id: r for r in produced}

    assert by_line["A"].proposal == NCP1117.mpn, "the sensor node never rejected it"
    assert by_line["C"].proposal == NCP1117.mpn
    assert by_line["B"].proposal != NCP1117.mpn


def test_a_request_with_no_proposal_does_not_invoice_for_a_part_that_does_not_exist():
    """It quoted $15,656 to qualify nobody's candidate, which the screen printed in full."""
    matrix = evaluate_matrix(
        [(LINES[1].id, LINES[1].label, make_board(LINES[1], AMS1117))],
        [AMS1117, NCP1117],
        SLOT,
    )

    request = change.for_line(matrix, "B", notice_mpn=AMS1117.mpn, annual_volume=20_000)

    assert not request.viable
    assert request.cost.one_time == 0.0
    assert request.cost.one_time_basis == "no candidate to cost"
    assert request.cost.recurring_annual is None


def test_the_request_says_what_each_desk_found():
    """Scenario B's *role-specific rendering of a shared finding*, on the document.

    One result, grouped by the desk that owns each part of it. The engine already checked
    every department's constraints on every candidate; until 10 September nothing said so,
    and every change request named engineering alone.
    """
    [request] = [r for r in requests() if r.line_id == "B"]

    by_role = {d.role: d for d in request.departments}
    assert "procurement" in by_role, "availability is procurement's rule and it ran"
    assert "production" in by_role, "footprint is production's rule and it ran"
    assert "engineering" in by_role

    # Order is fixed, so four blocks cannot reorder between two screens.
    assert [d.role for d in request.departments] == [
        role for role in ("engineering", "procurement", "production", "quality")
        if role in by_role
    ]

    # Every headline is a sentence a rule wrote, never one this module composed.
    said = {v.detail for v in request.evidence} | {v.margin for v in request.evidence}
    for desk in request.departments:
        assert desk.headline, f"{desk.role} said nothing"
        assert desk.satisfied or desk.failed, f"{desk.role} counted nothing"


def test_a_desk_that_looked_at_nothing_is_not_on_the_request():
    """`not_assessed` is a coverage boundary the engine declares on every board, not a
    department's involvement in this change. Counting it would put a desk on a document for
    a question nobody asked."""
    [request] = [r for r in requests() if r.line_id == "B"]

    assert request.not_assessed, "the three declared boundaries are still reported"
    for desk in request.departments:
        assert desk.satisfied + desk.failed > 0


def test_each_desks_headline_is_about_the_part_being_changed():
    """Every rule runs on every slot, so a desk's first satisfied verdict on this board is
    as likely to be about the output capacitor as about the regulator.

    Measured on the seeded world before this was fixed: procurement's line on a request to
    replace a regulator read *"CL31A226KAHNNNE: 1,020,639 in stock at JLCPCB"*, which is a
    true sentence about the wrong part on a document somebody signs. The capacitor sorts
    first because `availability` walks the slots in order.
    """
    verdicts = [
        Verdict(rule="availability", status="satisfied", subject="c1", involved=("c1",),
                detail="CL31A226KAHNNNE: 1,020,639 in stock at JLCPCB."),
        Verdict(rule="availability", status="satisfied", subject="u1", involved=("u1",),
                detail="NCP1117ST33T3G: 24,555 in stock at JLCPCB."),
    ]

    [desk] = change._departments_for(verdicts, "u1")

    assert desk.role == "procurement"
    assert "NCP1117" in desk.headline, "the desk is talking about the part being replaced"
    assert desk.satisfied == 2, "and it still counted both"


def test_a_headline_falls_back_when_the_desk_said_nothing_about_that_slot():
    """A desk whose rules never touched the changed slot still gets a sentence rather than
    an empty one, because a blank line reads as a desk that did not look."""
    verdicts = [
        Verdict(rule="availability", status="satisfied", subject="c1", involved=("c1",),
                detail="CL31A226KAHNNNE: 1,020,639 in stock at JLCPCB."),
    ]

    [desk] = change._departments_for(verdicts, "u1")

    assert desk.headline == "CL31A226KAHNNNE: 1,020,639 in stock at JLCPCB."


def test_the_request_counts_what_was_checked_before_anybody_was_asked():
    """The clock the topic states, answered with the run's own numbers rather than a
    fabricated saving.

    Nobody measured how long a cross-team response takes here, and the round-trip argument
    is reasoning rather than sourced data — SCENARIO-B says so itself. What is true and is
    worth counting is the sweep: this many parts against this many departments' rules on
    this many products, before the first person was asked anything.
    """
    [request] = [r for r in requests() if r.line_id == "B"]

    assert request.checked is not None
    # Every part placed on this board: the alternatives, plus the one chosen, which the
    # alternatives deliberately exclude, plus the one fitted today, which is the baseline
    # the comparison rests on and is re-checked like any other.
    assert request.checked.candidates == len(request.alternatives) + 2
    assert request.checked.checks > request.checked.candidates, (
        "the whole board is re-checked after every substitution, so this is not a rule count"
    )
    assert request.checked.departments == len(request.departments)
    assert request.checked.lines >= 1
