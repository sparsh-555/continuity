# Task · BUILD item 1 — real fixture, real parts, and the four fields it needs

A self-contained brief. You should not need to read the rest of `docs/world-finals/` to do
this, though [PARTS.md](../PARTS.md) is the evidence behind every number below and
[SPEC.md](../SPEC.md) §"The demo case" is where the expected matrix comes from.

**Repository** `~/Documents/GitHub/continuity`, work in `backend/`.
**Suite today** 721 passed, 5 skipped. It must still pass when you are done.
**Do not commit or push.**

---

## What this is for

`backend/tools/eol_differential.py` is the script behind the world-finals demo. It asks one
question: *does the engine produce a different verdict for the same substitute on different
boards?* Three product lines share a 3.3 V linear regulator that is going end-of-life, and the
replacements behave differently on each.

The current version of that file has values that no source supports, mixes one manufacturer's
datasheet with another manufacturer's distributor listing, and models its loads with a part
whose MPN is the string `"LOAD"`. This task replaces all of it with sourced data, and adds the
four model fields without which the sourced data cannot be stated honestly.

**The governing rule for this task: never write a number you cannot attribute.** If a value is
not in the JLCPCB listing or the manufacturer's datasheet quoted below, it does not go in the
file. If something below turns out to be wrong when you check it, say so and stop — do not
substitute a value that makes the test pass.

---

## Part 1 · The model additions — **DONE, do not redo**

Implemented and merged. The suite went from **721 passed / 5 skipped** to **728 / 5** — seven
new engine tests, no existing test moved. Read this section for the field names and semantics
you will use in Part 2; do not re-implement any of it.

Two things came out differently from the original plan, and the differences matter to Part 2:

**There are five fields, not four.** `Rail.i_load_basis` had to be separate from `Rail.basis`.
Folding the load's provenance into `basis` would have made R1 cite a power budget as the source
of the rail's *voltage*, which is not what a power budget says. A rail can take its ceiling from
a published standard and its load from a company document, and one string cannot honestly carry
both.

**`rail_draw` has five call sites, not three.** `draw.reflected_draw`,
`rules._check_rail_current`, `rules._check_rail_thermal`, `rules.energy_budget` and
`engine/situation.py`, plus two in `tests/test_rules.py`. All are updated. The signature is now
`rail_draw(board, rail, consumers, seen=frozenset())` — the rail is required rather than
defaulted, so a caller that forgets it raises rather than silently answering from an
under-counted sum.

What exists now:

| Field | Meaning |
|---|---|
| `PartSpec.theta_ja_mounting` | The installation the θJA was measured on, in the datasheet's words |
| `PartSpec.t_j_max` | Junction limit, separate from the ambient grade. R5 falls back to `temp_max` when unset |
| `Requirements.mounting` | The board's copper area and construction |
| `Rail.i_load` | The design's stated rail load. Returns with an empty `unstated` list |
| `Rail.i_load_basis` | Where `i_load` came from |

`rules._load_evidence()` emits a `"<rail> load (declared)"` evidence row sourced to
`i_load_basis`, and `_check_rail_current` cites that **instead of** each consumer's `i_peak`
when a load is declared. `_check_rail_thermal` cites both mounting conditions when they are set.

The original text of this section follows, for the record.

---

### Original brief

All are additive with a `None` default, so existing behaviour is unchanged and the
existing suite should not move. If it does move, that is a finding — report it.

### 1.1 `PartSpec.theta_ja_mounting: str | None = None`

In `engine/models.py`, beside `theta_ja` and `theta_ja_source_line`.

θJA is a property of the installation, not of the package. onsemi publishes 160 °C/W for the
NCP1117 in SOT-223 at a **minimum size pad**; AMS publishes 46 to >90 °C/W for the same package
depending on copper area. Those two numbers are not comparable, and a field that records the
condition is what stops us presenting them as though they were.

Docstring should say that, briefly.

### 1.2 `PartSpec.t_j_max: float | None = None`

**This is the subtle one, and getting it wrong is how the demo becomes dishonest.**

`temp_max` is doing two incompatible jobs today. `temperature_rating` reads it as the part's
**ambient** temperature grade, checked against the board's required range. `thermal_dissipation`
(`rules.py:850` and `rules.py:869`) reads the same field as the part's **junction** limit.

For three of the four regulators those happen to coincide at 125 °C. For NCP1117ST33T3G they do
not: the distributor states `0℃~+125℃@(Ta)` — explicitly an ambient range — while onsemi's
datasheet states *"Maximum Die Junction Temperature Range TJ −55 to 150 °C"*. Using 125 as a
junction limit would fail the part against a number that is not a junction limit at all.

