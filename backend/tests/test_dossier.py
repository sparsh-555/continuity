"""Board-independent part facts are filtered before they can become durable memory."""

from __future__ import annotations

import pytest

from continuity.engine.models import PartSpec
from continuity.parts import dossier
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
    # `cout_min_uf` and `cout_dielectrics` joined for the same reason, and their absence
    # had teeth too: they could not reach the engine on any live path, so
    # `capacitor_requirements` reported *evidence missing* on a product line whose datasheet
    # readings the company had recorded. That is the one passive check the product ships.
    # `vout_accuracy_pct` and `load_regulation_pct` are the third instance of the same
    # mistake, seven days later, and cost `signal_integrity` its answer on every real board.
    assert DOSSIER_FIELDS == frozenset(
        {
            "package", "theta_ja", "topology", "synchronous", "efficiency",
            "temp_min", "temp_max", "t_j_max",
            "vmin", "vmax", "vout_min", "vout_max", "i_max",
            "cout_min_uf", "cout_dielectrics",
            "capacitance_uf", "dielectric",
            "vout_accuracy_pct", "load_regulation_pct",
            "esr_stable_from_ohms", "esr_stable_to_ohms", "esr_ohms",
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


# ── the capacitor requirement, which could not travel ─────────────────────────


def test_a_regulators_output_capacitor_requirement_is_a_fact_about_the_part():
    """It is true of the MPN on every board, which is this module's own criterion.

    Left out, it could not reach the engine on any live path: `capacitor_requirements`
    reported *evidence missing* on a seeded product line whose datasheet readings the
    company had actually recorded. The rule is the one passive check the product ships, and
    SPEC names it "the first thing a hardware engineer attacks on an LDO substitution", so
    it firing only in an offline fixture was the gap between what we claim and what runs.
    """
    part = PartSpec(
        mpn="TLV1117LV33DCYR",
        manufacturer="Texas Instruments",
        description="3.3 V LDO",
        category="LDO Regulator",
        package="SOT-223",
        cout_min_uf=0.5,
        cout_dielectrics=("X5R", "X7R"),
        cout_source_line="Effective output capacitance … 0.5 µF",
    )

    written = {field: value for _, field, value, _ in dossier.facts_from_part(part)}

    assert written["cout_min_uf"] == "0.5"
    assert "X5R" in written["cout_dielectrics"] and "X7R" in written["cout_dielectrics"]


def test_a_capacitors_own_value_is_a_fact_about_the_part_too():
    """Both sides of the capacitor rule had to be able to travel, and neither could.

    A regulator states what it needs; a capacitor states what it is. With `capacitance_uf`
    absent from this list, the capacitor resolved live carried no value, so the rule
    reported evidence missing however many datasheet readings the regulator had. Adding one
    side without the other would have changed nothing.

    They are *not* engineering fields: a distributor states an MLCC's capacitance and
    dielectric accurately and our own seeded values came from the JLCPCB listing, so these
    fill a blank rather than outrank a listing.
    """
    part = PartSpec(
        mpn="CL31A226KAHNNNE",
        manufacturer="Samsung Electro-Mechanics",
        description="22 µF 25 V X5R",
        category="Multilayer Ceramic Capacitors MLCC - SMD/SMT",
        package="1206",
        capacitance_uf=22.0,
        dielectric="X5R",
    )

    written = {field: value for _, field, value, _ in dossier.facts_from_part(part)}

    assert written["capacitance_uf"] == "22.0" and written["dielectric"] == "X5R"


def test_the_dielectrics_a_datasheet_requires_come_back_as_a_tuple():
    """Empty means the datasheet named none, not that any will do, so the round trip has to
    keep the difference between "no requirement" and "a requirement of one"."""
    assert dossier.value_from_text("cout_dielectrics", "X5R, X7R") == ("X5R", "X7R")
    assert dossier.value_from_text("cout_dielectrics", "") is None


def test_a_capacitance_read_back_is_a_number_the_engine_can_add_up():
    """Found live, as a 500 on `/lines/{id}/check` for every seeded product line.

    `DOSSIER_FIELDS` says a fact may be stored; `_FLOAT_FIELDS` says what it decodes back
    into; `ENGINEERING_FIELDS` says whether it outranks a listing. Those are three
    questions, and `capacitance_uf` was kept out of the second on the grounds that answer
    the third — a distributor states an MLCC accurately, so a stored figure should not
    outrank one. True, and no argument at all about what type the string turns into.

    So a recorded capacitance came back as `"22.0"`, reached `PartSpec.capacitance_uf`, and
    `capacitor_requirements` summed a str into an int. The one passive rule the product
    ships took down the check the whole product line page is painted from.
    """
    assert dossier.value_from_text("capacitance_uf", "22.0") == 22.0
    assert dossier.value_from_text("capacitance_uf", "not a number") is None

    # The round trip in full, which is what the engine actually depends on.
    part = PartSpec(
        mpn="CL31A226KAHNNNE",
        manufacturer="Samsung Electro-Mechanics",
        description="22 µF 25 V X5R",
        category="Multilayer Ceramic Capacitors MLCC - SMD/SMT",
        capacitance_uf=22.0,
        dielectric="X5R",
    )
    written = {field: value for _, field, value, _ in dossier.facts_from_part(part)}
    read = {
        field: dossier.value_from_text(field, value) for field, value in written.items()
    }

    assert read["capacitance_uf"] == 22.0
    assert read["dielectric"] == "X5R"
    assert sum(read["capacitance_uf"] for _ in (1,)) == 22.0, "it has to be addable"


def test_a_reading_built_from_the_record_still_says_where_it_came_from():
    """The line a figure was read from is stored, and it used to stop at the door.

    `facts_from_part` writes each reading with its source, and `normalize` carries that
    source through as `Continuity dossier (…the line…)`. `part_from_facts` — the fallback a
    product line's own parts are built by — threw it away and stamped every field with the
    bare label, so a change request showed *vmax (dossier) 20.0* against nothing. PARTS.md
    promises a source line for every figure in it, and this is the path where that promise
    was not kept.
    """
    from tools.eol_differential import NCP1117

    facts = dossier.facts_from_part(NCP1117, verified=True)
    back = dossier.part_from_facts(NCP1117.mpn, NCP1117.manufacturer, [
        {"field": field, "value": value, "source": source} for _, field, value, source in facts
    ])

    assert back is not None
    for evidence in back.cite("u1", "vmax", "vout_accuracy_pct", "esr_stable_from_ohms"):
        assert evidence.source != dossier.DOSSIER_PROVENANCE_PREFIX, (
            f"{evidence.field} carries the bare label, so nothing says where it came from"
        )
        assert "(" in evidence.source and evidence.source.endswith(")"), evidence.source
        assert evidence.source != f"{dossier.DOSSIER_PROVENANCE_PREFIX} (not recorded)"


def test_a_regulators_published_error_is_a_fact_about_the_part():
    """The fields `signal_integrity` stacks, which were researched and then dropped.

    P2 built the rule on 11 September to replace a standing admission, and the rule was
    right — but the figures it needs never survived the company's own record, because
    neither field was on this list. So the rule declined on every real board and the change
    request a judge reads still said it could not check something. A figure read off a
    datasheet is exactly what this list is for.
    """
    from tools.eol_differential import TLV1117

    facts = {field: value for _, field, value, _ in dossier.facts_from_part(TLV1117, verified=True)}

    assert facts["vout_accuracy_pct"] == "1.5", "quoted from TI's electrical characteristics"
    assert float(facts["load_regulation_pct"]) > 0, "35 mV on a 3.3 V rail, derived and named"

    back = dossier.part_from_facts(TLV1117.mpn, TLV1117.manufacturer, [
        {"field": field, "value": value} for field, value in facts.items()
    ])

    assert back is not None
    assert back.vout_accuracy_pct == 1.5
    assert back.load_regulation_pct == pytest.approx(35 / 3300 * 100)


def test_an_esr_window_the_engine_reads_survives_the_record():
    """The third instance of the same mistake, found by looking for the class.

    `output_capacitor_stability` compares a capacitor's published ESR against the window its
    regulator publishes. Both readings are hand-read from datasheets and both were dropped
    by the company's own record, so the comparison could not run on any board anybody had
    described. Nothing catches it today because the demo's capacitor publishes no ESR — and
    a check that is silent because its data never arrives looks exactly like a check that
    passes.
    """
    from tools.eol_differential import NCP1117

    facts = {field: value for _, field, value, _ in dossier.facts_from_part(NCP1117, verified=True)}

    assert facts["esr_stable_from_ohms"] == "0.033"
    assert facts["esr_stable_to_ohms"] == "2.2"

    back = dossier.part_from_facts(NCP1117.mpn, NCP1117.manufacturer, [
        {"field": field, "value": value} for field, value in facts.items()
    ])

    assert back is not None
    assert back.esr_stable_from_ohms == pytest.approx(0.033)
    assert back.esr_stable_to_ohms == pytest.approx(2.2)
    assert back.provenance.get("esr_stable_from_ohms"), (
        "the reading is marked as recorded rather than sourced from a listing"
    )


def test_every_numeric_dossier_field_decodes_to_a_number():
    """A guard against the same slip in the next field somebody adds.

    Written against `PartSpec`'s own annotations rather than a hand-kept list, because a
    hand-kept list is the thing that was wrong.
    """
    import typing

    hints = typing.get_type_hints(PartSpec)
    numeric = {
        field
        for field in DOSSIER_FIELDS
        if "float" in str(hints.get(field, "")) or "int" in str(hints.get(field, ""))
    }

    for field in sorted(numeric):
        assert isinstance(dossier.value_from_text(field, "1.5"), float), (
            f"{field} is a number on PartSpec and decodes as text, so the engine gets a str"
        )
