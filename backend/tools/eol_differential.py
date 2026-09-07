"""Compare sourced 3.3 V LDO substitutes across three existing product lines.

Each board uses its signed 3V3 power-budget load rather than a synthetic component sum.
Listing values were captured through the JLCPCB sourcing path on 7 Sep 2026; thermal
values retain their manufacturer's quoted installation beside the number.

Run from ``backend`` with ``PYTHONPATH=. python -m tools.eol_differential``.
"""

from __future__ import annotations

from dataclasses import dataclass

from continuity.engine.models import Board, PartSpec, Rail, Requirements, Slot
from continuity.engine.rules import evaluate


LDO = "Voltage Regulators - Linear, Low Drop Out (LDO) Regulators"
EIA_RS_198 = "EIA RS-198 X5R dielectric rating (−55 °C to +85 °C)"
"""The capacitor listing states X5R, not an operating-temperature range."""


# JLCPCB C6186; AMS Table 1's 1000 mm² copper row, not its 46–>90 °C/W headline range.
AMS1117 = PartSpec(
    mpn="AMS1117-3.3", manufacturer="Advanced Monolithic Systems",
    description="3.3 V fixed low-dropout regulator", category=LDO, package="SOT-223",
    vmax=15.0, vout_min=3.3, vout_max=3.3, i_max=1.0, temp_min=-40.0, temp_max=125.0,
    t_j_max=125.0,  # AMS datasheet: maximum junction temperature must not exceed 125 °C.
    theta_ja=60.0,
    theta_ja_source_line="1000 Sq. mm / 1000 Sq. mm / 1000 Sq. mm — 60 °C/W",
    theta_ja_mounting=(
        "Table 1, 1000 mm² top and back copper on a 1000 mm² board, 1/16in FR-4, 1 oz foil"
    ),
    topology="ldo", stock=1_493_359, unit_price=0.2176, distributor="JLCPCB",
    datasheet="http://www.advanced-monolithic.com/pdf/ds1117.pdf",
    product_url="https://jlcpcb.com/partdetail/C6186",
)

# JLCPCB C15578 is TI's listing. C48937499 is JSMSEMI's conflicting listing, and is not used.
TLV1117 = PartSpec(
    mpn="TLV1117LV33DCYR", manufacturer="Texas Instruments",
    description="3.3 V fixed low-dropout regulator", category=LDO, package="SOT-223",
    vmax=5.5, vout_min=3.3, vout_max=3.3, i_max=1.0, temp_min=-40.0, temp_max=125.0,
    t_j_max=125.0,  # TI recommends limiting reliable operation to a 125 °C junction.
    theta_ja=62.9,
    theta_ja_source_line="RθJA Junction-to-ambient thermal resistance 62.9 °C/W",
    theta_ja_mounting="TI thermal information, DCY (SOT-223) 4 pins",
    topology="ldo", stock=3_416, unit_price=0.3345, distributor="JLCPCB",
    datasheet="https://www.ti.com/lit/ds/symlink/tlv1117lv.pdf",
    product_url="https://jlcpcb.com/partdetail/C15578",
)

# JLCPCB C86781. Read the revision on the datasheet before touching this number: Rev 26's
# thermal table publishes RthJA for TO-220 only, and Rev 38 adds SOT-223, SO-8 and DPAK.
# ST's own revision history dates the addition to 19 Oct 2012.
LD1117 = PartSpec(
    mpn="LD1117S33TR", manufacturer="STMicroelectronics",
    description="3.3 V fixed low-dropout regulator", category=LDO, package="SOT-223",
    vmax=15.0, vout_min=3.3, vout_max=3.3, i_max=0.8, temp_min=0.0, temp_max=125.0,
    t_j_max=125.0,  # ST specifies the electrical characteristics over TJ = 0 to 125 °C.
    theta_ja=110.0,
    theta_ja_source_line="RthJA Thermal resistance junction-ambient — SOT-223 110 °C/W",
    theta_ja_mounting="ST LD1117 Table 2, thermal data, SOT-223 column",
    topology="ldo", stock=41_254, unit_price=0.2429, distributor="JLCPCB",
    datasheet="https://www.st.com/resource/en/datasheet/ld1117.pdf",
    product_url="https://jlcpcb.com/partdetail/C86781",
)