So: add `t_j_max`, and in `_check_rail_thermal` read `regulator.t_j_max or regulator.temp_max`
wherever the junction limit is needed. `temp_max` keeps its ambient-grade meaning everywhere
else. The `regulator.temp_max is None` early return at `rules.py:850` becomes a check on the
resolved limit.

### 1.3 `Requirements.mounting: str | None = None`

The board's copper area and construction — the basis for whichever θJA we applied. A string,
not a number: we are not interpolating anything, we are recording which row of the
manufacturer's table the value came from so a reader can check it.

Where it is used: in `_check_rail_thermal`, when `board.requirements.mounting` is set, append
one `Evidence` row to the thermal verdict — `Evidence(subject, "board mounting", mounting,
None)` — so the mounting condition appears beside the θJA it justifies. The field must not be
dead data.

### 1.4 `Rail.i_load: float | None = None`

The product line's declared rail load, in amperes.

When Continuity designs a board from a brief it chose every part, so summing what it placed *is*
the rail load. A product line already exists: it has a BOM of a couple of hundred lines and a
power budget somebody computed and signed. Deriving the load from the handful of parts we
modelled would under-count by construction.

**Change `draw.rail_draw()` to take the rail**, and return the declared figure when it is set:

```python
def rail_draw(
    board: Board, rail: Rail, consumers: list[tuple[str, PartSpec]],
    seen: frozenset[str] = frozenset(),
) -> tuple[float, list[str]]:
    if rail.i_load is not None:
        return rail.i_load, []
```

The empty `unstated` list is correct and deliberate: a declared load is complete by definition,
so the "this is a floor" caveat must not fire on it.

Three call sites: `draw.reflected_draw` (so a declared 3V3 load reflects correctly onto the 5 V
rail above it), `rules._check_rail_current` (`rules.py:600`), and `rules._check_rail_thermal`
(`rules.py:785`). Both rules reach the draw through this one function, which is why this is the
only change point.

**A verdict computed on a declared load must say so.** `Rail.basis` already exists for exactly
this — it is what makes a rail's own numbers cite their origin. `_supply_evidence` currently
only emits a row when `rail.basis` is set and reports voltage or `i_limit`; extend it, or add a
sibling, so that a rail with `i_load` set cites the declared load and its basis instead of
citing consumers' `i_peak`. A declared figure must never appear on screen looking like a sum of
parts.

---

## Part 2 · The fixture

Rewrite `backend/tools/eol_differential.py`. Keep it a runnable script
(`PYTHONPATH=. python -m tools.eol_differential` from `backend/`) — it is used to inspect the
case by eye — and rewrite the module docstring to describe what is actually there now.

### 2.1 The regulators

Every listing field below came from `search.get_part(mpn=...)` on 7 Sep 2026. Every datasheet
value is quoted in [PARTS.md](../PARTS.md).

| field | AMS1117-3.3 | TLV1117LV33DCYR | LD1117S33TR | NCP1117ST33T3G |
|---|---|---|---|---|
| LCSC | C6186 | **C15578** | C86781 | C26537 |
| `manufacturer` | Advanced Monolithic Systems | **Texas Instruments** | STMicroelectronics | onsemi |
| `package` | SOT-223 | SOT-223 | SOT-223 | SOT-223 |
| `vmax` | 15.0 | **5.5** | 15.0 | 20.0 |
| `vout_min` / `vout_max` | 3.3 / 3.3 | 3.3 / 3.3 | 3.3 / 3.3 | 3.3 / 3.3 |
| `i_max` | 1.0 | 1.0 | **0.8** | 1.0 |
| `temp_min` / `temp_max` | −40 / 125 | −40 / 125 | 0 / 125 | 0 / 125 |
| `t_j_max` | 125.0 | 125.0 | 125.0 | **150.0** |
| `theta_ja` | **60.0** | 62.9 | **None** | 160.0 |
| `stock` | 1493359 | 3416 | 41254 | 78632 |
| `unit_price` | 0.2176 | 0.3345 | 0.2429 | 0.2354 |
| `topology` | `"ldo"` | `"ldo"` | `"ldo"` | `"ldo"` |

`product_url` is `https://jlcpcb.com/partdetail/<LCSC>` for each.

**There are two JLCPCB listings for TLV1117LV33DCYR and you must use TI's.** JSMSEMI's
`C48937499` states 12 V and $0.1115; TI's `C15578` states 5.5 V and $0.3345. The current file
carries JSMSEMI's row with TI's datasheet θJA, which is the exact error this task exists to
remove — and only TI's ceiling produces the demo's voltage failure.

