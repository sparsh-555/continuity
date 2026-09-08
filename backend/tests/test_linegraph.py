"""The power tree of a product line that already exists.

Every graph Continuity has drawn until now came out of a design run. These come out of the
database: a bill of materials and an operating profile, which between them state which part
makes which rail and which parts that rail feeds. The tests are about what the picture is
allowed to claim — no connection nobody stated, no verdict nobody produced.
"""

from __future__ import annotations

from continuity.linegraph import SUPPLY_ID, graph_from

GATEWAY_PROFILE = {
    "ambient_c": 45,
    "rails": {
        "3v3": {"source": "u1", "members": ["u2", "c1"], "voltage": None, "i_load": 0.42},
        "vin": {
            "source": None,
            "members": ["u1"],
            "voltage": 5.0,
            "basis": "USB Type-C default Rp advertisement",
        },
    },
}

GATEWAY_BOM = [
    {"refdes": "u1", "mpn": "AMS1117-3.3", "manufacturer": "AMS", "footprint": "SOT-223"},
    {"refdes": "u2", "mpn": "ESP32-C3-MINI-1-N4", "manufacturer": "Espressif"},
    {"refdes": "c1", "mpn": "CL31A226KAHNNNE", "manufacturer": "Samsung"},
]


def graph():
    return graph_from(GATEWAY_PROFILE, GATEWAY_BOM)


def test_the_tree_the_profile_states_is_the_tree_that_is_drawn():
    """Supply into the regulator, regulator out to what it feeds."""
    edges = {(edge["from"], edge["to"]) for edge in graph().edges}

    assert edges == {(SUPPLY_ID, "u1"), ("u1", "u2"), ("u1", "c1")}


def test_the_rail_that_nothing_on_the_board_makes_is_the_supply():
    supply = graph().supply

    assert supply["id"] == SUPPLY_ID
    assert supply["voltage"] == 5.0
    assert "USB" in supply["label"], "the profile's own words for where power comes from"


def test_the_part_that_makes_a_rail_is_in_the_power_tier():
    """Structure decides before any word does: u1 sources 3v3, so it is power."""
    tiers = {slot["id"]: slot["tier"] for slot in graph().slots}

    assert tiers["u1"] == "power"
    assert tiers["u2"] == "core"
    assert tiers["c1"] == "passives"


def test_nothing_claims_to_have_been_checked():
    """A fitted part no rule has looked at is `unchecked`. `pass` would be a verdict
    nobody produced, on a board nobody ran."""
    drawn = graph()

    assert {slot["status"] for slot in drawn.slots} == {"unchecked"}
    assert {edge["status"] for edge in drawn.edges} == {"unchecked"}


def test_every_node_carries_the_part_the_bill_records():
    parts = {slot["id"]: slot["part"] for slot in graph().slots}

    assert parts["u1"]["mpn"] == "AMS1117-3.3"
    assert parts["u1"]["package"] == "SOT-223"
    assert parts["u2"]["manufacturer"] == "Espressif"


def test_only_power_edges_are_drawn():
    """A rail states what it feeds. Nothing here has read a schematic, so an edge between
    the MCU and a sensor would be an invention."""
    assert {edge["kind"] for edge in graph().edges} == {"power"}


def test_a_rail_naming_a_part_that_is_not_fitted_draws_no_edge():
    profile = {
        "rails": {
            "3v3": {"source": "u1", "members": ["u2", "u9"], "voltage": 3.3},
            "vin": {"source": None, "members": ["u1"], "voltage": 5.0},
        }
    }

    drawn = graph_from(profile, GATEWAY_BOM)

    assert not any(edge["to"] == "u9" for edge in drawn.edges), "u9 is on no bill"


def test_an_unpopulated_row_is_not_on_the_board():
    """A do-not-populate line is on the document and not on the product."""
    bom = [*GATEWAY_BOM, {"refdes": "c9", "mpn": "SPARE", "populated": False}]

    assert {slot["id"] for slot in graph_from(GATEWAY_PROFILE, bom).slots} == {"u1", "u2", "c1"}


def test_a_line_with_no_profile_still_shows_its_parts():
    """The honest picture of a bill nobody has described the power tree of: the parts are
    real, and there is nothing to say about how they connect."""
    drawn = graph_from(None, GATEWAY_BOM)

    assert len(drawn.slots) == 3
    assert drawn.edges == ()
    assert drawn.supply is None


def test_the_highest_external_rail_is_the_input():
    """Two rails with no source is a product describing an intermediate it does not make.
    The input is the one carrying the most volts, and that is the only guess made here."""
    profile = {
        "rails": {
            "vin": {"source": None, "members": ["u1"], "voltage": 12.0},
            "5v": {"source": None, "members": ["u2"], "voltage": 5.0},
        }
    }

    assert graph_from(profile, GATEWAY_BOM).supply["voltage"] == 12.0
