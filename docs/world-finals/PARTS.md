# The demo's parts, verified

Every value below was read from the source named beside it on **7 Sep 2026** — the JLCPCB
listing through `graph.sourcing` (the same path the product uses), or the manufacturer's own
datasheet PDF opened and parsed. Nothing here is remembered, inferred from a package table, or
carried over from an earlier document.

This file exists because [BUILD.md](BUILD.md) item 1 requires that no value be invented and no
manufacturer's specification be attached to another manufacturer's listing. Checking that
turned up four errors in [SPEC.md](SPEC.md)'s demo case, recorded at the bottom.

---

## The listings

Fetched with `search.get_part(mpn=...)`, which is `jlc_get_part` under the hood.

| | AMS1117-3.3 | TLV1117LV33DCYR | LD1117S33TR | NCP1117ST33T3G |
|---|---|---|---|---|
| LCSC | C6186 | **C15578** | C86781 | C26537 |
| Manufacturer | Advanced Monolithic Systems | **Texas Instruments** | STMicroelectronics | onsemi |
| Library | **basic** | extended | extended | extended |
| Package | SOT-223 | SOT-223 | SOT-223 | SOT-223 |
| Voltage – Supply | 15 V | **5.5 V** | 15 V | 20 V |
| Output Current | 1 A | 1 A | **800 mA** | 1 A |
| Operating Temperature | −40 ~ +125 ℃ | −40 ~ +125 ℃ @(Tj) | 0 ~ +125 ℃ @(Tj) | 0 ~ +125 ℃ **@(Ta)** |
| Voltage Dropout | 1.1 V @ 800 mA | 455 mV @ 1 A | 1.1 V @ 800 mA | 1.2 V @ 800 mA |
| Stock | 1,493,359 | 3,416 | 41,254 | 78,632 |
| Unit price | $0.2176 | $0.3345 | $0.2429 | $0.2354 |

### The TLV1117LV33DCYR listing has to be TI's

JLCPCB carries **two** listings for that MPN and they do not agree:

| LCSC | Manufacturer | Voltage – Supply | Price | Stock |
|---|---|---|---|---|
| C48937499 | JSMSEMI | 12 V | $0.1115 | 167,495 |
| **C15578** | **Texas Instruments** | **5.5 V** | $0.3345 | 3,416 |

The current fixture carries JSMSEMI's row and TI's datasheet θJA — the exact
cross-manufacturer error item 1 exists to remove. It also matters to the story: only TI's
5.5 V ceiling fails a 12 V line.

**7 Sep 2026 — this recurred through the matrix, and both causes are now fixed.** Sourcing
a candidate by MPN alone picked whichever exact match came back first, which was JSMSEMI's
12 V row, so the cabinet controller passed a substitution that would destroy the part.
`api/matrix.resolve` now refuses to choose: one MPN listed by two manufacturers raises
`Ambiguous` and the grid names it, because which one you meant is a question only the
person asking can answer.

Separately, a *verified* datasheet reading now outranks a distributor's parametric table
on engineering fields — see `dossier.ENGINEERING_FIELDS`. TI publishes **2 V to 5.5 V
recommended** and **6 V absolute maximum** (SBVS160C §6.1, §6.3), so 12 V is double the
voltage the part survives. 5.5 V is the figure to hold: above the recommended maximum the
device may survive and is no longer performing to specification, and "it probably will not
die" is not an engineering sign-off. Commercial fields go the other way and always will —
stock, price, lead time and lifecycle are the distributor's to state and no datasheet knows
them.

### The output capacitor

`C12891` · **CL31A226KAHNNNE** · Samsung Electro-Mechanics · 1206 · 22 µF ±10% · 25 V · X5R ·
**basic** part · 1,473,130 in stock · $0.1725.

---

## The datasheets

Each PDF was downloaded and parsed. Where a value sits in a multi-column table, the column was
confirmed by the word's **x-coordinate**, not by the value merely appearing on the page.

