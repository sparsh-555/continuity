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

### The output capacitor

`C12891` · **CL31A226KAHNNNE** · Samsung Electro-Mechanics · 1206 · 22 µF ±10% · 25 V · X5R ·
**basic** part · 1,473,130 in stock · $0.1725.

---

## The datasheets

Each PDF was downloaded and parsed. Where a value sits in a multi-column table, the column was
confirmed by the word's **x-coordinate**, not by the value merely appearing on the page.

### AMS1117-3.3 — Advanced Monolithic Systems, `ds1117.pdf`

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

### TLV1117LV33DCYR — Texas Instruments, SBVS160C (Rev. Jan 2023)

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

### LD1117S33TR — STMicroelectronics, LD1117xx, **DocID2572 Rev 38**

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

**Two traps here, and item 5 has to survive both.** A θJA extractor that only checks that a
number and a quote appear on the page would attach TO-220's 50 °C/W to a SOT-223 part and report
the coolest candidate in the field. And an extractor handed an outdated revision will conclude
the manufacturer published nothing, which is just as wrong in the other direction. Bind the
value to the column *and* record the document revision it came from.

### NCP1117ST33T3G — onsemi, NCP1117/D

- **RθJA 160 °C/W**, row *"Thermal Resistance, Junction−to−Ambient, **Minimum Size Pad**"* under
  *Case 318H (SOT−223)*. The DPAK row beside it reads 67 °C/W, so the two are distinguishable.
- Junction-to-case 15 °C/W.
- **Maximum die junction temperature: TJ −55 to 150 °C.** The 0 to +125 °C that the distributor
  shows is the *Operating Ambient Temperature Range* (TA), a different quantity.
- Absolute maximum input 20 V; output current limit 1000–2200 mA.
- Figure 21 plots SOT-223 thermal resistance against PCB copper area, but it is a graph — no
  number from it is quotable.
- Capacitors: Cin = 10 µF, Cout = 10 µF in the characterisation conditions.

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
