"""What a substitute does to a board, asked and answered in one call.

The sequence is the argument. Check the board as it stands; put the substitute's footprint
where the retired part sits, carrying each net to the pad with the same function; check it
again; render both. Nothing here decides whether the result is acceptable. It reports what
KiCad found, and *that* is the fact a change request needs: this substitute costs a layout
revision on this board and none on that one.

## The nets are carried by function, never by position

The old footprint's pads say what they were for, because the schematic put a function on
each of them. The substitute's pinout says which of its pads have those functions. Matching
those two is the whole mapping, and every pad the substitute has that the mapping does not
cover is reported rather than left silently bare — on a SOT-23-5 regulator those are the
enable pin, which a real design must tie high, and a no-connect.

A function on the old part that the new one does not have is reported too. That is a net
with nowhere to go, and it is the loudest thing that can happen to a board.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import drc, pins, render
from .project import Project
from .runner import Runner

SCRIPTS = Path(__file__).parent / "scripts"

FOOTPRINT_LIBRARY = "/usr/share/kicad/footprints"
"""Where KiCad's own footprints live inside the pinned image."""


class NoSuchPart(ValueError):
    """The board has no footprint with that reference designator."""


@dataclass(frozen=True)
class Pad:
    number: str
    net: str | None
    function: str | None

    @property
    def role(self) -> str | None:
        return pins.role_of(self.function)


@dataclass(frozen=True)
class Placement:
    """One footprint as the board has it placed."""

    refdes: str
    value: str
    footprint: str
    x_mm: float
    y_mm: float
    pads: tuple[Pad, ...]

    def nets_by_role(self) -> dict[str, str]:
        """Which net each role sits on. First pad wins; a tab repeats its pin's net."""
        found: dict[str, str] = {}
        for pad in self.pads:
            role, net = pad.role, pad.net
            if role and net and role not in found:
                found[role] = net
        return found


@dataclass(frozen=True)
class Wiring:
    """How the substitute's pads were connected, and what was left."""

    wired: Mapping[str, str]
    unwired_pads: tuple[str, ...]
    roles_with_nowhere_to_go: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.roles_with_nowhere_to_go


@dataclass(frozen=True)
class Consequence:
    """The whole answer for one substitute on one board."""

    placement: Placement
    footprint: str
    wiring: Wiring
    delta: drc.Delta
    before: render.Picture
    after: render.Picture
    crop: render.Crop

    @property
    def broke_connections(self) -> bool:
        return self.delta.broke_connections


def _run_script(runner: Runner, name: str, arguments: list[str], *, workdir: Path) -> None:
    """Scripts are shipped in this package and copied in, because a container only sees
    what is mounted."""
    shutil.copy(SCRIPTS / name, workdir / name)
    runner.python_run([name, *arguments], workdir=workdir)


def placements(project: Project, runner: Runner) -> dict[str, Placement]:
    """Every footprint the board places, by reference designator."""
    out = "kicad-board.json"
    _run_script(
        runner, "inspect_board.py", [project.board_name, out], workdir=project.root
    )
    payload = json.loads((project.root / out).read_text(encoding="utf-8"))
    placed = {}
    for entry in payload["footprints"]:
        placed[entry["refdes"]] = Placement(
            refdes=entry["refdes"],
            value=entry["value"],
            footprint=entry["footprint"],
            x_mm=float(entry["x_mm"]),
            y_mm=float(entry["y_mm"]),
            pads=tuple(
                Pad(number=pad["number"], net=pad["net"], function=pad["function"])
                for pad in entry["pads"]
            ),
        )
    return placed


def _mapping(placement: Placement, pinout: Mapping[str, str]) -> Wiring:
    """Which net lands on which pad of the substitute, by function on both sides."""
    nets = placement.nets_by_role()
    wired: dict[str, str] = {}
    bare: list[str] = []
    for pad_number, function in pinout.items():
        role = pins.role_of(function)
        net = nets.get(role) if role else None
        if net is None:
            bare.append(pad_number)
            continue
        wired[pad_number] = net
    carried = {
        pins.role_of(function)
        for pad, function in pinout.items()
        if pad in wired
    }
    stranded = tuple(role for role in sorted(nets) if role not in carried)
    return Wiring(
        wired=wired, unwired_pads=tuple(sorted(bare)), roles_with_nowhere_to_go=stranded
    )


def consequence(
    project: Project,
    runner: Runner,
    *,
    refdes: str,
    footprint: str,
    pinout: Mapping[str, str],
    value: str | None = None,
    library_root: str = FOOTPRINT_LIBRARY,
) -> Consequence:
    """Substitute one part on a copy of the board and report what changed.

    `footprint` is a KiCad footprint identifier, `Library:Name`. `pinout` maps the
    substitute's pad numbers to the function each one has, which is a datasheet reading and
    belongs to the caller — nothing here infers a pinout from a package name.

    The original board file is never written to. The substituted copy is a new file beside
    it, which is also what makes the two renders comparable.
    """
    placed = placements(project, runner)
    if refdes not in placed:
        raise NoSuchPart(
            f"this board has no {refdes}. It places "
            f"{', '.join(sorted(placed)[:8])}{'…' if len(placed) > 8 else ''}."
        )
    placement = placed[refdes]
    wiring = _mapping(placement, pinout)

    library, _, name = footprint.partition(":")
    if not name:
        raise ValueError(f"{footprint!r} is not a Library:Name footprint identifier")

    after_board = f"kicad-after-{refdes}.kicad_pcb"
    spec = {
        "refdes": refdes,
        "library": f"{library_root.rstrip('/')}/{library}.pretty",
        "footprint": name,
        "value": value,
        "nets": dict(wiring.wired),
    }
    (project.root / "kicad-swap.json").write_text(json.dumps(spec), encoding="utf-8")
    _run_script(
        runner,
        "swap_footprint.py",
        [project.board_name, after_board, "kicad-swap.json", "kicad-swap-report.json"],
        workdir=project.root,
    )

    # Both boards through the same filler, each in its own interpreter. `pcbnew` keeps
    # global state and two boards in one process made the same input answer differently.
    filled_before = f"kicad-filled-before-{refdes}.kicad_pcb"
    filled_after = f"kicad-filled-after-{refdes}.kicad_pcb"
    _run_script(runner, "refill_zones.py", [project.board_name, filled_before],
                workdir=project.root)
    _run_script(runner, "refill_zones.py", [after_board, filled_after], workdir=project.root)

    before = drc.run(
        runner, workdir=project.root, board=filled_before, out="kicad-drc-before.json"
    )
    after = drc.run(
        runner, workdir=project.root, board=filled_after, out="kicad-drc-after.json"
    )

    return Consequence(
        placement=placement,
        footprint=footprint,
        wiring=wiring,
        delta=drc.compare(before, after),
        before=render.svg(
            runner, workdir=project.root, board=project.board_name, out="kicad-before.svg"
        ),
        after=render.svg(
            runner, workdir=project.root, board=after_board, out="kicad-after.svg"
        ),
        crop=render.around(placement.x_mm, placement.y_mm),
    )