# JLCPCB C26537; onsemi specifies this SOT-223 figure on a minimum-size pad.
NCP1117 = PartSpec(
    mpn="NCP1117ST33T3G", manufacturer="onsemi",
    description="3.3 V fixed low-dropout regulator", category=LDO, package="SOT-223",
    vmax=20.0, vout_min=3.3, vout_max=3.3, i_max=1.0, temp_min=0.0,
    temp_max=125.0,  # The listing's explicitly ambient 0–125 °C range.
    t_j_max=150.0,  # onsemi datasheet: maximum die junction temperature TJ −55 to 150 °C.
    theta_ja=160.0,
    theta_ja_source_line="Thermal Resistance, Junction-to-Ambient, Minimum Size Pad — 160 °C/W",
    theta_ja_mounting="minimum size pad, Case 318H (SOT-223)",
    topology="ldo", stock=78_632, unit_price=0.2354, distributor="JLCPCB",
    datasheet="https://www.onsemi.com/pdf/datasheet/ncp1117-d.pdf",
    product_url="https://jlcpcb.com/partdetail/C26537",
)

# JLCPCB C12891 states X5R; EIA RS-198 supplies the -55–85 °C dielectric range.
OUTPUT_CAPACITOR = PartSpec(
    mpn="CL31A226KAHNNNE", manufacturer="Samsung Electro-Mechanics",
    description="22 µF ±10% 25 V X5R ceramic capacitor",
    category="Multilayer Ceramic Capacitors MLCC - SMD/SMT", package="1206", vmax=25.0,
    temp_min=-55.0, temp_max=85.0, stock=1_473_130, unit_price=0.1725,
    distributor="JLCPCB", product_url="https://jlcpcb.com/partdetail/C12891",
    provenance={"temp_min": EIA_RS_198, "temp_max": EIA_RS_198},
)


@dataclass(frozen=True)
class ProductLine:
    """One product line's declared supply, load and ambient conditions."""

    id: str
    label: str
    input_voltage: float
    input_limit: float
    input_basis: str
    load: float
    load_basis: str
    ambient_c: int
    ambient_basis: str
    load_part: PartSpec


LINE_A = ProductLine(
    "A", "Sensor node", 5.0, 3.0, "USB Type-C default Rp advertisement", 0.150,
    "sensor node power budget Rev C — 150 mA continuous at 3V3", 25,
    "sensor node operating profile Rev C — 25 °C open-air ambient",
    PartSpec(
        mpn="ESP32-C3-MINI-1-N4", manufacturer="Espressif", description="Wi-Fi and BLE module",
        category="RF Modules", vmin=3.0, vmax=3.6, i_peak=0.350, i_typ=0.084,
        temp_min=-40.0, temp_max=85.0, stock=18_086, unit_price=3.8336,
        distributor="JLCPCB", product_url="https://jlcpcb.com/partdetail/C2838502",
    ),
)
LINE_B = ProductLine(
    "B", "Gateway", 5.0, 3.0, "USB Type-C default Rp advertisement", 0.420,
    "gateway power budget Rev C — 420 mA continuous at 3V3", 45,
    "gateway operating profile Rev C — 45 °C sealed-enclosure ambient",
    PartSpec(
        mpn="ESP32-WROOM-32E-N4", manufacturer="Espressif", description="Wi-Fi and BLE module",
        category="RF Modules", vmin=3.0, vmax=3.6, i_peak=0.239, i_typ=0.112,
        temp_min=-40.0, temp_max=85.0, stock=28_108, unit_price=3.7312,
        distributor="JLCPCB", product_url="https://jlcpcb.com/partdetail/C701341",
    ),
)
LINE_C = ProductLine(
    "C", "Cabinet controller", 12.0, 1.0,
    "12 V DIN-rail supply, product line power budget Rev C", 0.060,
    "cabinet controller power budget Rev C — 60 mA continuous at 3V3", 55,
    "cabinet controller operating profile Rev C — 55 °C cabinet ambient",
    PartSpec(
        # JLCPCB C8734 states no current, so i_peak and i_typ deliberately remain unset.
        mpn="STM32F103C8T6", manufacturer="STMicroelectronics", description="ARM Cortex-M3 MCU",
        category="Microcontrollers (MCU)", vmin=2.0, vmax=3.6, temp_min=-40.0, temp_max=85.0,
        stock=224_069, unit_price=1.7203, distributor="JLCPCB",
        product_url="https://jlcpcb.com/partdetail/C8734",
    ),
)
LINES = (LINE_A, LINE_B, LINE_C)


