# Three real KiCad projects

`propico/` is [ProPico](https://github.com/diminDDL/ProPico), a Raspberry Pi Pico compatible
board, **MIT licensed, Copyright (c) 2022 Dima**. Its `LICENSE` travels with it, unmodified,
and so do the three project files exactly as upstream published them.

It is here because an ingestion path tested only against a file we wrote proves nothing. This
one was drawn by somebody else, in KiCad 7, and it carries a genuine **AMS1117-3.3 in SOT-223
at U3** with the JLCPCB code `C347222` on the symbol — the retired part of the demonstration,
on a board nobody made for the demonstration.

Only `.kicad_pro`, `.kicad_sch` and `.kicad_pcb` are vendored. The upstream repository also
carries symbol and footprint libraries, 3D models and Gerbers, none of which any command here
reads: symbols are cached inside the schematic and footprints inside the board.

---

## The other two, added 9 Sep

One project attached to three product lines would claim three different products are the
same board, and anybody can check that by opening two of them. So each affected line has its
own, found by searching GitHub for a KiCad schematic carrying an `AMS1117-3.3`.

| Folder | Project | Licence | Regulator at | What it is |
|---|---|---|---|---|
| `propico/` | ProPico | MIT, © 2022 Dima | **U3** | Raspberry Pi Pico compatible board |
| `ws2812/` | WS2812Controller | MIT, © Matthias Kleine | **U1** | WiFi controller for WS2812 LED strips, ESP-12F |
| `openjbod/` | OpenJBOD-RP2040 | CERN-OHL-P-2.0 | **U2** | Disk-enclosure controller: RP2040, W5500 Ethernet, EMC2301 fan controller |

Each licence file travels with its project, unmodified. Only `.kicad_pro`, `.kicad_sch` and
`.kicad_pcb` are vendored; OpenJBOD is hierarchical, so its sub-sheets come too.

**Three different designators is the point.** Every seeded product line used to put its
regulator at `u1`, which no real company does, and that uniformity was hiding a requirement:
the review has to resolve the position per board. It does. The one-shot review endpoint,
which takes a single position for every line, now refuses rather than guessing.

**OpenJBOD found two defects the day it arrived**, both recorded in `kicad/drc.py` and
`scripts/refill_zones.py`. It carries 687 copper zones where ProPico carries twenty, and
that difference was enough to expose stale zone fills and, underneath them, a verdict that
changed between runs of the same input. That is the argument for boards nobody here drew.
