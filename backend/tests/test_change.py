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


def test_a_clean_proposal_asks_nobody_to_approve_anything():
    """A request that manufactured an approver would waste somebody's afternoon."""
    [request] = [r for r in requests(prefer=[LD1117.mpn]) if r.line_id == "A"]

    assert request.viable
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
        "no_evidence", "cost", "approvals_required",
    }
    assert body["not_assessed"], "the coverage boundaries survive serialisation"
    assert body["cost"]["one_time_basis"]