def make_board(line: ProductLine, regulator: PartSpec) -> Board:
    """Model the relevant BOM slots while retaining the whole-board declared rail load.

    The module and capacitor remain real slots so other rules inspect their ratings;
    they do not pretend these three parts make up the production BOM.
    """
    return Board(
        requirements=Requirements(
            ambient_c=line.ambient_c, ambient_source=line.ambient_basis,
            temp_range=(0, 70),
            mounting="1000 mm² top and back copper, 1/16in FR-4, 1 oz",
        ),
        slots={
            # The incumbent is the baseline every candidate is measured against, and a
            # candidate replacing itself is not a substitution — line A running AMS1117
            # is the board as it stands today, not a proposed change to it.
            "u1": Slot(
                "u1", "3V3 regulator", "power", status="pass", part=regulator,
                baseline=None if regulator is AMS1117 else AMS1117,
            ),
            "u2": Slot("u2", line.label + " module", "core", status="pass", part=line.load_part),
            "c1": Slot("c1", "3V3 output capacitor", "passives", status="pass", part=OUTPUT_CAPACITOR),
        },
        rails={
            "vin": Rail("vin", line.input_voltage, members=("u1",), i_limit=line.input_limit,
                        basis=line.input_basis),
            "3v3": Rail("3v3", 3.3, source="u1", members=("u2", "c1"), i_load=line.load,
                        i_load_basis=line.load_basis),
        },
    )


def _print_line(line: ProductLine, regulator: PartSpec) -> None:
    """Print non-pass verdicts so the matrix and its qualifications travel together."""
    verdicts = evaluate(make_board(line, regulator))
    bad = [item for item in verdicts if item.status in ("fail", "warn")]
    power = (line.input_voltage - 3.3) * line.load
    print("\n  {} · {}   P={:.3f} W".format(line.id, line.label, power))
    print(
        "    {} pass, {} FAIL, {} warn".format(
            sum(item.status == "pass" for item in verdicts),
            sum(item.status == "fail" for item in verdicts),
            sum(item.status == "warn" for item in verdicts),
        )
    )
    for item in bad:
        print("    [{:4}] {}: {}".format(item.status.upper(), item.rule, item.detail))


def main() -> None:
    """Render the sourced candidate-by-product-line matrix for hardware review."""
    for heading, regulator in (
        ("INCUMBENT — part undergoing end-of-life review", AMS1117),
        ("CANDIDATE — TI low-voltage replacement", TLV1117),
        ("CANDIDATE — ST replacement", LD1117),
        ("CANDIDATE — onsemi replacement", NCP1117),
    ):
        print("\n{}\n{}: {}  ({}, USD {})\n{}".format(
            "=" * 84, heading, regulator.mpn, regulator.package, regulator.unit_price, "=" * 84
        ))
        for line in LINES:
            _print_line(line, regulator)


if __name__ == "__main__":
    main()