`theta_ja_source_line` and `theta_ja_mounting`, verbatim from each datasheet:

- **AMS1117-3.3** — value `60.0`. Source line: `"1000 Sq. mm / 1000 Sq. mm / 1000 Sq. mm — 60 °C/W"`.
  Mounting: `"Table 1, 1000 mm² top and back copper on a 1000 mm² board, 1/16in FR-4, 1 oz foil"`.
  Datasheet `http://www.advanced-monolithic.com/pdf/ds1117.pdf`.
  *Why 60 and not the headline 90:* the headline is footnoted *"46 °C/W to >90 °C/W depending on
  mounting technique and copper area"*, and the datasheet then publishes a copper-area table.
  The boards state their copper, so the table row that matches is the honest figure. Both ends
  of the range are still checked by the test below.
- **TLV1117LV33DCYR** — value `62.9`. Source line:
  `"RθJA Junction-to-ambient thermal resistance 62.9 °C/W"`. Mounting:
  `"TI thermal information, DCY (SOT-223) 4 pins"`.
  Datasheet `https://www.ti.com/lit/ds/symlink/tlv1117lv.pdf`.
- **LD1117S33TR** — `theta_ja=None`, `theta_ja_source_line=None`, `theta_ja_mounting=None`.
  Datasheet `https://www.st.com/resource/en/datasheet/ld1117.pdf`.
  **Do not fill this in.** ST's Table 3 has columns SOT-223 / SO-8 / DPAK / TO-220. `RthJC`
  carries four values; `RthJA` carries one, 50 °C/W, printed under the **TO-220** column. There
  is no published junction-to-ambient for SOT-223, and taking the 50 would attach a TO-220
  figure to a SOT-223 part. The engine must report that it cannot check, and the file should
  carry a comment saying why the field is empty so nobody helpfully fills it in later.
- **NCP1117ST33T3G** — value `160.0`. Source line:
  `"Thermal Resistance, Junction-to-Ambient, Minimum Size Pad — 160 °C/W"`. Mounting:
  `"minimum size pad, Case 318H (SOT-223)"`.
  Datasheet `https://www.onsemi.com/pdf/datasheet/ncp1117-d.pdf`.

Set `lifecycle` from the distributor listing only. AMS1117 going end-of-life is what the change
notice asserts; JLCPCB says nothing about it, so the part must not claim it.

### 2.2 The output capacitor

`C12891` · `CL31A226KAHNNNE` · Samsung Electro-Mechanics · `1206` · 22 µF ±10% · 25 V · X5R ·
basic part · 1,473,130 in stock · $0.1725.

`vmax=25.0`. `temp_min=-55.0`, `temp_max=85.0` — **derived from the stated X5R dielectric code
under EIA RS-198, not from the listing**, which states no operating temperature. Record that
derivation in `provenance` and in a comment; it is a standards lookup on a stated field rather
than an invention, and it must be visibly one or the other.

### 2.3 The loads

Real modules, replacing `mpn="LOAD"`. Currents are the distributor's own `Send Current` and
`Receive Current` where stated.

| line | part | LCSC | supply | temp | `i_peak` / `i_typ` | stock | price |
|---|---|---|---|---|---|---|---|
| A | ESP32-C3-MINI-1-N4, Espressif | C2838502 | 3–3.6 V | −40/+85 | 0.350 / 0.084 | 18086 | 3.8336 |
| B | ESP32-WROOM-32E-N4, Espressif | C701341 | 3–3.6 V | −40/+85 | 0.239 / 0.112 | 28108 | 3.7312 |
| C | STM32F103C8T6, STMicroelectronics | C8734 | 2–3.6 V | −40/+85 | **unset** | 224069 | 1.7203 |

STM32F103C8T6's listing states no current, so leave both fields `None`. Nothing depends on it:
the rail declares its load.

### 2.4 The three boards

Each board is three slots — `u1` regulator, `u2` load module, `c1` output capacitor — and two
rails.

| | A · Sensor node | B · Gateway | C · Cabinet controller |
|---|---|---|---|
| input rail voltage | 5.0 | 5.0 | 12.0 |
| input rail `i_limit` / `basis` | 3.0 / `"USB Type-C default Rp advertisement"` | 3.0 / same | 1.0 / `"12 V DIN-rail supply, product line power budget Rev C"` |
| 3V3 rail `i_load` | 0.150 | 0.420 | 0.060 |
| 3V3 rail `i_load_basis` | `"sensor node power budget Rev C — 150 mA continuous at 3V3"` | `"gateway power budget Rev C — 420 mA continuous at 3V3"` | `"cabinet controller power budget Rev C — 60 mA continuous at 3V3"` |

