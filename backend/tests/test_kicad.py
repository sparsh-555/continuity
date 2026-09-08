"""Reading a KiCad project, and asking it what a substitute would do to the board.

Two layers, deliberately. Everything that decides something — which column is the part
number, which net lands on which pad, what a design rule report *means* — is tested without
KiCad, because those are our decisions and a container should not be needed to check them.
The layer that shells out is tested against KiCad itself on a real third-party board, and
skipped when none is configured.

The board is ProPico, MIT, drawn by somebody else in KiCad 7. See `fixtures/kicad/README.md`.
"""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from continuity.kicad import board, bom, drc, pins, project, render, runner

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "kicad" / "propico"

HAS_KICAD = bool(os.environ.get("CONTINUITY_KICAD")) and runner.available()
needs_kicad = pytest.mark.skipif(
    not HAS_KICAD, reason="set CONTINUITY_KICAD=docker to run against real KiCad"
)


# ── the bundle ────────────────────────────────────────────────────────────────


def a_project(tmp_path: Path, *, drop: str | None = None) -> Path:
    root = tmp_path / "bundle"
    (root / "hardware").mkdir(parents=True)
    for name in ("ProPico.kicad_pro", "ProPico.kicad_sch", "ProPico.kicad_pcb"):
        if name == drop:
            continue
        (root / "hardware" / name).write_text("(placeholder)")
    return root


def test_a_project_is_found_wherever_in_the_bundle_it_sits(tmp_path):
    found = project.find(a_project(tmp_path))

    assert found.name == "ProPico"
    assert found.schematic_name == "hardware/ProPico.kicad_sch"
    assert found.board_name == "hardware/ProPico.kicad_pcb"


def test_a_bundle_without_a_schematic_says_which_half_is_missing(tmp_path):
    with pytest.raises(project.NotAProject) as refused:
        project.find(a_project(tmp_path, drop="ProPico.kicad_sch"))

    assert "schematic" in str(refused.value)


def test_a_bundle_with_a_board_and_no_project_file_says_so(tmp_path):
    root = tmp_path / "loose"
    root.mkdir()
    (root / "board.kicad_pcb").write_text("(placeholder)")

    with pytest.raises(project.NotAProject) as refused:
        project.find(root)

    assert "no .kicad_pro" in str(refused.value)


def test_an_archive_that_would_write_outside_its_directory_is_refused(tmp_path):
    """The upload is a file somebody else wrote. `..` in a member escapes the unpack."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escaped.kicad_pro", "(project)")

    with pytest.raises(project.NotAProject) as refused:
        project.unpack(buffer.getvalue(), tmp_path / "out")

    assert "unsafe path" in str(refused.value)
    assert not (tmp_path / "escaped.kicad_pro").exists()


def test_an_archive_of_too_many_members_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(project.MAX_MEMBERS + 1):
            archive.writestr(f"f{index}.txt", "x")

    with pytest.raises(project.NotAProject):
        project.unpack(buffer.getvalue(), tmp_path / "out")


def test_a_file_that_is_not_a_zip_is_refused(tmp_path):
    with pytest.raises(project.NotAProject):
        project.unpack(b"not a zip", tmp_path / "out")


def test_a_real_bundle_unpacks_and_is_found(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in FIXTURE.glob("ProPico.*"):
            archive.write(path, f"ProPico/{path.name}")

    found = project.find(project.unpack(buffer.getvalue(), tmp_path / "out"))

    assert found.name == "ProPico"


# ── which column is the part number ───────────────────────────────────────────


def a_bill(**columns) -> str:
    """One CSV row per reference, in the shape kicad-cli writes."""
    header = ["Reference", "Value", "Footprint", *bom.PART_NUMBER_FIELDS, *bom.DISTRIBUTOR_FIELDS]
    lines = [",".join(f'"{name}"' for name in header)]
    for refdes, values in columns.items():
        row = [values.get(name, "") for name in header]
        row[0] = refdes
        lines.append(",".join(f'"{value}"' for value in row))
    return "\n".join(lines)


def test_a_real_part_number_field_is_preferred_over_the_value():
    bill = bom.parse(
        a_bill(
            U1={"Value": "AMS1117-3.3", "MPN": "AMS1117-3.3", "LCSC": "C6186"},
            C1={"Value": "100n", "MPN": "CL10B104KB8NNNC"},
        )
    )

    assert bill.mpn_field == "MPN"
    assert bill.by_refdes["C1"].mpn == "CL10B104KB8NNNC"
    assert bill.by_refdes["C1"].value == "100n"


def test_without_one_the_value_is_used_and_said_so():
    """A capacitor's value is not a part number, and the reader has to know which it got."""
    bill = bom.parse(a_bill(U1={"Value": "AMS1117-3.3"}, C1={"Value": "100n"}))

    assert bill.mpn_field == bom.VALUE_FIELD
    assert bill.by_refdes["C1"].mpn == "100n"


