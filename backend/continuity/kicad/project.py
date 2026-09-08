"""A KiCad project as it arrives: a zip file somebody exported, or a directory on disk.

## What a bundle has to contain

A schematic and a board, sharing the project's name. The schematic is where a bill of
materials comes from and the board is where a footprint has consequences, so a bundle
missing either is refused *naming which*, rather than half-ingested.

## Unpacking is where the danger is

A zip is a file somebody else wrote. Members with absolute paths or `..` in them escape the
directory they are unpacked into, which is how an upload becomes a write anywhere the server
can reach; sizes and counts are how one becomes a full disk. Every member is checked before
anything is written, and a bundle that fails is refused whole.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

MAX_MEMBERS = 2_000
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
"""A KiCad project with 3D models runs to tens of megabytes. Beyond this it is not one."""


class NotAProject(ValueError):
    """The bundle is not a KiCad project, and the message says what was missing."""


@dataclass(frozen=True)
class Project:
    """The files of one KiCad project, inside a directory we control."""

    root: Path
    name: str
    schematic: Path
    board: Path

    @property
    def schematic_name(self) -> str:
        return str(self.schematic.relative_to(self.root))

    @property
    def board_name(self) -> str:
        return str(self.board.relative_to(self.root))


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise NotAProject(f"that archive holds {len(members)} files, which is not a project")
    total = 0
    for member in members:
        name = member.filename
        if name.startswith("/") or ".." in Path(name).parts:
            raise NotAProject(f"that archive contains an unsafe path: {name!r}")
        total += member.file_size
        if total > MAX_UNPACKED_BYTES:
            raise NotAProject("that archive unpacks to more than 200 MB")
    return members


def unpack(archive_bytes: bytes, into: Path) -> Path:
    """Unpack a zip into a directory we own, or refuse it."""
    into.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            members = _safe_members(archive)
            archive.extractall(into, members=members)
    except zipfile.BadZipFile as error:
        raise NotAProject("that file is not a zip archive") from error
    return into


def find(root: Path) -> Project:
    """The project inside a directory, or a refusal naming what is missing.

    A KiCad project is a set of files sharing one stem. Sub-sheets are separate
    `.kicad_sch` files, so the root schematic is the one whose name matches the project's,
    and taking any other would export a bill of materials for one page of a design.
    """
    projects = sorted(root.rglob("*.kicad_pro"), key=lambda path: len(path.parts))
    if not projects:
        boards = sorted(root.rglob("*.kicad_pcb"), key=lambda path: len(path.parts))
        if boards:
            raise NotAProject(
                "that bundle has a board but no .kicad_pro, so its schematic cannot be "
                "identified. Zip the whole project directory."
            )
        raise NotAProject("no KiCad project (.kicad_pro) was found in that bundle")

    project = projects[0]
    schematic = project.with_suffix(".kicad_sch")
    board = project.with_suffix(".kicad_pcb")
    missing = [
        name
        for name, path in (("schematic", schematic), ("board", board))
        if not path.is_file()
    ]
    if missing:
        raise NotAProject(
            f"{project.name} has no {' and no '.join(missing)}. Both are needed: the "
            f"schematic carries the parts, the board carries their footprints."
        )
    return Project(root=root, name=project.stem, schematic=schematic, board=board)
