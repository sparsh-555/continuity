"""Does the engine produce a per-board differential for one substitute? Yes.

Three product lines share a 3.3 V linear regulator that is going end-of-life. The obvious
cheap replacement passes on two of them and cooks on the third, and the engine derives that
itself — we choose the boards, it computes the physics.

**Every part here is real.** MPNs, packages, voltage and current limits, temperature ratings,
stock and price were pulled from JLCPCB through `graph.sourcing`, the same path the product
uses, on 6 Sep 2026. θJA is not on the distributor rows, so the engine falls back to its own
package table — SOT-223 at 62 °C/W against SOT-23-5 at 250 °C/W, a four-fold difference that
is the whole story. Uploading a datasheet through `/datasheet` replaces that approximation
with a quoted figure, which is the stronger version of this demo.

    python -m tools.eol_differential      (from backend/, with PYTHONPATH=.)

## What it shows

    | candidate                  | A 120 mA | B 200 mA | C 350 mA          |
    | AMS1117-3.3   SOT-223      | pass     | pass     | pass              |  today
    | ME6211C33M5G  SOT-23-5     | pass     | hot      | FAIL 174 vs 150   |  the cheap swap
    | TLV1117LV33   SOT-223      | pass     | pass     | pass              |  same package

Three things worth noticing, none of them staged:

1. **The result is three-state.** Line B clears its limit at 110 °C and the engine still
   warns that it runs hot. Pass / marginal / fail is a better matrix than pass / fail.
2. **The failure is a property of the board, not the part.** The same regulator is fine on
   A and lethal on C. That is the argument for validating a whole board rather than looking
   up a pin-compatible substitute.
3. **The answer is per-board.** ME6211 at $0.0597 is correct for two lines; the third needs
   TLV1117 at $0.1115, nearly twice the price. A single verdict cannot express that.

## Known blemish

`voltage_overlap` warns on every row: the distributor states a maximum but no minimum, and
these are all LDOs whose real minimum is dropout above 3.3 V. It is honest — the engine says
what it could not check — but it is noise on nine cells out of nine, and a datasheet upload
would clear it.
"""

from continuity.engine.models import Board, PartSpec, Rail, Requirements, Slot
from continuity.engine.rules import evaluate

LDO = "Voltage Regulators - Linear, Low Drop Out (LDO) Regulators"

# Going end-of-life. SOT-223, the default 3.3V rail part; 1.49M in stock at JLCPCB.
AMS1117 = PartSpec(
    mpn="AMS1117-3.3", manufacturer="Advanced Monolithic Systems", category=LDO,
    description="3.3V fixed LDO, SOT-223", topology="ldo", package="SOT-223",
    vmax=15.0, vout_min=3.3, vout_max=3.3, i_max=1.0,
    temp_min=-40.0, temp_max=125.0, stock=1495109, unit_price=0.2176,
    datasheet="https://www.ic-components.tw/files/4b/AMS1117-1.2.pdf",
)

# The cheap, obvious swap. SOT-23-5, half the price, lower dropout.
ME6211 = PartSpec(
    mpn="ME6211C33M5G-N", manufacturer="MICRONE", category=LDO,
    description="3.3V fixed LDO, SOT-23-5", topology="ldo", package="SOT-23-5",
    vmax=6.0, vout_min=3.3, vout_max=3.3, i_max=0.5,
    temp_min=-40.0, temp_max=150.0, stock=328862, unit_price=0.0597,
    datasheet="https://datasheet.lcsc.com/szlcsc/1811131510_MICRONE-Nanjing-Micro-One-Elec-ME6211C33M5G-N_C82942.pdf",
)

# Same package as the part leaving, so the same thermal behaviour. Costs more, thinner stock.
TLV1117 = PartSpec(
    mpn="TLV1117LV33DCYR", manufacturer="JSMSEMI", category=LDO,
    description="3.3V fixed LDO, SOT-223", topology="ldo", package="SOT-223",
    vmax=12.0, vout_min=3.3, vout_max=3.3, i_max=1.0,
    temp_min=-40.0, temp_max=125.0, stock=3447, unit_price=0.1115,
    datasheet="https://jlcpcb.com/partdetail/C48937499", lifecycle="active",
)

def load(draw: float) -> PartSpec:
    return PartSpec(mpn="LOAD", manufacturer="-", category="Microcontrollers",
                    description="downstream load", role="mcu", i_typ=draw * 0.6, i_peak=draw,
                    vmin=3.0, vmax=3.6, temp_min=-40, temp_max=85, stock=50000)

def board(draw: float, regulator: PartSpec) -> Board:
    return Board(
        requirements=Requirements(ambient_c=25, temp_range=(0, 70)),
        slots={"u1": Slot(id="u1", label="3V3 regulator", tier="power", status="pass", part=regulator),
               "u2": Slot(id="u2", label="load", tier="core", status="pass", part=load(draw))},
        rails={"vin": Rail(id="vin", voltage=5.0, source=None, members=("u1",), i_limit=3.0,
                           basis="USB Type-C default Rp advertisement"),
               "3v3": Rail(id="3v3", voltage=3.3, source="u1", members=("u2",))},
    )

LINES = [("Line A · sensor node   120 mA", 0.120),
         ("Line B · gateway       200 mA", 0.200),
         ("Line C · display unit  350 mA", 0.350)]

for name, part in (("TODAY — the part going EOL", AMS1117),
                   ("CANDIDATE 1 — the cheap swap", ME6211),
                   ("CANDIDATE 2 — same package", TLV1117)):
    print(f"\n{'='*84}\n{name}: {part.mpn}  ({part.package}, ${part.unit_price})\n{'='*84}")
    for label, draw in LINES:
        v = evaluate(board(draw, part))
        bad = [x for x in v if x.status in ("fail", "warn")]
        p = (5.0 - 3.3) * draw
        print(f"\n  {label}   P={p:.3f} W")
        print(f"    {sum(1 for x in v if x.status=='pass')} pass, "
              f"{sum(1 for x in v if x.status=='fail')} FAIL, {sum(1 for x in v if x.status=='warn')} warn")
        for x in bad:
            print(f"    [{x.status.upper():4}] {x.rule}: {x.detail}")
