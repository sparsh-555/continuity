# Item 18 · KiCad

BUILD said to research before planning, because none of this had been verified. It has now,
against KiCad **9.0.9** in the pinned container and a real third-party board. Everything
below was run, not read.

## What was proved, and how

The board is [diminDDL/ProPico](https://github.com/diminDDL/ProPico), MIT licensed, a
Raspberry Pi Pico compatible design that carries a genuine **AMS1117-3.3 in SOT-223** with
the JLCPCB code `C347222` on the symbol. It was saved by KiCad 7 and we did not write it,
which is the point: an ingestion path tested only against a file we authored proves nothing.

| Step | Command | Result |
| --- | --- | --- |
| BOM | `kicad-cli sch export bom --fields 'Reference,Value,Footprint,LCSC,${QUANTITY},${DNP}'` | 55 rows, LCSC codes included |
| Render | `kicad-cli pcb export svg --mode-single --layers F.Cu,F.SilkS,Edge.Cuts --exclude-drawing-sheet` | 271 kB SVG |
| Check | `kicad-cli pcb drc --format json --severity-all` | 54 violations, 1 unconnected item, 0 parity |
| Upgrade | `python3 -c "pcbnew.LoadBoard(...).Save(...)"` | KiCad 7 `20221018` → 9 `20241229` |
| Swap | `pcbnew` FootprintLoad + net remap by pad number | SOT-223 → SOT-23-5, three nets carried, two pads left |

**The consequence is measured by KiCad, not by us.** After swapping U3 from the SOT-223
AMS1117 to a SOT-23-5 ME6211, a second DRC run reports:

| | before | after |
| --- | --- | --- |
| unconnected items | 1 | **4** |
| shorting items | 0 | **4** |
| clearance | 0 | **3** |
| solder mask bridge | 5 | 15 |

Each unconnected item names both ends: *"Pad 2 [GND] of U3 on F.Cu"* against *"Via [GND] on
F.Cu - B.Cu"*, with millimetre coordinates. That is the footprint consequence, computed by
the tool that owns the question, and it is exactly the shape of evidence the rest of the
engine already produces.

## Decisions this settles

**Pinned at `kicad/kicad:9.0`, run through Docker.** The tag is amd64 only, so on Apple
silicon it needs `--platform linux/amd64`; the Docker Hub page's claim of arm64 does not hold
for this tag. Emulated, a BOM export takes a few seconds, which is irrelevant for an upload.

**An older board needs no conversion step, and this was measured rather than assumed.**
The first plan had a normalisation pass: a KiCad 9 library footprint is written in a dialect
the KiCad 7 file does not use, and mixing dialects by hand is how a board file gets quietly
corrupted. But nothing here edits text. `pcbnew` parses the 7 file into objects, accepts the
9 footprint into the same object model and writes 9 on save, and the swap against the
untouched upstream file gives byte-for-byte the same DRC answer as the swap against a
pre-upgraded copy: four unconnected items either way. So ingestion keeps the file it was
given, and the substituted copy is written at the pinned version by construction. The
original is never written back to.

**The swap uses `pcbnew`, deliberately, against BUILD's own note.** BUILD steered towards
`kicad-cli` because the SWIG bindings are deprecated from KiCad 9 and slated for removal in
11. That is a reason not to depend on them *loosely*, and the container pins the version, so
nothing moves underneath us. `kicad-cli` alone cannot do it: 9.0 has no board-writing command
at all — `--refill-zones` and `--save-board` are KiCad 10 arguments and 9.0.9 rejects them.
Everything that `kicad-cli` can do, it does; only the swap uses `pcbnew`, and when the
bindings go, that one file is what changes.

**Cropping needs page coordinates.** `--fit-page-to-board` produces a viewBox with no fixed
relationship to board coordinates, so a caller cannot say where a part is in the picture.
With `--page-size-mode 1` the SVG is the page, one user unit per millimetre, and a footprint
at `(104.24, 52.49)` in the board file is at `(104.24, 52.49)` in the SVG. The before and
after pictures then crop to the same rectangle, which is what makes them comparable at all.

**Read all three DRC arrays.** `violations`, `unconnected_items` and `schematic_parity` are
siblings, and a reader that takes only the first reports a clean board for one that is
entirely unrouted. A missing key is an error rather than an empty list, for the same reason:
an empty list renders exactly like a clean board.

## What this does not do

It does not route. Nothing here repairs the connections the swap breaks; it reports them,
which is the decision-grade fact — *this substitute costs a layout revision on this board and
that one does not*.

It does not decide the pin mapping. Pads carry `pinfunction` in a placed footprint but a
library footprint has none, so the mapping from the old package's nets to the new package's
pads is stated as data and shown to the reader, along with every pad left unassigned. On the
ME6211 those are pin 3 `EN`, which a real design must tie high, and pin 4 `NC`.

## Provenance

`ProPico` is MIT, Copyright (c) 2022 Dima. The licence travels with the vendored copy.

## Turning it on

    CONTINUITY_KICAD=docker                       # or `local`, for kicad-cli on the machine
    CONTINUITY_KICAD_IMAGE=kicad/kicad:9.0        # the default
    CONTINUITY_KICAD_PLATFORM=linux/amd64         # the default; needed on Apple silicon
    CONTINUITY_KICAD_CLI=/path/to/kicad-cli       # `local` only
    CONTINUITY_KICAD_PYTHON=/path/to/python3      # `local` only, needs pcbnew importable

Unset means **no KiCad**, and every route says so rather than guessing: an upload is still
stored and structurally checked, and the bill of materials and the substitution report the
capability as absent. Nothing here silently reaches for a two-gigabyte image because it
happens to be on the machine.

## What it looks like on the day

Attach the project from the product line's own menu on `/lines`. A line with no bill of
materials adopts the one KiCad reads out of the schematic; a line that already has one keeps
it, because a file dropped on a screen is not permission to overwrite a bill somebody typed.

Every change request with a proposal then carries a **THE BOARD** section: one button, and
the answer comes back as two pictures of the same twelve millimetres of board and the design
rule findings that appeared between them. `F.Paste` is in the render for a reason — with
copper alone, a regulator sitting on a ground pour is one red rectangle inside another, and
the pads have to be visible for the difference between a SOT-223 and a SOT-23-5 to be the
first thing in the picture.
