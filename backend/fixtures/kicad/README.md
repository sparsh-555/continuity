# A real KiCad project

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
