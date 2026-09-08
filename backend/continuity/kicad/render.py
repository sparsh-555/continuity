"""A picture of the board, in coordinates a caller can point at.

## Page coordinates, deliberately

`--fit-page-to-board` crops to the design, which sounds like what a viewer wants and makes
the picture useless for pointing: the resulting viewBox has no fixed relationship to the
board file, so nothing can say *the regulator is here*. With `--page-size-mode 1` the SVG is
the page, one user unit per millimetre, and a footprint at `(104.24, 52.49)` in the board is
at `(104.24, 52.49)` in the picture.

That is what makes a before and an after comparable: both crop to the same rectangle around
the part that changed, so the reader sees one thing move rather than two pictures that need
aligning by eye.

## Copper, silkscreen, outline

Enough to see pads, tracks and where the board ends. The fabrication layers are noise for
this question, and a mask layer would hide the very pads the reader is looking at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .runner import Runner

LAYERS = "F.Cu,F.SilkS,F.Paste,Edge.Cuts"
"""The top of the board, which is where a substituted part lands.

**`F.Paste` is in the list to make the pads visible at all.** On a board with a ground pour
under the regulator, the pads are copper on copper: the same colour as everything around
them, and a reader looking for the part sees one red rectangle inside another. The paste
apertures are exactly the pads, drawn in their own colour, and with them the difference
between a SOT-223 and a SOT-23-5 is the first thing in the picture rather than something to
hunt for. `F.Fab` was tried alongside and removed: it draws every component's value at
footprint scale, and the crop filled with letters.

The back copper was in this list once and made the picture unreadable: a ground pour on
B.Cu is drawn over everything and turns the whole crop one colour. What breaks on the back
of the board is not lost by leaving it out — the design rule check names every item on
either side, with coordinates."""

DEFAULT_MARGIN_MM = 6.0
"""Context either side of the part, in millimetres.

A SOT-223 is 6.5 mm by 3.5 mm before its pads, so a twelve-millimetre window holds the part
and the tracks reaching it. Wider than this and a regulator on a densely poured board
becomes a red rectangle somewhere in the middle of another red rectangle."""


@dataclass(frozen=True)
class Crop:
    """A rectangle in board millimetres, which is also SVG user units."""

    x: float
    y: float
    width: float
    height: float

    @property
    def view_box(self) -> str:
        return f"{self.x:.4f} {self.y:.4f} {self.width:.4f} {self.height:.4f}"


def around(x_mm: float, y_mm: float, margin: float = DEFAULT_MARGIN_MM) -> Crop:
    return Crop(x=x_mm - margin, y=y_mm - margin, width=margin * 2, height=margin * 2)


@dataclass(frozen=True)
class Picture:
    """One rendered board, and the page it was drawn on.

    The page size travels with the picture because a crop is meaningless without it: a
    viewer scaling the SVG into a box needs to know that its user units run 0 to 210, or
    the rectangle it was handed points somewhere else entirely.
    """

    svg: str
    width_mm: float
    height_mm: float


_SIZE = re.compile(r'width="([0-9.]+)mm"\s+height="([0-9.]+)mm"')


def page_of(svg_text: str) -> tuple[float, float]:
    """The page size KiCad declared, or a refusal — nothing here guesses A4."""
    found = _SIZE.search(svg_text[:2000])
    if not found:
        raise ValueError("that SVG declares no millimetre page size")
    return float(found.group(1)), float(found.group(2))


def svg(runner: Runner, *, workdir: Path, board: str, out: str) -> Picture:
    """Render one board and return the picture with its page size."""
    runner.cli_run(
        [
            "pcb",
            "export",
            "svg",
            "-o",
            out,
            "--mode-single",
            "--layers",
            LAYERS,
            "--exclude-drawing-sheet",
            "--page-size-mode",
            "1",
            board,
        ],
        workdir=workdir,
    )
    text = (workdir / out).read_text(encoding="utf-8")
    width, height = page_of(text)
    return Picture(svg=text, width_mm=width, height_mm=height)
