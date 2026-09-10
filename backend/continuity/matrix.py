"""One candidate against every board that carries the part it would replace.

## What this is for

An end-of-life notice names a part, not a board. The question it raises is never "is this
substitute any good" — it is "is it good *here*, and here, and here", and the answer is
routinely different for each, because the same regulator runs at 25 °C in an open-air
sensor node and 45 °C inside a sealed gateway. A single verdict cannot express that, and a
manufacturer's recommendation is made without seeing any of it.

So the unit of work is a **cell**: one board, one candidate, evaluated in full.

## Why this does not go through the graph

Each cell is one `evaluate(board)` with the candidate substituted, and nothing more. No
repair loop, no interrupt, no per-cell checkpoint — a cell has no decisions to make, so
routing it through the graph would inherit machinery none of it uses.

The graph still does the thing only it can do, upstream: when the manufacturer's
recommendation fails somewhere, its repair loop is what proposes the next candidate to
try. **Repair produces rows; the fan-out fills them.** Keeping the two apart is what makes
the matrix reproducible — the same boards and candidates give the same grid every time,
with no model in the loop.

## Identity is recorded, never assumed

A cell reports the candidate found in the slot *after* substitution, read back off the
board rather than copied from the request. That sounds pedantic until a repair changes the
candidate mid-flight, at which point a result carrying the mpn that was asked for rather
than the one that was checked is a verdict attributed to a part nobody evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .engine import rules
from .engine.models import Board, CheckStatus, PartSpec, Verdict
from .roles import ANSWERABLE_RULES, decision_roles


@dataclass(frozen=True)
class Cell:
    """One candidate, evaluated against one board, in full."""

    line_id: str
    line_name: str
    candidate: PartSpec
    verdicts: tuple[Verdict, ...]

    incumbent_mpn: str | None = None
    """What this candidate would replace on this board, or `None` where it *is* the
    incumbent — the row that says what the board does today, which is not a substitution
    and must not be reported as one."""

    @property
    def is_incumbent(self) -> bool:
        return self.incumbent_mpn is None

    @property
    def failures(self) -> tuple[Verdict, ...]:
        return tuple(rules.failures(list(self.verdicts)))

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def gates(self) -> tuple[Verdict, ...]:
        """Failures a department can answer, as opposed to failures that are physics."""
        return tuple(v for v in self.failures if v.rule in ANSWERABLE_RULES)

    @property
    def answerable(self) -> bool:
        """Nothing physical stands, so what remains is somebody's decision.

        The same test `review.Attempt.gated` applies, and deliberately the same words: a
        candidate that is a proposal in the streaming review and a rejection in the change
        request would be two different products. Before 10 September they were — the review
        proposed a gated candidate and the document said *rejected because*, which showed up
        the moment `availability` became answerable and the Gateway's request lost its
        proposal entirely.
        """
        return bool(self.gates) and len(self.gates) == len(self.failures)

    @property
    def counts(self) -> dict[CheckStatus, int]:
        """Every coverage label, including the zeroes.

        Zeroes on purpose: a matrix that shows a count only when it is non-zero makes a
        reader compare cells of different shapes, and "no evidence missing here" is itself
        worth seeing beside a cell where three checks had nothing to read.
        """
        counted: dict[CheckStatus, int] = {
            "satisfied": 0, "failed": 0, "not_applicable": 0,
            "not_assessed": 0, "evidence_missing": 0,
        }
        for verdict in self.verdicts:
            counted[verdict.status] += 1
        return counted

    @property
    def margin(self) -> str | None:
        """The narrowest margin any satisfied check reports, where one can be ordered.

        Margins are prose because their units belong to their rules, so only a leading
        number can be compared honestly. A qualitative margin is still shown on its own
        verdict; it just cannot be called tighter than a measured one.
        """
        measurable: list[tuple[float, str]] = []
        for verdict in self.verdicts:
            if verdict.status != "satisfied" or not verdict.margin:
                continue
            head = verdict.margin.split()[0].lstrip("<").replace("−", "-")
            try:
                measurable.append((float(head), verdict.margin))
            except ValueError:
                continue
        return min(measurable)[1] if measurable else None

    @property
    def departments(self) -> tuple[str, ...]:
        """Whose desks this cell lands on, from what actually failed on it.

        Derived rather than assigned: a cell is owned by the people qualified to answer
        the questions it raises, and a cell that raises none is owned by nobody. Naming an
        owner for a passing cell would put a decision in front of someone who has none to
        make."""
        owners: list[str] = []
        for verdict in self.failures:
            for role in decision_roles(verdict):
                if role not in owners:
                    owners.append(role)
        return tuple(owners)


@dataclass(frozen=True)
class Matrix:
    """Every candidate against every board, and the arithmetic that produced each cell."""

    slot: str
    cells: tuple[Cell, ...]

    @property
    def candidates(self) -> tuple[str, ...]:
        seen: list[str] = []
        for cell in self.cells:
            if cell.candidate.mpn not in seen:
                seen.append(cell.candidate.mpn)
        return tuple(seen)

    @property
    def lines(self) -> tuple[str, ...]:
        seen: list[str] = []
        for cell in self.cells:
            if cell.line_id not in seen:
                seen.append(cell.line_id)
        return tuple(seen)

    def cell(self, line_id: str, mpn: str) -> Cell | None:
        return next(
            (c for c in self.cells if c.line_id == line_id and c.candidate.mpn == mpn), None
        )

    def viable_on_every_board(self) -> tuple[str, ...]:
        """Candidates that clear every board, which is the only kind worth recommending.

        A part that passes two of three lines is not a two-thirds answer — it is a part
        that breaks a product, and reporting it as a near miss is how a matrix becomes a
        way of losing information rather than keeping it.
        """
        return tuple(
            mpn
            for mpn in self.candidates
            if all(c.ok for c in self.cells if c.candidate.mpn == mpn)
        )

    def departments(self) -> tuple[str, ...]:
        owners: list[str] = []
        for cell in self.cells:
            for role in cell.departments:
                if role not in owners:
                    owners.append(role)
        return tuple(owners)


def substitute(board: Board, slot_id: str, candidate: PartSpec) -> Board:
    """A new board with `candidate` in `slot_id`, and the old part recorded as its baseline.

    The baseline is what `footprint_compatibility` compares against — "does this fit where
    the old one was" is unanswerable without it. Substituting a part for *itself* sets no
    baseline, because a board running the part it already runs is not a proposed change and
    reporting a land-pattern comparison against itself would be noise.
    """
    slot = board.slots[slot_id]
    outgoing = slot.part
    baseline = None if outgoing is not None and outgoing.mpn == candidate.mpn else outgoing

    # A regulator defines the rail it makes. Leaving the rail at the outgoing part's
    # voltage would check every downstream part against a number the proposed board does
    # not have — a 5 V substitute into a 3.3 V rail would pass, because nothing on the
    # board would ever be told the rail had moved. Only a *fixed* output is taken:
    # an adjustable part states a range and the rail's voltage is then set by the
    # feedback network, which is not in the BOM.
    rails = board.rails
    if candidate.vout is not None:
        rails = {
            rail_id: replace(rail, voltage=candidate.vout) if rail.source == slot_id else rail
            for rail_id, rail in board.rails.items()
        }

    return replace(
        board,
        slots={**board.slots, slot_id: replace(slot.with_part(candidate), baseline=baseline)},
        rails=rails,
    )


def evaluate_matrix(
    boards: Sequence[tuple[str, str, Board]],
    candidates: Sequence[PartSpec],
    slot_id: str,
) -> Matrix:
    """Every candidate against every board. Deterministic, and no model is involved.

    `boards` is `(line_id, line_name, board)` rather than a mapping so the caller decides
    the row order and it survives to the screen; a dict would hand that decision to
    whatever order the store happened to return.
    """
    cells: list[Cell] = []
    for line_id, line_name, board in boards:
        if slot_id not in board.slots:
            raise KeyError(
                f"{line_name} has no slot {slot_id!r}; a board that does not carry the "
                "part under review does not belong in this matrix"
            )
        for candidate in candidates:
            substituted = substitute(board, slot_id, candidate)
            placed = substituted.slots[slot_id]
            cells.append(
                Cell(
                    line_id=line_id,
                    line_name=line_name,
                    # Read back off the board, not copied from `candidate`: the cell
                    # reports what was actually evaluated.
                    candidate=placed.part,
                    incumbent_mpn=placed.baseline.mpn if placed.baseline else None,
                    verdicts=tuple(rules.evaluate(substituted)),
                )
            )
    return Matrix(slot=slot_id, cells=tuple(cells))