def test_a_distributor_code_is_kept_apart_from_the_part_number():
    bill = bom.parse(a_bill(U1={"Value": "AMS1117-3.3", "LCSC": "C347222"}))

    row = bill.by_refdes["U1"]
    assert row.distributor_code == "C347222"
    assert row.mpn == "AMS1117-3.3"


def test_the_rows_carrying_a_part_are_found_by_part_number():
    bill = bom.parse(
        a_bill(
            U1={"Value": "x", "MPN": "AMS1117-3.3"},
            U2={"Value": "y", "MPN": "ams1117-3.3"},
            U3={"Value": "z", "MPN": "NCP1117ST33T3G"},
        )
    )

    assert {row.refdes for row in bill.carrying("AMS1117-3.3")} == {"U1", "U2"}


# ── what a pin is for ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "function,role",
    [
        ("VI", pins.INPUT), ("VIN", pins.INPUT), ("IN", pins.INPUT),
        ("VO", pins.OUTPUT), ("VOUT", pins.OUTPUT),
        ("GND", pins.GROUND), ("VSS", pins.GROUND),
        ("EN", pins.ENABLE), ("NC", pins.NOT_CONNECTED),
    ],
)
def test_the_names_a_datasheet_uses_reach_the_same_role(function, role):
    assert pins.role_of(function) == role


def test_a_function_we_do_not_know_is_not_guessed():
    """A regulator wired input to output is a destroyed board. Unknown stays unknown."""
    assert pins.role_of("BOOST") is None
    assert pins.role_of("") is None
    assert pins.role_of(None) is None


# ── which net lands on which pad ──────────────────────────────────────────────


def a_placement(*pads) -> board.Placement:
    return board.Placement(
        refdes="U3",
        value="AMS1117-3.3",
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        x_mm=104.2416,
        y_mm=52.4878,
        pads=tuple(board.Pad(number=n, net=net, function=fn) for n, net, fn in pads),
    )


SOT223 = (("1", "GND", "GND"), ("2", "+3V3", "VO"), ("2", "+3V3", "VO"), ("3", "+5V", "VI"))
SOT23_5 = {"1": "VIN", "2": "GND", "3": "EN", "4": "NC", "5": "VOUT"}


def test_each_net_is_carried_to_the_pad_with_the_same_function():
    wiring = board._mapping(a_placement(*SOT223), SOT23_5)

    assert wiring.wired == {"1": "+5V", "2": "GND", "5": "+3V3"}
    assert wiring.unwired_pads == ("3", "4")
    assert wiring.complete


def test_a_pad_is_left_bare_rather_than_wired_to_something_near_it():
    """Enable and no-connect have no net on the old part. Neither gets one invented."""
    wiring = board._mapping(a_placement(*SOT223), SOT23_5)

    assert "3" not in wiring.wired and "4" not in wiring.wired


def test_a_net_with_nowhere_to_go_is_reported():
    """The loudest thing that can happen: the substitute has no pin for a net in use."""
    with_adjust = (*SOT223, ("4", "ADJ_NET", "ADJ"))

    wiring = board._mapping(a_placement(*with_adjust), SOT23_5)

    assert wiring.roles_with_nowhere_to_go == (pins.ADJUST,)
    assert not wiring.complete


def test_a_crop_is_centred_on_the_part_that_changed():
    crop = render.around(104.2416, 52.4878, margin=5.0)

    assert crop.view_box == "99.2416 47.4878 10.0000 10.0000"


# ── what the design rule check said ───────────────────────────────────────────


def a_report(**categories) -> dict:
    payload = {name: [] for name in drc.CATEGORIES}
    payload.update(categories)
    return payload


def a_finding(rule: str, *items: str) -> dict:
    return {
        "type": rule,
        "description": "Missing connection between items",
        "severity": "error",
        "items": [{"description": item} for item in items],
    }


