"""Acceptance matrix for the sourced end-of-life regulator comparison.

The runnable demo prints the same result for a hardware review, but this test keeps the
per-board result, the declared-load path, and the source distinction from drifting.
"""

import pytest
from dataclasses import replace

from continuity.engine import packages
from continuity.engine.draw import consumers, rail_draw
from continuity.engine.rules import evaluate
from tools.eol_differential import AMS1117, LD1117, LINES, NCP1117, TLV1117, make_board


def verdict(board, rule: str, scope: str | None = None):
    """Return the one verdict for a rule in this deliberately small board."""
    found = [
        item for item in evaluate(board)
        if item.rule == rule and (scope is None or item.scope == scope)
    ]
    assert len(found) == 1
    return found[0]


def test_declared_load_replaces_the_partial_component_sum():
    """A signed power budget is complete; absent one, the old component sum remains."""
    declared = make_board(LINES[0], AMS1117)
    rail = declared.rails["3v3"]
    assert rail_draw(declared, rail, consumers(declared, rail)) == (0.150, [])

    summed = replace(rail, i_load=None, i_load_basis=None)
    assert rail_draw(declared, summed, consumers(declared, summed)) == (0.350, ["c1"])


def test_ams1117_thermal_passes_at_both_published_extremes():
    """The incumbent conclusion survives AMS's 46–90 °C/W published spread.

    This is the claim the demo leans on hardest — the boards are fine today, so the
    substitution is the whole problem — and it must not depend on which end of the
    range you believe. Asserted on the junction temperatures rather than on the
    statuses, because a status can stay `pass` while the arithmetic drifts.
    """
    expected = {
        46.0: {"A": 36.7, "B": 77.8, "C": 79.0},
        90.0: {"A": 48.0, "B": 109.3, "C": 102.0},
    }
    for theta, per_line in expected.items():
        regulator = replace(AMS1117, theta_ja=theta)
        for line in LINES:
            board = make_board(line, regulator)
            thermal = verdict(board, "thermal_dissipation")
            power = (line.input_voltage - 3.3) * line.load
            junction = board.requirements.ambient_c + power * theta

            assert junction == pytest.approx(per_line[line.id], abs=0.5)
            assert junction < AMS1117.t_j_max
            # 90 °C/W crosses R5's independent 60 °C rise advisory band on the gateway,
            # which is a margin attribute rather than a failure.
            assert thermal.status == "satisfied"


def test_ld1117_clears_every_line_but_only_just_on_the_gateway():
    """The candidate whose problem is margin rather than a failure.

    110 °C/W is ST's own published SOT-223 figure, from Table 2 of DocID2572 Rev 38.
    Read the revision before changing it: Rev 26 publishes junction-to-ambient for
    TO-220 only, and reading that table alone is how this part briefly looked as though
    ST had never characterised it.

    On the gateway it lands at 123.5 °C against a 125 °C limit — satisfied, and nobody
    would ship it. That is the whole argument for carrying margin as an attribute of a
    passing check rather than collapsing it into a green tick.
    """
    expected = {"A": (53.0, "satisfied"), "B": (123.5, "satisfied"), "C": (112.4, "satisfied")}
    for line in LINES:
        thermal = verdict(make_board(line, LD1117), "thermal_dissipation")
        junction = line.ambient_c + (line.input_voltage - 3.3) * line.load * LD1117.theta_ja
        temperature, status = expected[line.id]

        assert junction == pytest.approx(temperature, abs=0.5)
        assert junction < LD1117.t_j_max
        assert thermal.status == status

    gateway = next(line for line in LINES if line.id == "B")
    margin = LD1117.t_j_max - (
        gateway.ambient_c + (gateway.input_voltage - 3.3) * gateway.load * LD1117.theta_ja
    )
    assert margin == pytest.approx(1.5, abs=0.5)


def test_tlv1117_fails_only_the_12v_line_and_stays_thermally_safe():
    for line in LINES:
        board = make_board(line, TLV1117)
        voltage = verdict(board, "voltage_overlap", scope="vin")
        thermal = verdict(board, "thermal_dissipation")
        assert (voltage.status == "failed") is (line.id == "C")
        assert thermal.status == "satisfied"


def test_ncp1117_fails_thermal_only_on_gateway_at_its_junction_limit():
    for line in LINES:
        thermal = verdict(make_board(line, NCP1117), "thermal_dissipation")
        assert (thermal.status == "failed") is (line.id == "B")
        if line.id == "B":
            assert "159" in thermal.detail
            assert "150 °C limit" in thermal.detail
            assert "125 °C limit" not in thermal.detail


def test_every_theta_ja_in_the_matrix_comes_from_a_datasheet():
    """No cell in this demo rests on the package table.

    The table is a fallback for design mode, where a brief has to be answered even when
    nobody published a figure. A substitution decision is a different question, and all
    four of these parts have a manufacturer's number behind them — so every θJA on
    screen cites a datasheet URL, and none cites us.
    """
    for regulator in (AMS1117, TLV1117, LD1117, NCP1117):
        assert regulator.theta_ja is not None
        for line in LINES:
            thermal = verdict(make_board(line, regulator), "thermal_dissipation")
            theta = next(row for row in thermal.evidence if row.field.startswith("θJA"))

            assert theta.field == "θJA (datasheet)"
            assert theta.source == regulator.datasheet
            assert theta.source != packages.THETA_JA_SOURCE


def test_the_sourced_fixture_exposes_the_two_board_specific_candidate_failures():
    """The engine distinguishes a voltage-limited and a thermally-limited replacement."""
    assert [verdict(make_board(line, TLV1117), "voltage_overlap", "vin").status for line in LINES] == [
        "satisfied", "satisfied", "failed"
    ]
    assert [verdict(make_board(line, NCP1117), "thermal_dissipation").status for line in LINES] == [
        "satisfied", "failed", "satisfied"
    ]


def test_the_printer_counts_the_labels_the_engine_actually_returns():
    """The report's vocabulary against the engine's, rather than against a memory of it.

    `_print_line` counted `pass`, `warn` and `fail` for as long as those labels existed and
    kept counting them afterwards, so every cell of the matrix read "0 pass, 0 FAIL,
    0 warn" while `evaluate` was answering correctly underneath. Nothing failed, because
    nothing compared the two lists.
    """
    from typing import get_args

    from continuity.engine.models import CheckStatus
    from tools.eol_differential import COVERAGE_LABELS

    assert set(COVERAGE_LABELS) == set(get_args(CheckStatus))

    observed = {
        item.status
        for line in LINES
        for regulator in (AMS1117, TLV1117, LD1117, NCP1117)
        for item in evaluate(make_board(line, regulator))
    }
    assert observed <= set(COVERAGE_LABELS)
