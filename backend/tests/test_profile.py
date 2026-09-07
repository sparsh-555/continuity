from dataclasses import replace

import pytest

from continuity.engine.models import Requirements
from continuity.profile import OperatingProfile, RailProfile
from tools.eol_differential import AMS1117, LINE_B, OUTPUT_CAPACITOR, make_board


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


def stored_line_b():
    """LINE_B's gateway board, expressed the way the database holds it."""
    return OperatingProfile(
        ambient_c=LINE_B.ambient_c,
        ambient_source=LINE_B.ambient_basis,
        mounting="1000 mm² top and back copper, 1/16in FR-4, 1 oz",
        rails={
            "vin": RailProfile(
                voltage=LINE_B.input_voltage,
                i_limit=LINE_B.input_limit,
                basis=LINE_B.input_basis,
                members=("u1",),
            ),
            "3v3": RailProfile(
                source="u1",
                members=("u2", "c1"),
                i_load=LINE_B.load,
                i_load_basis=LINE_B.load_basis,
            ),
        },
    )


def stored_bom():
    return [
        {"refdes": "u1", "mpn": AMS1117.mpn, "populated": True},
        {"refdes": "u2", "mpn": LINE_B.load_part.mpn, "populated": True},
        {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn, "populated": True},
    ]


def stored_specs():
    return {
        AMS1117.mpn: AMS1117,
        LINE_B.load_part.mpn: LINE_B.load_part,
        OUTPUT_CAPACITOR.mpn: OUTPUT_CAPACITOR,
    }


def test_a_board_built_from_storage_checks_the_same_as_one_built_by_hand():
    """The property the matrix rests on, and the one most able to break it silently.

    `tools/eol_differential.make_board` is the reference: it is what the demo's arithmetic
    was verified against. If a board assembled out of the database disagrees with it, the
    matrix on screen is checking a different circuit from the one anybody reviewed, and
    every cell would still look plausible.
    """
    from continuity.engine.rules import evaluate
    from continuity.profile import board_from

    stored = board_from(stored_line_b(), stored_bom(), stored_specs())
    reference = make_board(LINE_B, AMS1117)

    assert stored.requirements.ambient_c == reference.requirements.ambient_c
    assert stored.requirements.ambient_source == reference.requirements.ambient_source
    assert stored.requirements.mounting == reference.requirements.mounting
    assert set(stored.slots) == set(reference.slots)
    assert {s: slot.part.mpn for s, slot in stored.slots.items()} == {
        s: slot.part.mpn for s, slot in reference.slots.items()
    }
    for rail_id, rail in reference.rails.items():
        built = stored.rails[rail_id]
        assert (built.voltage, built.source, built.i_limit, built.i_load) == (
            rail.voltage, rail.source, rail.i_limit, rail.i_load
        )
        assert set(built.members) == set(rail.members)

    # The verdicts are what actually matter, so compare those too.
    def summary(board):
        return sorted(
            (v.rule, v.scope, v.status, v.detail) for v in evaluate(board)
        )

    assert summary(stored) == summary(reference)


def test_a_do_not_populate_row_is_not_on_the_board():
    """A DNP line is on the document and not on the circuit."""
    from continuity.profile import board_from

    bom = [*stored_bom(), {"refdes": "c9", "mpn": OUTPUT_CAPACITOR.mpn, "populated": False}]

    board = board_from(stored_line_b(), bom, stored_specs())

    assert "c9" not in board.slots


def test_a_part_that_could_not_be_resolved_is_left_out_rather_than_faked():
    from continuity.profile import board_from

    bom = [*stored_bom(), {"refdes": "u9", "mpn": "NOT-IN-ANY-CATALOGUE", "populated": True}]

    board = board_from(stored_line_b(), bom, stored_specs())

    assert "u9" not in board.slots
    assert set(board.slots) == {"u1", "u2", "c1"}


def test_rail_membership_never_names_a_slot_that_is_not_there():
    """A rail listing a part the board does not carry would send rules looking for it."""
    from continuity.profile import board_from

    profile = stored_line_b()
    board = board_from(profile, stored_bom()[:1], {AMS1117.mpn: AMS1117})

    for rail in board.rails.values():
        assert set(rail.members) <= set(board.slots)