def test_every_category_is_read():
    report = drc.parse(
        a_report(
            violations=[a_finding("clearance", "Track", "Pad")],
            unconnected_items=[a_finding("unconnected_items", "Pad 2 [GND] of U3", "Via")],
            schematic_parity=[a_finding("footprint", "U3")],
        )
    )

    assert len(report.violations) == 1
    assert len(report.unconnected) == 1
    assert len(report.parity) == 1


def test_a_report_missing_a_category_is_an_error_rather_than_an_empty_board():
    """An absent key renders exactly like nothing wrong, which is the one answer that
    must never be produced by accident."""
    payload = a_report()
    del payload["unconnected_items"]

    with pytest.raises(drc.UnreadableReport) as refused:
        drc.parse(payload)

    assert "unconnected_items" in str(refused.value)


def test_the_delta_reports_what_the_substitution_added():
    before = drc.parse(a_report(unconnected_items=[a_finding("unconnected_items", "Pad 1 of J1")]))
    after = drc.parse(
        a_report(
            unconnected_items=[
                a_finding("unconnected_items", "Pad 1 of J1"),
                a_finding("unconnected_items", "Pad 2 [GND] of U3", "Via [GND]"),
            ],
            violations=[a_finding("shorting_items", "Pad 5 of U3", "Zone [+3V3]")],
        )
    )

    delta = drc.compare(before, after)

    assert delta.broke_connections
    assert [f.items for f in delta.added_unconnected] == [("Pad 2 [GND] of U3", "Via [GND]")]
    assert delta.by_rule()["unconnected_items"] == (1, 2)
    assert delta.by_rule()["shorting_items"] == (0, 1)
    assert delta.removed == ()


def test_a_second_identical_finding_counts_as_an_addition():
    """Two complaints KiCad words the same way are two complaints, and set arithmetic
    would report the second one as nothing at all."""
    one = a_finding("clearance", "Track [GND]", "Pad 1 of U3")
    before = drc.parse(a_report(violations=[one]))
    after = drc.parse(a_report(violations=[one, dict(one)]))

    delta = drc.compare(before, after)

    assert len(delta.added) == 1
    assert delta.by_rule()["clearance"] == (1, 2)


# ── against KiCad itself ──────────────────────────────────────────────────────


@pytest.fixture
def bundle(tmp_path):
    """A working copy, because every command writes its output beside the project."""
    root = tmp_path / "bundle"
    shutil.copytree(FIXTURE, root / "ProPico")
    return project.find(root)


@needs_kicad
def test_the_pinned_version_is_what_runs(bundle):
    assert runner.require().check(workdir=bundle.root).startswith(runner.PINNED)


@needs_kicad
def test_the_bill_of_materials_comes_out_of_the_schematic(bundle):
    bill = bom.read(bundle, runner.require())

    assert len(bill.rows) > 40
    carrying = bill.carrying("AMS1117-3.3")
    assert [row.refdes for row in carrying] == ["U3"]
    assert carrying[0].distributor_code == "C347222"
    assert carrying[0].footprint == "Package_TO_SOT_SMD:SOT-223-3_TabPin2"


@needs_kicad
def test_a_smaller_package_breaks_connections_and_kicad_is_what_says_so(bundle):
    """The whole item in one call: the substitute lands where the retired part sat, and
    the check that ran before it ran again after."""
    outcome = board.consequence(
        bundle,
        runner.require(),
        refdes="U3",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        pinout=SOT23_5,
        value="ME6211C33M5G-N",
    )

    assert outcome.placement.footprint.endswith("SOT-223-3_TabPin2")
    assert outcome.wiring.wired == {"1": "+5V", "2": "GND", "5": "+3V3"}
    assert outcome.wiring.unwired_pads == ("3", "4")
    assert outcome.broke_connections, "a SOT-23-5 on SOT-223 pads cannot stay connected"
    assert len(outcome.delta.added_unconnected) >= 3
    assert any("U3" in item for f in outcome.delta.added_unconnected for item in f.items)
    before, after = outcome.delta.by_rule()["unconnected_items"]
    assert after > before

    assert outcome.before.svg.startswith("<?xml") and outcome.after.svg.startswith("<?xml")
    assert outcome.before.svg != outcome.after.svg
    assert (outcome.before.width_mm, outcome.before.height_mm) == (
        outcome.after.width_mm,
        outcome.after.height_mm,
    ), "the two pictures must be the same page or the crops point at different places"
    assert outcome.crop.view_box == "98.2416 46.4878 12.0000 12.0000"