### AMS1117-3.3 — Advanced Monolithic Systems, `ds1117.pdf`

- **Output voltage, AMS1117-3.3 at V_IN = 4.8 V: 3.251–3.349 V at 25 °C and 3.201–3.399 V
  over the full range**, from the Output Voltage row of the electrical characteristics. The
  wider pair is **±3.0% of 3.3 V** and it is what a worst-case deviation has to use; the
  percentage is derived from the published window and is recorded as a derivation.
- **Load regulation 0.4% Max**, from the Load Regulation row and repeated on the front page.
  The row's four figures are typ/max over two columns, and 0.4% is the guaranteed end.

- **θJA, SOT-223: 90 °C/W**, footnoted *"46 °C/W to >90 °C/W depending on mounting technique and
  copper area"*.
- Junction limit: *"Maximum junction temperature must not exceed 125 °C."*
- Junction-to-tab 15 °C/W; *"Thermal resistance from tab to ambient can be as low as 30 °C/W"*;
  *"The total thermal resistance from junction to ambient can be as low as 45 °C/W."*
- **Table 1 gives θJA against copper area**, measured on 1/16″ FR-4 with 1 oz copper, for the
  SOT-223 package:

  | Top side | Back side | Board area | θJA |
  |---|---|---|---|
  | 2500 mm² | 2500 mm² | 2500 mm² | 55 °C/W |
  | 1000 mm² | 2500 mm² | 2500 mm² | 55 °C/W |
  | 225 mm² | 2500 mm² | 2500 mm² | 65 °C/W |
  | 100 mm² | 2500 mm² | 2500 mm² | 80 °C/W |
  | 1000 mm² | 1000 mm² | 1000 mm² | 60 °C/W |
  | 1000 mm² | 0 | 1000 mm² | 65 °C/W |

- Output capacitor: *"The AMS1117 requires an output capacitor for device stability. Its value of
  22 µF tantalum covers all cases…"*, and *"22 µF solid tantalum on the output will ensure
  stability."*
- No minimum VIN is published; the seeded 4.4 V minimum is explicitly derived from 3.3 V
  output plus the 1.1 V dropout at 800 mA.

### TLV1117LV33DCYR — Texas Instruments, SBVS160C (Rev. Jan 2023)

- **Output accuracy ±1.5%**, quoted from Table 6.5, and **load regulation 35 mV maximum
  across 0–1 A** from the same table. On a 3.3 V rail 35 mV is **1.06%**, derived; the rail
  voltage decides that figure, so it is recorded as a derivation rather than a quotation.

- **RθJA 62.9 °C/W**, in §6.4 Thermal Information under the single column *DCY (SOT-223) 4
  PINS*. Unambiguous — one package column.
- Recommended operating: **VIN 2 V to 5.5 V**, IOUT 0–1 A. Absolute maximum VIN **6 V**. So a
  12 V rail exceeds even the absolute maximum.
- Junction: absolute maximum −55 to 150 °C, but *"For reliable operation, limit junction
  temperature to 125°C maximum."* The ordering table states −40 to 125 TJ.
- Output capacitor: *"For stability, 1.0-µF ceramic capacitors are required at the output… Use
  X5R- and X7R-type ceramic capacitors… Unlike traditional linear regulators that need a
  minimum ESR for stability, the TLV1117LV is specified to be stable with no ESR… Effective
  output capacitance… must be greater than 0.5 µF."*
- Electrical characteristics: output accuracy ±1.5%; load regulation is 35 mV maximum across
  0–1 A (Table 6.5).

### LD1117S33TR — STMicroelectronics, LD1117xx, **DocID2572 Rev 38**

- **Output voltage 3.235–3.365 V over TJ = 0 to 125 °C**, from Table 6, which is **±2.0% of
  3.3 V** and is what the worst case uses. The front page's *±1% trim* is a 25 °C figure and
  is deliberately not the one recorded: a guarantee over temperature is the one that holds
  on a board running at 55 °C. **Maximum load regulation 30 mV**, or **0.91%** on a 3.3 V
  rail, derived.

