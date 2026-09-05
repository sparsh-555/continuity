"""Does the engine produce a per-board differential for one substitute?

Three product lines share a linear regulator that is going end-of-life. The
manufacturer's recommended replacement is a smaller package. The question the whole
demo rests on: does `evaluate()` pass it on some boards and fail it on others, for a
reason it derives rather than one we staged?
"""
from continuity.engine.models import Board, PartSpec, Rail, Requirements, Slot
from continuity.engine.rules import evaluate

EOL = PartSpec(
    mpn="LD1117S33-EOL", manufacturer="Acme", category="Voltage Regulators - Linear, Low Drop Out (LDO) Regulators",
    description="3.3V LDO, DPAK", topology="ldo", package="TO-252",
    vmin=4.5, vmax=15.0, vout_min=3.3, vout_max=3.3,
    i_max=1.0, temp_min=-40, temp_max=125, theta_ja=35.0,
    theta_ja_source_line="Thermal resistance junction-ambient 35 C/W", lifecycle="eol",
    role="regulator", stock=0, unit_price=0.42,
)

# The replacement named on the PCN. Same function, same pinout family, smaller package.
REPLACEMENT = PartSpec(
    mpn="LD1117-SO8-NEW", manufacturer="Acme", category="Voltage Regulators - Linear, Low Drop Out (LDO) Regulators",
    description="3.3V LDO, SOIC-8", topology="ldo", package="SOIC-8",
    vmin=4.5, vmax=15.0, vout_min=3.3, vout_max=3.3,
    i_max=1.0, temp_min=-40, temp_max=125, theta_ja=110.0,
    theta_ja_source_line="Thermal resistance junction-ambient 110 C/W", lifecycle="active",
    role="regulator", stock=8400, unit_price=0.51,
)

def load(mpn: str, draw: float) -> PartSpec:
    return PartSpec(mpn=mpn, manufacturer="Acme", category="Microcontrollers",
                    description="load", role="mcu", i_typ=draw * 0.6, i_peak=draw,
                    vmin=3.0, vmax=3.6, temp_min=-40, temp_max=85)

def board(vin: float, draw: float, regulator: PartSpec) -> Board:
    return Board(
        requirements=Requirements(ambient_c=25, temp_range=(-40, 85)),
        slots={
            "u1": Slot(id="u1", label="3V3 regulator", tier="core", status="pass", part=regulator),
            "u2": Slot(id="u2", label="MCU", tier="core", status="pass", part=load("MCU-1", draw)),
        },
        rails={
            "vin": Rail(id="vin", voltage=vin, source=None, members=("u1",), i_limit=3.0, basis="stated in brief"),
            "3v3": Rail(id="3v3", voltage=3.3, source="u1", members=("u2",)),
        },
    )

LINES = [("Line A  5V rail, 0.30 A", 5.0, 0.30),
         ("Line B  5V rail, 0.50 A", 5.0, 0.50),
         ("Line C  12V rail, 0.20 A", 12.0, 0.20)]

for name, part in (("EOL PART (today)", EOL), ("RECOMMENDED REPLACEMENT", REPLACEMENT)):
    print(f"\n{'='*78}\n{name}: {part.mpn}  (theta_ja {part.theta_ja} C/W, {part.package})\n{'='*78}")
    for label, vin, draw in LINES:
        verdicts = evaluate(board(vin, draw, part))
        bad = [v for v in verdicts if v.status in ("fail", "warn")]
        p = (vin - 3.3) * draw
        print(f"\n  {label}   P = {p:.2f} W   junction ~= {25 + p * (part.theta_ja or 0):.0f} C")
        print(f"    {len(verdicts)} verdicts, {sum(1 for v in verdicts if v.status=='pass')} pass, "
              f"{sum(1 for v in verdicts if v.status=='fail')} FAIL, {sum(1 for v in verdicts if v.status=='warn')} warn")
        for v in bad:
            print(f"    [{v.status.upper():4}] {v.rule}: {v.detail}")

# Does a second candidate resolve all three? A buck converts rather than dissipating.
BUCK = PartSpec(
    mpn="TPS5430-BUCK", manufacturer="Acme", category="DC-DC Converters",
    description="3.3V buck", topology="buck", package="SOIC-8", efficiency=0.90,
    vmin=5.5, vmax=36.0, vout_min=1.22, vout_max=31.0,
    i_max=3.0, temp_min=-40, temp_max=125, theta_ja=110.0,
    theta_ja_source_line="Thermal resistance junction-ambient 110 C/W", lifecycle="active",
    role="regulator", stock=12000, unit_price=1.94,
)
print(f"\n{'='*78}\nSECOND CANDIDATE: {BUCK.mpn}  (switching)\n{'='*78}")
for label, vin, draw in LINES:
    verdicts = evaluate(board(vin, draw, BUCK))
    bad = [v for v in verdicts if v.status in ("fail", "warn")]
    print(f"\n  {label}")
    print(f"    {sum(1 for v in verdicts if v.status=='pass')} pass, "
          f"{sum(1 for v in verdicts if v.status=='fail')} FAIL, {sum(1 for v in verdicts if v.status=='warn')} warn")
    for v in bad:
        print(f"    [{v.status.upper():4}] {v.rule}: {v.detail}")