@needs_kicad
def test_the_same_footprint_keeps_the_board_connected(bundle):
    """The other half of the argument, and the reason the demo has two answers: a true
    drop-in adds nothing, on the same board, through the same code path."""
    outcome = board.consequence(
        bundle,
        runner.require(),
        refdes="U3",
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        pinout={"1": "GND", "2": "VO", "3": "VI"},
        value="NCP1117ST33T3G",
    )

    assert not outcome.broke_connections, "a same-package substitute broke a connection"
    assert outcome.delta.added_unconnected == ()


@needs_kicad
def test_a_reference_the_board_does_not_place_is_refused(bundle):
    with pytest.raises(board.NoSuchPart) as refused:
        board.consequence(
            bundle,
            runner.require(),
            refdes="U99",
            footprint="Package_TO_SOT_SMD:SOT-23-5",
            pinout=SOT23_5,
        )

    assert "U99" in str(refused.value)


# ── KiCad names a different witness for the same defect ───────────────────────


def test_the_same_unconnected_net_is_the_same_finding_however_kicad_names_it():
    """Measured on OpenJBOD, 9 Sep: three DRC runs on a byte-identical board.

    All three reported five unconnected groups and two of them named **different witness
    pads for the same defects** — `pad 4 / pad 6 of J1` in one run, `pad 2 / pad 12 of J1`
    in another. KiCad names one representative pair per unconnected group and which pair it
    picks varies between runs.

    Keyed on the pads, that made a same-package drop-in look as though it had broken a
    connection at the far end of the board, on a net it never touched, **intermittently**.
    A verdict that changes between runs of the same input is not a verdict.
    """
    before = drc.parse(a_report(unconnected_items=[
        a_finding("unconnected_items", "PTH pad 4 [/+5v] of J1", "PTH pad 6 [/+5v] of J1"),
        a_finding("unconnected_items", "Track [/+3.3v] on Back, length 37.1300 mm",
                  "PTH pad 12 [/+3.3v] of J1"),
    ]))
    after = drc.parse(a_report(unconnected_items=[
        a_finding("unconnected_items", "PTH pad 21 [/+5v] of J1", "PTH pad 22 [/+5v] of J1"),
        a_finding("unconnected_items", "PTH pad 2 [/+3.3v] of J1", "PTH pad 12 [/+3.3v] of J1"),
    ]))

    assert drc.compare(before, after).added == (), "the same two defects, named differently"


def test_a_genuinely_new_unconnected_net_is_still_reported():
    """Ignoring the witness must not mean ignoring the defect."""
    before = drc.parse(a_report(unconnected_items=[
        a_finding("unconnected_items", "PTH pad 4 [/+5v] of J1", "PTH pad 6 [/+5v] of J1"),
    ]))
    after = drc.parse(a_report(unconnected_items=[
        a_finding("unconnected_items", "PTH pad 21 [/+5v] of J1", "PTH pad 22 [/+5v] of J1"),
        a_finding("unconnected_items", "Pad 2 [/SDA] of U7", "Pad 5 [/SDA] of U9"),
    ]))

    added = drc.compare(before, after).added
    assert len(added) == 1 and "/SDA" in " ".join(added[0].items)


def test_a_second_break_on_a_net_that_already_had_one_is_reported():
    """Counted, not set-subtracted. Two groups where there was one is a change."""
    before = drc.parse(a_report(unconnected_items=[
        a_finding("unconnected_items", "PTH pad 4 [/+5v] of J1", "PTH pad 6 [/+5v] of J1"),
    ]))
    after = drc.parse(a_report(unconnected_items=[
        a_finding("unconnected_items", "PTH pad 4 [/+5v] of J1", "PTH pad 6 [/+5v] of J1"),
        a_finding("unconnected_items", "PTH pad 21 [/+5v] of J1", "PTH pad 22 [/+5v] of J1"),
    ]))

    assert len(drc.compare(before, after).added) == 1


def test_a_clearance_finding_still_keys_on_the_items_it_names():
    """Only `unconnected_items` has a varying witness. Nothing else measured does, and
    widening the exemption without evidence would hide real changes."""
    before = drc.parse(a_report())
    after = drc.parse(a_report(violations=[
        a_finding("clearance", "Pad 5 [/+3V3] of U3", "Zone [/+3V3]"),
    ]))

    assert len(drc.compare(before, after).added) == 1
