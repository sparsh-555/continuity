"""The substitution matrix, against the sourced demo case.

BUILD item 12: *the demo case produces the full matrix, every cell attributable to a
board, a candidate and an owning department.*

The parts and the operating conditions here are the real ones — `tools/eol_differential`
is the same data, and the arithmetic in these cells is the arithmetic on stage. If a cell
stops landing, or lands for the wrong reason, it fails here rather than in front of judges.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from continuity.matrix import evaluate_matrix, substitute
from tools.eol_differential import (
    AMS1117,
    LD1117,
    LINES,
    NCP1117,
    TLV1117,
    make_board,
)

CANDIDATES = (AMS1117, TLV1117, LD1117, NCP1117)
SLOT = "u1"


def demo_matrix():
    boards = [(line.id, line.label, make_board(line, AMS1117)) for line in LINES]
    return evaluate_matrix(boards, CANDIDATES, SLOT)


# ── the grid itself ───────────────────────────────────────────────────────────


def test_the_demo_case_produces_a_full_grid_with_no_gaps():
    matrix = demo_matrix()

    assert len(matrix.lines) == 3
    assert len(matrix.candidates) == 4
    assert len(matrix.cells) == 12, "three product lines by four candidates, none missing"
    for line_id in matrix.lines:
        for mpn in matrix.candidates:
            assert matrix.cell(line_id, mpn) is not None, f"no cell for {mpn} on {line_id}"


def test_every_cell_names_its_board_its_candidate_and_who_owns_it():
    """Attribution is the whole point: a verdict with no cell is an opinion."""
    matrix = demo_matrix()

    # The ownership invariant below is `False == False` on a grid where nothing fails, so
    # pin that both kinds of cell are actually present before asserting anything about it.
    assert any(cell.failures for cell in matrix.cells), "no failing cell to attribute"
    assert any(cell.ok for cell in matrix.cells), "no passing cell to leave unattributed"

    for cell in matrix.cells:
        assert cell.line_id and cell.line_name
        assert cell.candidate.mpn
        assert cell.verdicts, "a cell with no verdicts is a hole pretending to be a result"
        # A failing cell lands on somebody's desk; a passing one puts no decision anywhere.
        assert bool(cell.departments) == bool(cell.failures)


def test_the_incumbent_row_is_not_reported_as_a_substitution():
    """A board running the part it already runs is the status quo, not a proposed change."""
    matrix = demo_matrix()

    for line_id in matrix.lines:
        today = matrix.cell(line_id, AMS1117.mpn)
        proposed = matrix.cell(line_id, NCP1117.mpn)

        assert today.is_incumbent
        assert today.incumbent_mpn is None
        assert proposed.incumbent_mpn == AMS1117.mpn


# ── the beats the demo rests on ───────────────────────────────────────────────


def test_the_incumbent_passes_on_every_line():
    """The premise of the whole scenario: nothing is broken until the notice arrives."""
    matrix = demo_matrix()

    for line_id in matrix.lines:
        cell = matrix.cell(line_id, AMS1117.mpn)
        assert cell.ok, f"the incumbent fails on {cell.line_name}: {cell.failures}"


def test_the_manufacturers_recommendation_cooks_the_gateway():
    """NCP1117 is what the notice recommends, and it is the beat the demo turns on."""
    matrix = demo_matrix()

    gateway = matrix.cell("B", NCP1117.mpn)
    assert not gateway.ok
    thermal = [v for v in gateway.failures if v.rule == "thermal_dissipation"]
    assert thermal, f"expected a thermal failure, got {[v.rule for v in gateway.failures]}"
    assert "159 °C" in thermal[0].detail and "150 °C limit" in thermal[0].detail
    assert gateway.departments == ("engineering",), "a junction temperature is not a buying call"


def test_the_low_voltage_part_fails_only_the_twelve_volt_line():
    matrix = demo_matrix()

    for line_id in matrix.lines:
        cell = matrix.cell(line_id, TLV1117.mpn)
        assert cell.ok is (line_id != "C"), f"{cell.line_name} was the wrong answer"

    cabinet = matrix.cell("C", TLV1117.mpn)
    assert [v.rule for v in cabinet.failures] == ["voltage_overlap"]


def test_the_st_part_clears_every_board_but_only_just():
    """Satisfied and unshippable is the distinction margin exists to carry."""
    matrix = demo_matrix()

    for line_id in matrix.lines:
        assert matrix.cell(line_id, LD1117.mpn).ok

    assert matrix.cell("B", LD1117.mpn).margin == "1.5 °C"
    assert matrix.cell("A", LD1117.mpn).margin == "72 °C"


def test_only_two_candidates_survive_every_board():
    """A part that passes two lines of three breaks a product; it is not a near miss."""
    assert demo_matrix().viable_on_every_board() == (AMS1117.mpn, LD1117.mpn)


# ── coverage is reported, not hidden ──────────────────────────────────────────


def test_every_cell_reports_all_five_labels_including_the_zeroes():
    """The counts a reader needs in order to compare two cells of different shapes."""
    counts = demo_matrix().cell("B", AMS1117.mpn).counts

    assert set(counts) == {
        "satisfied", "failed", "not_applicable", "not_assessed", "evidence_missing",
    }
    assert counts["satisfied"] > 0
    assert counts["not_assessed"] == 3, "the engine's declared coverage boundaries"
    assert sum(counts.values()) == len(demo_matrix().cell("B", AMS1117.mpn).verdicts)


def test_a_failing_cell_is_owned_by_the_desk_that_can_answer_it():
    matrix = demo_matrix()

    assert matrix.cell("B", NCP1117.mpn).departments == ("engineering",)
    assert matrix.cell("C", TLV1117.mpn).departments == ("engineering",)
    assert matrix.departments() == ("engineering",), "nothing in this case is a buying call"


# ── substitution ──────────────────────────────────────────────────────────────


def test_substituting_records_what_is_being_replaced():
    board = make_board(LINES[1], AMS1117)

    after = substitute(board, SLOT, NCP1117)

    assert after.slots[SLOT].part.mpn == NCP1117.mpn
    assert after.slots[SLOT].baseline.mpn == AMS1117.mpn
    assert board.slots[SLOT].part.mpn == AMS1117.mpn, "the original board is untouched"


def test_substituting_a_part_for_itself_records_no_baseline():
    board = make_board(LINES[1], AMS1117)

    after = substitute(board, SLOT, AMS1117)

    assert after.slots[SLOT].baseline is None


def test_the_cell_reports_the_candidate_it_actually_checked():
    """Read off the board, never copied from the request.

    A repair changes the candidate mid-flight, and a result carrying the mpn that was asked
    for rather than the one that was checked attributes a verdict to a part nobody
    evaluated.
    """
    renamed = replace(NCP1117, mpn="NCP1117-RELABELLED")
    boards = [(LINES[1].id, LINES[1].label, make_board(LINES[1], AMS1117))]

    [cell] = evaluate_matrix(boards, [renamed], SLOT).cells

    assert cell.candidate.mpn == "NCP1117-RELABELLED"


def test_a_board_without_the_slot_is_refused_rather_than_skipped():
    """A silently missing row is a matrix that lies about its own coverage."""
    boards = [(LINES[0].id, LINES[0].label, make_board(LINES[0], AMS1117))]

    with pytest.raises(KeyError, match="no slot"):
        evaluate_matrix(boards, [NCP1117], "does-not-exist")


def test_the_matrix_is_reproducible():
    """Rehearsal and stage must produce the same grid. No model touches any of this."""
    def grid():
        return [
            (c.line_id, c.candidate.mpn, c.ok, c.margin, c.departments, len(c.verdicts))
            for c in demo_matrix().cells
        ]

    assert grid() == grid()


def test_a_candidate_with_a_different_output_moves_the_rail_it_makes():
    """Otherwise every part downstream is checked against a voltage the board would not have.

    A 5 V regulator dropped into a 3.3 V rail must not pass because nothing on the board
    was told the rail had moved. The demo's candidates are all 3.3 V fixed, so this is a
    guard rather than a beat — and a guard is what it needs to be, because the failure is
    silent.
    """
    five_volt = replace(AMS1117, mpn="MADE-UP-5V", vout_min=5.0, vout_max=5.0)
    board = make_board(LINES[1], AMS1117)

    after = substitute(board, SLOT, five_volt)

    assert after.rails["3v3"].voltage == 5.0
    assert after.rails["vin"].voltage == board.rails["vin"].voltage, "the input is untouched"

    boards = [(LINES[1].id, LINES[1].label, board)]
    [cell] = evaluate_matrix(boards, [five_volt], SLOT).cells
    over_voltage = [v for v in cell.failures if v.rule == "voltage_overlap"]
    assert over_voltage, "5 V on a rail feeding 3.6 V parts has to fail somewhere"


def test_an_adjustable_part_leaves_the_rail_alone():
    """A range does not set a rail; the feedback network does, and it is not in the BOM."""
    adjustable = replace(AMS1117, mpn="MADE-UP-ADJ", vout_min=1.25, vout_max=13.8)
    board = make_board(LINES[1], AMS1117)

    after = substitute(board, SLOT, adjustable)

    assert after.rails["3v3"].voltage == board.rails["3v3"].voltage
