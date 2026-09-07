from dataclasses import replace

import pytest

from continuity.engine.models import Requirements
from continuity.profile import OperatingProfile, RailProfile
from tools.eol_differential import AMS1117, LINE_B, make_board


def line_b_profile() -> OperatingProfile:
    return OperatingProfile(
        ambient_c=LINE_B.ambient_c,
        ambient_source=LINE_B.ambient_basis,
        mounting="1000 mm² top and back copper, 1/16in FR-4, 1 oz",
        rails={
            "vin": RailProfile(LINE_B.input_voltage, LINE_B.input_limit, LINE_B.input_basis),
            # No voltage: the 3V3 rail takes it from whichever regulator is in the
            # slot. A stored 3.3 would overwrite a candidate's own output with the
            # number that was true the day the line was entered.
            "3v3": RailProfile(i_load=LINE_B.load, i_load_basis=LINE_B.load_basis),
        },
    )


def test_stored_line_b_profile_builds_the_same_requirements_and_rails_as_reference():
    expected = make_board(LINE_B, AMS1117)
    actual = line_b_profile().applied_to(
        make_board(
            replace(LINE_B, ambient_c=25, ambient_basis="wrong", load=0.1),
            AMS1117,
        )
    )
    assert actual.requirements == expected.requirements
    assert actual.rails == expected.rails


def test_profile_round_trips_and_rejects_unknown_keys():
    profile = line_b_profile()
    assert OperatingProfile.from_json(profile.to_json()) == profile
    with pytest.raises(ValueError, match="unknown operating profile keys"):
        OperatingProfile.from_json({**profile.to_json(), "future": True})
    with pytest.raises(ValueError, match="unknown rail profile keys"):
        OperatingProfile.from_json({**profile.to_json(), "rails": {"vin": {"future": 1}}})


def test_profile_preserves_unstated_mounting():
    profile = OperatingProfile(45, "stored")
    base = Requirements(mounting="existing")
    assert profile.to_requirements(base).mounting == "existing"


def test_profile_rejects_a_rail_that_is_not_on_the_board():
    with pytest.raises(ValueError, match="absent from board"):
        OperatingProfile(45, "stored", rails={"missing": RailProfile(1.0)}).applied_to(
            make_board(LINE_B, AMS1117)
        )


def test_an_unstated_rail_field_does_not_erase_what_the_board_carries():
    """A profile is a set of statements, and silence is not a statement.

    The gateway states its 5 V supply and its signed load. It says nothing about where
    the ceiling came from, and writing `None` over that would destroy "USB Type-C default
    Rp advertisement" — a provenance string every rule that uses the ceiling cites.
    """
    board = make_board(LINE_B, AMS1117)
    stated_only_voltage = OperatingProfile(
        45, "stored", rails={"vin": RailProfile(voltage=9.0)}
    ).applied_to(board)

    assert stated_only_voltage.rails["vin"].voltage == 9.0
    assert stated_only_voltage.rails["vin"].basis == board.rails["vin"].basis
    assert stated_only_voltage.rails["vin"].i_limit == board.rails["vin"].i_limit
    assert stated_only_voltage.rails["vin"].members == board.rails["vin"].members


def test_applying_a_profile_leaves_the_original_board_alone():
    board = make_board(LINE_B, AMS1117)
    before = board.rails["vin"].voltage

    OperatingProfile(45, "stored", rails={"vin": RailProfile(voltage=9.0)}).applied_to(board)

    assert board.rails["vin"].voltage == before


def test_a_run_on_a_line_with_a_profile_uses_the_line_ambient(monkeypatch):
    """The done-condition from BUILD: the ambient reaches the run without being passed in.

    A stored profile that no run reads is a capability with no consumer — the exact shape
    this project already rejected for `p_dis_min`. So this asserts the value arrives at
    `Requirements`, where every thermal verdict reads it.
    """
    from continuity.graph import nodes

    emitted: list[str] = []

    class Events:
        def reasoning(self, slot, text):
            emitted.append(text)
            return {"type": "reasoning", "text": text}

    monkeypatch.setattr(nodes, "_emit", lambda event: None)

    applied = nodes._with_line_profile(
        Events(),
        Requirements(ambient_c=25),
        OperatingProfile(45, "gateway operating profile Rev C", mounting="1000 mm² copper").to_json(),
    )

    assert applied.ambient_c == 45
    assert applied.ambient_source == "gateway operating profile Rev C"
    assert applied.mounting == "1000 mm² copper"
    assert any("45 °C" in line for line in emitted)


def test_an_unreadable_stored_profile_says_so_rather_than_passing_silently(monkeypatch):
    from continuity.graph import nodes

    emitted: list[str] = []

    class Events:
        def reasoning(self, slot, text):
            emitted.append(text)
            return {"type": "reasoning", "text": text}

    monkeypatch.setattr(nodes, "_emit", lambda event: None)

    applied = nodes._with_line_profile(Events(), Requirements(ambient_c=25), {"nonsense": 1})

    assert applied.ambient_c == 25
    assert any("could not be read" in line for line in emitted)
