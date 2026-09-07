"""Board-independent part facts are filtered before they can become durable memory."""

from __future__ import annotations

from continuity.engine.models import PartSpec
from continuity.parts.dossier import DOSSIER_FIELDS, facts_from_part


def test_facts_from_part_keeps_only_known_nonempty_part_properties():
    part = PartSpec(
        mpn="TPS54331DR",
        manufacturer="TI",
        description="buck regulator",
        category="DC-DC",
        package="SOIC-8",
        theta_ja=62.0,
        theta_ja_source_line="RθJA Junction-to-ambient thermal resistance 62.0",
        topology="buck",
        synchronous=False,
        efficiency=0.91,
        temp_min=None,
        temp_max=125.0,
        provenance={"topology": "Topology", "efficiency": "Efficiency"},
    )

    # `t_j_max` is on this list for the same reason `theta_ja` is, and its absence had
    # teeth: the thermal rule falls back to `temp_max` when no junction limit is known,
    # and an ambient grade is not a junction limit — a part graded to 125 °C ambient and
    # rated to 150 °C at the junction would have been checked 25 °C too harshly, with a
    # verdict that read as entirely reasonable.
    assert DOSSIER_FIELDS == frozenset(
        {
            "package", "theta_ja", "topology", "synchronous", "efficiency",
            "temp_min", "temp_max", "t_j_max",
            "vmin", "vmax", "vout_min", "vout_max", "i_max",
        }
    )
    assert facts_from_part(part) == [
        ("TPS54331DR", "efficiency", "0.91", "Efficiency"),
        ("TPS54331DR", "package", "SOIC-8", None),
        ("TPS54331DR", "synchronous", "False", None),
        ("TPS54331DR", "temp_max", "125.0", None),
        ("TPS54331DR", "theta_ja", "62.0", "RθJA Junction-to-ambient thermal resistance 62.0"),
        ("TPS54331DR", "topology", "buck", "Topology"),
    ]


def test_facts_from_part_never_emits_empty_values():
    part = PartSpec(
        mpn="EMPTY",
        manufacturer="",
        description="",
        category="",
        package="",
        topology="",
    )

    assert facts_from_part(part) == []


def test_a_listings_not_stated_placeholder_never_becomes_a_durable_fact():
    """JLCPCB publishes a bare "-" for an unknown package.

    Found live: `HS91L02W2C01` was stored as `package = "-"`. Nothing upstream treats a
    dash as absent, and the dossier is the one place a transient blank becomes permanent
    and can later gap-fill a genuinely empty field on another board.
    """
    from continuity.engine.models import PartSpec
    from continuity.parts.dossier import facts_from_part

    part = PartSpec(
        mpn="HS91L02W2C01",
        manufacturer="m",
        description="d",
        category="Optoelectronics",
        package="-",
    )
    assert [field for _, field, _, _ in facts_from_part(part)] == []

    stated = PartSpec(
        mpn="HS91L02W2C01",
        manufacturer="m",
        description="d",
        category="Optoelectronics",
        package="SOP-8",
    )
    assert ("HS91L02W2C01", "package", "SOP-8", None) in facts_from_part(stated)


def test_a_verified_reading_is_marked_and_an_ordinary_one_is_not():
    """`verified` is a claim about where a number came from, so only a caller who knows makes it."""
    from continuity.parts.dossier import VERIFIED_PREFIX, facts_from_part

    part = PartSpec(
        mpn="TLV1117LV33DCYR",
        manufacturer="Texas Instruments",
        description="3.3 V LDO",
        category="LDO",
        vmax=5.5,
        provenance={"vmax": "Recommended Operating Conditions: VIN 2 V to 5.5 V"},
    )

    plain = dict((field, source) for _, field, _, source in facts_from_part(part))
    marked = dict((field, source) for _, field, _, source in facts_from_part(part, verified=True))

    assert plain["vmax"] == "Recommended Operating Conditions: VIN 2 V to 5.5 V"
    assert marked["vmax"].startswith(VERIFIED_PREFIX)
    assert "2 V to 5.5 V" in marked["vmax"], "the quoted line travels with the marker"


def test_only_engineering_fields_are_marked_verifiable():
    """Stock, price and lifecycle are the listing's to state; a datasheet cannot know them."""
    from continuity.parts.dossier import DOSSIER_FIELDS, ENGINEERING_FIELDS

    assert "vmax" in ENGINEERING_FIELDS and "theta_ja" in ENGINEERING_FIELDS
    for commercial in ("stock", "unit_price", "lifecycle", "lead_time_days", "distributor"):
        assert commercial not in ENGINEERING_FIELDS
        assert commercial not in DOSSIER_FIELDS, "a listing fact must not become durable"