Note `i_load_basis`, not `basis` — see Part 1. The 3V3 rail's `basis` stays unset, because its
voltage comes from the regulator's datasheet and R1 already quotes it.
| `ambient_c` | 25 | 45 | 55 |
| `temp_range` | (0, 70) | (0, 70) | (0, 70) |
| `mounting` | `"1000 mm² top and back copper, 1/16in FR-4, 1 oz"` | same | same |

The `vin` rail has `members=("u1",)` and no source. The `3v3` rail has `source="u1"` and
`members=("u2", "c1")`.

---

## Part 3 · The acceptance test

Add a real test — `backend/tests/test_eol_differential.py` or wherever the suite keeps
fixture-level tests — that asserts the matrix. The script stays runnable for inspection, but a
printout is not a regression test.

Junction temperature is `ambient + power × θJA`, where power is `(V_in − 3.3) × i_load`.

| | A · 25 °C, 5 V, 150 mA | B · 45 °C, 5 V, 420 mA | C · 55 °C, 12 V, 60 mA |
|---|---|---|---|
| dissipation | 0.255 W | 0.714 W | 0.522 W |
| **AMS1117-3.3** | 40.3 °C, pass | 87.8 °C, pass | 86.3 °C, pass |
| **TLV1117LV33** | 41.0 °C, pass | 89.9 °C, pass | **fails `voltage_overlap`** |
| **LD1117S33** | thermal not checked | thermal not checked | thermal not checked |
| **NCP1117ST33** | 65.8 °C, pass | **fails `thermal_dissipation`, 159.2 °C vs 150 °C** | 138.5 °C, pass, 11.5 °C margin |

Assert, to ±0.5 °C where a temperature is named:

1. **AMS1117-3.3 passes `thermal_dissipation` on all three lines at both ends of its published
   spread** — substitute `theta_ja=46.0` and `theta_ja=90.0` and check it still passes
   everywhere. At 46 the gateway is 77.8 °C and at 90 it is 109.3 °C, both under 125. This is
   the claim that the conclusion does not depend on which end of AMS's range you believe, and
   it is the one most worth protecting with a test.
2. **TLV1117LV33 fails `voltage_overlap` on line C and only line C**, because 12 V exceeds its
   5.5 V ceiling. It passes thermal on all three.
3. **NCP1117ST33 fails `thermal_dissipation` on line B and only line B**, at 159.2 °C against
   its 150 °C junction limit — and the verdict must name 150, not 125.
4. **LD1117S33's thermal verdict rests on the package table, not on ST.** Note carefully: the
   package table *does* have an entry — `packages.theta_ja("SOT-223")` returns **62.0** — so
   with `theta_ja=None` the rule does not decline to answer. It substitutes a generic figure and
   discloses it, emitting an evidence row labelled `θJA (package table)` whose source is
   `packages.THETA_JA_SOURCE` rather than a datasheet URL.

   Assert exactly that: LD1117S33's thermal evidence cites the package table and **not** a
   datasheet, on all three lines, while the other three cite their datasheet. That seam is what
   item 3 converts into the `evidence missing` label, and pinning it now is what stops someone
   quietly setting `theta_ja=62.0` on the part and making the distinction disappear.

   Do **not** change the package table or the fallback in this task. That 62.0 standing against
   onsemi's published 160 for the same package is a real problem, and it is a bigger one than
   this fixture — it is raised separately.
5. **No candidate clears all three lines**, and the incumbent clears all three.

Also assert that a rail with `i_load` set reports that figure with no `unstated` entries, and
that a rail without it still sums its consumers exactly as before.

---

## Constraints

**Do not tune the fixture to quiet a rule.** If `pin_budget`, `interface_role_match`,
`footprint`, `rail_coverage` or anything else fires on these boards, that is information. Report
what fired and why; do not add a field to silence it and do not delete a slot to avoid it.

**Do not change the engine's behaviour beyond the four additions.** No new rules, no threshold
edits, no rewriting `thermal_dissipation`'s logic. The junction-limit resolution in 1.2 and the
draw resolution in 1.4 are the only behavioural changes in scope.

**Run the full suite** (`pytest` from `backend/`, with
`CONTINUITY_TEST_DB=postgresql:///continuity_test` for the store tests) and report the before
and after counts. 721 passed / 5 skipped is the baseline.

**Report anything that does not reconcile.** Several figures in this brief were wrong in the
previous version of the fixture and were only caught by opening the datasheets. If a number here
does not match what you find, that is more likely a real error than a typo to work around.
