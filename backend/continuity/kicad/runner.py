"""How a KiCad command gets run, and what happens when there is none.

KiCad is a desktop application, not a library. Everything this package needs — a bill of
materials out of a schematic, a picture of a board, a design rule check, a footprint
swapped for another — is a program we invoke, and the whole point of doing it that way is
that **KiCad answers the question, not us**. The same division the engine already lives
under: the tool that owns the fact produces it.

## The version is pinned, and it is checked

File formats move between KiCad releases. A board written by 7 is not a board written by 9,
and a 9 library footprint dropped into a 7 file is a corrupted board rather than an error.
So the version is pinned, and `check()` refuses to proceed against anything else instead of
finding out halfway through a write.

## Two ways to have KiCad, and no third

`CONTINUITY_KICAD=docker` runs the pinned image. `CONTINUITY_KICAD=local` runs binaries
already on the machine. Anything else means *no KiCad*, and every caller reports the
capability as unavailable rather than degrading into a guess. Nothing here quietly reaches
for a two-gigabyte image because it happened to be installed.

On Apple silicon the pinned tag is amd64 only — the Docker Hub page's arm64 claim does not
hold for `9.0` — so `--platform` is passed explicitly and emulation does the rest.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .. import env

PINNED = "9.0"
"""The KiCad minor line every file format and command argument here was verified against."""

DEFAULT_IMAGE = "kicad/kicad:9.0"
DEFAULT_PLATFORM = "linux/amd64"
DEFAULT_TIMEOUT_S = 300.0

MOUNT = "/work"
"""Where the working directory appears inside the container."""


class Unavailable(RuntimeError):
    """No KiCad is configured, or the configured one could not be run."""


class KicadFailed(RuntimeError):
    """KiCad ran and refused. Carries what it said, which is usually the whole answer."""

    def __init__(self, argv: list[str], code: int, output: str) -> None:
        super().__init__(f"kicad exited {code}: {output.strip()[:400]}")
        self.argv = argv
        self.code = code
        self.output = output


@dataclass(frozen=True)
class Completed:
    argv: list[str]
    code: int
    output: str


@dataclass(frozen=True)
class Runner:
    """One way to run KiCad against a directory of files.

    Every path a caller passes is **relative to the working directory**, which is the only
    shape that means the same thing in a container and on a laptop.
    """

    kind: str
    image: str | None = None
    platform: str | None = None
    cli: str = "kicad-cli"
    python: str = "python3"

    def _argv(self, command: list[str], workdir: Path) -> list[str]:
        if self.kind == "local":
            return command
        mount = ["-v", f"{workdir.resolve()}:{MOUNT}", "-w", MOUNT]
        platform = ["--platform", self.platform] if self.platform else []
        return ["docker", "run", "--rm", *platform, *mount, str(self.image), *command]

    def run(
        self,
        command: list[str],
        *,
        workdir: Path,
        timeout: float = DEFAULT_TIMEOUT_S,
        check: bool = True,
    ) -> Completed:
        argv = self._argv(command, workdir)
        try:
            finished = subprocess.run(
                argv,
                cwd=workdir if self.kind == "local" else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:  # docker itself, or kicad-cli, is not there
            raise Unavailable(f"could not run {argv[0]}: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise Unavailable(f"{argv[0]} did not finish within {timeout:g}s") from error

        # KiCad writes some of its own progress to stderr, so both streams are one answer.
        output = (finished.stdout or "") + (finished.stderr or "")
        if check and finished.returncode != 0:
            raise KicadFailed(argv, finished.returncode, output)
        return Completed(argv, finished.returncode, output)

    def cli_run(self, arguments: list[str], **kwargs) -> Completed:
        return self.run([self.cli, *arguments], **kwargs)

    def python_run(self, arguments: list[str], **kwargs) -> Completed:
        """Run a script through the interpreter that has `pcbnew` on its path."""
        return self.run([self.python, *arguments], **kwargs)

    def version(self, *, workdir: Path) -> str:
        return self.cli_run(["version"], workdir=workdir, timeout=120.0).output.strip()

    def check(self, *, workdir: Path) -> str:
        """The running version, or a refusal naming what was found against what is pinned."""
        found = self.version(workdir=workdir)
        if not found.startswith(PINNED):
            raise Unavailable(
                f"this build is pinned to KiCad {PINNED} and found {found!r}. File formats "
                f"and command arguments differ between releases, so nothing is written "
                f"against an unverified version."
            )
        return found


def configured() -> Runner | None:
    """The runner this deployment declares, or `None` when it declares none."""
    env.load()
    kind = (os.environ.get("CONTINUITY_KICAD") or "").strip().lower()
    if kind == "docker":
        return Runner(
            kind="docker",
            image=os.environ.get("CONTINUITY_KICAD_IMAGE") or DEFAULT_IMAGE,
            platform=os.environ.get("CONTINUITY_KICAD_PLATFORM") or DEFAULT_PLATFORM,
        )
    if kind == "local":
        return Runner(
            kind="local",
            cli=os.environ.get("CONTINUITY_KICAD_CLI") or "kicad-cli",
            python=os.environ.get("CONTINUITY_KICAD_PYTHON") or "python3",
        )
    return None


def available() -> bool:
    """Whether a KiCad is configured *and* the program behind it exists.

    Deliberately cheap: it does not start a container. A configuration naming a runner
    whose program is missing is the common mistake, and it is worth answering before an
    upload rather than after.
    """
    runner = configured()
    if runner is None:
        return False
    program = "docker" if runner.kind == "docker" else runner.cli
    return shutil.which(program) is not None


def require() -> Runner:
    runner = configured()
    if runner is None:
        raise Unavailable(
            "no KiCad is configured. Set CONTINUITY_KICAD=docker to use the pinned "
            f"{DEFAULT_IMAGE} image, or CONTINUITY_KICAD=local with kicad-cli installed."
        )
    return runner