- **RthJA, SOT-223: 110 °C/W.** Table 2 *Thermal data*, columns SOT-223 / SO-8 / DPAK /
  TO-220, values 110 / 55 / 100 / 50 °C/W. Confirmed by word position: 110 sits at x = 299
  under SOT-223 at x = 288.

  **Read the revision before touching this number.** Rev 26 publishes `RthJA` for TO-220
  *only* — a single 50 °C/W printed at x = 458, under TO-220 at x = 448 — and reading that
  revision alone is how this part briefly looked as though ST had never characterised it in
  SOT-223. ST's own revision history for the sibling LD1117A datasheet dates the addition:
  *"19-Oct-2012 — Added: RthJA value for DPAK and SOT-223."* A stale mirror is a real hazard
  here; several of the first PDFs a search returns are Rev 26.
- Absolute maximum VIN 15 V (18 V below 20 mA); PTOT 12 W.
- *"TOP Operating junction temperature range — for standard version 0 to +150 °C"*; the
  electrical characteristics are specified over *"TJ = 0 to 125 °C"*.
- Output capacitor: CO = 10 µF in the characterisation conditions.
- Table 6 gives 3.235–3.365 V across 0–800 mA; the front page quotes ±1% trim and the table
  gives 30 mV maximum load regulation. The seeded 4.4 V input minimum is 3.3 V plus 1.1 V
  dropout at 800 mA, explicitly a derivation.

**Two traps here, and item 5 has to survive both.** A θJA extractor that only checks that a
number and a quote appear on the page would attach TO-220's 50 °C/W to a SOT-223 part and report
the coolest candidate in the field. And an extractor handed an outdated revision will conclude
the manufacturer published nothing, which is just as wrong in the other direction. Bind the
value to the column *and* record the document revision it came from.

### NCP1117ST33T3G — onsemi, NCP1117/D

- **Output voltage 3.235–3.365 V over the operating ambient range**, which is **±2.0% of
  3.3 V** and is used for the worst-case deviation. **Maximum load regulation 10 mV**, or
  **0.30%** on a 3.3 V rail, derived.

- **RθJA 160 °C/W**, row *"Thermal Resistance, Junction−to−Ambient, **Minimum Size Pad**"* under
  *Case 318H (SOT−223)*. The DPAK row beside it reads 67 °C/W, so the two are distinguishable.
- Junction-to-case 15 °C/W.
- **Maximum die junction temperature: TJ −55 to 150 °C.** The 0 to +125 °C that the distributor
  shows is the *Operating Ambient Temperature Range* (TA), a different quantity.
- Absolute maximum input 20 V; output current limit 1000–2200 mA.
- Figure 21 plots SOT-223 thermal resistance against PCB copper area, but it is a graph — no
  number from it is quotable.
- Cout is mandatory for stability: 4.7 µF minimum, with 33 mΩ (typical) to 2.2 Ω ESR; ceramic,
  tantalum, and aluminium electrolytic are permitted inside that window. The 3.3 V output row
  is 3.235–3.365 V over its operating ambient range; maximum load regulation is 10 mV. The
  seeded 4.5 V input minimum is 3.3 V plus 1.2 V dropout at 800 mA, explicitly a derivation.

---

### The parts the boards already carry — added 11 Sep 2026

The four regulators above are the substitution's candidates. These are the parts the bills
already fit, and until 11 September their readings carried no source line at all, so a change
request showed *source unavailable* beside every one of them. Each is now pinned to the line
that states it, in `tools/eol_differential.py`.

| Part | Reading | The line it came from |
|---|---|---|
| ESP32-C3-MINI-1-N4 | 3.0~3.6 V, −40 to 85 °C | Espressif, *Operating Conditions*: "Operating voltage/Power supply: 3.0~3.6 V"; "85 °C version module: –40 ~ 85 °C" |
| ESP32-WROOM-32E-N4 | 3.0~3.6 V, −40 to 85 °C | Espressif, *Operating Conditions*: "Operating voltage/Power supply: 3.0~3.6 V"; "85 °C version: –40~85 °C" |
| CL31A226KAHNNNE | 22 µF, 25 V, X5R, 1206 | Samsung, *Specification*: "CAP, 22uF, 25V, ±10%, X5R, 1206", and the part-number breakdown naming each code |
| STM32F103C8T6 | 2.0–3.6 V, −40 to 85 °C | **nothing, deliberately** — see below |

**The STM32F103C8T6's four readings have no line on purpose.** ST's current document is
**DS5319 Rev 20**. st.com will not serve it to a scripted download, and the only mirror that
answers is a **July 2007 Rev 2 marked *Preliminary***. Its "2.0 to 3.6 V application supply
and I/Os" is the right figure out of a document nobody should be citing, which is the LD1117
Rev 26 lesson above wearing different clothes. An unsourced reading is weaker than a sourced
one, and it is stronger than a wrong one.

Both Espressif modules exist in an 85 °C and a 105 °C version. The line quoted is the **85 °C**
one, which is what the distributor states and what these readings say. If a board ever carries
the 105 °C variant the citation will not match its part number, and naming the line rather than
the value is what makes that visible instead of silent.

---

### What these four sets of figures are for

`signal_integrity` stacks a regulator's published output accuracy with its published load
regulation, and checks that the resulting worst-case rail voltage stays inside every load's
published supply window. Three of the four figures above are **derived from a published
window** rather than quoted as a percentage, and each says so where it is recorded: a
datasheet that states 3.201–3.399 V has stated ±3.0% of 3.3 V without ever printing the
percentage, and printing it here without saying where it came from would be the kind of
number this document exists to prevent.

Line regulation is a third published figure and is deliberately **not** stacked. It describes
what the output does when the *input* moves, and this check is about the output under load.
The rule's own evidence sentence names the two it did stack, so the denominator is on screen
rather than implied.

---

## θJA is a mounting condition, not a package property

The four figures above are **not measured on the same board**, and comparing them directly is a
methodological error a hardware engineer would catch immediately.

| Part | θJA | The condition it was measured under |
|---|---|---|
| AMS1117-3.3 | 46 – >90 | Explicitly copper-area dependent; Table 1 gives 55–80 by area |
| TLV1117LV33 | 62.9 | TI thermal information, JEDEC test board |
| LD1117S33 | 110 | ST Table 2, SOT-223 column, DocID2572 Rev 38 |
| NCP1117ST33 | 160 | **Minimum size pad** — onsemi's own qualifier |

So a board's **copper area has to be part of its operating profile** before any of these
numbers can be applied to it. That is `mounting` in [SPEC.md](SPEC.md)'s data model, and it is
what makes the θJA on a verdict mean something.

---

## What this corrects in SPEC.md

1. ~~LD1117S33's θJA of 110 has no source.~~ **Withdrawn — 110 °C/W was right.** It is ST's
   published SOT-223 figure in DocID2572 Rev 38. The claim that it was unsourced came from
   reading Rev 26, which predates the addition of that column. Corrected 7 Sep 2026.
2. **NCP1117's junction limit is 150 °C, not 125.** The 125 is an ambient rating. SPEC's
   "fails: 134 °C" does not fail against 150.
3. **AMS1117's published range is 46 to >90, not 46–95**, with a copper-area table behind it.
4. **TI does not say "do not use an electrolytic output capacitor."** It requires ≥ 1.0 µF
   ceramic, X5R or X7R, with effective capacitance above 0.5 µF, and states the part is stable
   with no ESR. The AMS1117 is the one with a dielectric requirement — 22 µF *tantalum*.

The four values that survive unchanged are TLV1117LV33's 62.9 °C/W, its 5.5 V ceiling,
NCP1117's 160 °C/W, and the 125 °C junction limits on AMS1117 and TLV1117LV33.
