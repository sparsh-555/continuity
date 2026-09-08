"""One substitution, on one board, with the desk that owns the answer named.

The board already exists, so there is no planner here. The run is: put the candidate where
the retired part sits, re-check the **whole** board, and read what the engine says. Same
rules, same coverage labels, same evidence as everywhere else.

## The part that is new

`change.py` chose a proposal from the candidates that clear every rule. That leaves the most
interesting answer on the floor: a part that is electrically perfect and **not on the
approved list** is not *unviable*, it is *somebody else's decision*. On the seeded Gateway
that part is LD1117S33TR, which holds the board with 1.5 °C to spare and has never been
qualified, while the manufacturer's own recommendation runs 9 °C over its junction limit.

So a candidate lands in one of three states:

  **clear** — nothing failed. Engineering signs it, because a change to a released design is
  approved before it is implemented, never after.
  **gated** — the only failures are the rules a department owns: qualification is quality's,
  source approval is procurement's. The part works. The answer is not engineering's.
  **blocked** — something physical failed. No signature makes 159 °C into 150 °C.

That is the whole of Scenario B's question in three lines: design validates, procurement
checks availability, production confirms assembly, and the tool routes rather than decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .engine import rules
from .engine.models import Board, PartSpec, Verdict
from .matrix import substitute
from .roles import decision_roles

GATE_RULES = ("part_qualification", "source_approval")
"""Rules a department owns rather than physics. A failure here is a decision, not a wall."""


@dataclass(frozen=True)
class Attempt:
    """One candidate placed on this board, and everything the engine said about it."""

    candidate: PartSpec
    verdicts: tuple[Verdict, ...]

    @property
    def mpn(self) -> str:
        return self.candidate.mpn

    @property
    def blocking(self) -> tuple[Verdict, ...]:
        """Failed, and not waived. What the graph would route on."""
        return tuple(rules.blocking(list(self.verdicts)))

    @property
    def gates(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.blocking if v.rule in GATE_RULES)

    @property
    def physical(self) -> tuple[Verdict, ...]:
        """Failures no signature can clear."""
        return tuple(v for v in self.blocking if v.rule not in GATE_RULES)

    @property
    def clear(self) -> bool:
        return not self.blocking

    @property
    def gated(self) -> bool:
        return bool(self.gates) and not self.physical

    @property
    def margin(self) -> str | None:
        """The headline margin, and only when there is a measured one.

        Thermal first, because it is the one that decides these boards. The fallback is
        restricted to margins that begin with a number: `availability` reports "lifecycle
        concern", which is a real margin and reads as nonsense in the sentence this feeds —
        *"clears every check, with lifecycle concern to spare"*. Seen live.
        """
        for verdict in self.verdicts:
            if verdict.rule == "thermal_dissipation" and verdict.margin:
                return verdict.margin
        for verdict in self.verdicts:
            if verdict.margin and verdict.margin[:1].isdigit():
                return verdict.margin
        return None


@dataclass(frozen=True)
class Proposal:
    """What this board should do, and who has to say so."""

    mpn: str
    roles: tuple[str, ...]
    detail: str

    gate_rule: str | None = None
    """The department rule standing between the part and the board, when there is one.

    `None` means nothing failed and the approval is the ordinary one every released design
    needs. A rule here means the part works and the decision belongs to another desk."""

    @property
    def conditional(self) -> bool:
        return self.gate_rule is not None


@dataclass(frozen=True)
class Outcome:
    """The end of one line's run."""

    line_id: str
    line_name: str
    slot_id: str
    retiring: str
    attempts: tuple[Attempt, ...]
    proposal: Proposal | None

    @property
    def viable(self) -> bool:
        return self.proposal is not None


def attempt(board: Board, slot_id: str, candidate: PartSpec) -> Attempt:
    """Place the candidate and re-check the whole board.

    The whole board, not the slot: a regulator moves the rail it makes, and a substitution
    that only re-checked its own position would clear a part that browns out everything
    downstream of it.
    """
    substituted = substitute(board, slot_id, candidate)
    placed = substituted.slots[slot_id]
    # Read the part back off the board rather than trusting what was handed in, exactly as
    # the matrix does: the attempt reports what was actually evaluated.
    return Attempt(candidate=placed.part, verdicts=tuple(rules.evaluate(substituted)))


def choose(attempts: Sequence[Attempt], *, excluded: Mapping[str, str] | None = None) -> Proposal | None:
    """The board's answer, in the caller's order of preference.

    Order matters and is the caller's: a part already on the approved list resolves for
    about a twelfth of what qualifying one from scratch costs, so "try the cheap answer
    first" is a real input rather than a tie break.

    A part this board already ruled out is never proposed again, whatever it scores. That is
    the whole point of remembering a rejection.
    """
    ruled_out = dict(excluded or {})
    usable = [a for a in attempts if a.mpn not in ruled_out]

    for candidate in usable:
        if candidate.clear:
            margin = f", with {candidate.margin} to spare" if candidate.margin else ""
            return Proposal(
                mpn=candidate.mpn,
                roles=("engineering",),
                detail=f"Clears every check on this board{margin}.",
            )

    for candidate in usable:
        if candidate.gated:
            gate = candidate.gates[0]
            return Proposal(
                mpn=candidate.mpn,
                roles=tuple(decision_roles(gate)),
                gate_rule=gate.rule,
                detail=gate.detail,
            )

    return None


def narrate(attempt_made: Attempt) -> str:
    """One sentence about one candidate, in the engine's own words.

    Deterministic, like every other sentence this product puts on screen. The verdict's
    `detail` is written by the rule that produced it and carries its arithmetic, so quoting
    it is both the shortest and the most defensible thing to say.
    """
    if attempt_made.clear:
        margin = f" — {attempt_made.margin} to spare" if attempt_made.margin else ""
        return f"{attempt_made.mpn} clears every check on this board{margin}."
    first = attempt_made.blocking[0]
    if attempt_made.gated:
        return f"{attempt_made.mpn} is electrically fine here. {first.detail}"
    return f"{attempt_made.mpn} — {first.detail}"


# ── where candidates come from ────────────────────────────────────────────────


@dataclass(frozen=True)
class Candidate:
    """A part worth trying, and why it is on the list.

    The origin is not decoration. "The manufacturer recommended this" and "we already ship
    this" are different claims with different costs behind them — roughly $1,281 to resolve
    with a part that is already approved against $15,656 to qualify one from scratch — and a
    reader deciding between two candidates is entitled to know which they are looking at.
    """

    part: PartSpec
    origin: str


NOTICE_ORIGIN = "recommended by the notice"
APPROVED_ORIGIN = "already on the approved manufacturer list"
CATALOGUE_ORIGIN = "found in the distributor's catalogue"
NAMED_ORIGIN = "named by you"


async def candidates_for(
    *,
    retiring: PartSpec,
    resolve,
    notice_replacement: str | None = None,
    approved: Sequence[str] = (),
    search=None,
    named: Sequence[str] = (),
) -> tuple[Candidate, ...]:
    """What to try, in the order to try it, and why each one is on the list.

    **The manufacturer's own recommendation first.** It is the answer the notice puts in
    front of everybody, it is what a reader asks about if it is missing, and on a board it
    does not suit, watching it fail is the point.

    **Then the parts this company has already qualified**, because that is the cheap
    resolution: roughly $1,281 against $15,656 to qualify one from scratch. A tool that
    proposed a new part while an approved one would have done is a tool that costs its owner
    twelve times more than it had to.

    **Then the distributor's catalogue.** This is how a part nobody here has ever bought gets
    considered at all, and it is the only leg that can produce the interesting answer — a
    part that holds a board no approved part holds, which is then quality's decision rather
    than engineering's.

    **Anything a person named is tried last**, and is an override rather than part of the
    flow: the point is that nobody should have to type a part number.

    Only the approved list and the catalogue are filtered by category. A part the
    manufacturer named, or one a person typed, is a deliberate choice, and refusing it
    because our category strings disagree would be the tool overruling them.

    The part being retired is never a candidate to replace itself.
    """
    seen: set[str] = {retiring.mpn.casefold()}
    found: list[Candidate] = []

    def keep(part: PartSpec | None, origin: str, *, same_category: bool) -> None:
        if part is None or part.mpn.casefold() in seen:
            return
        if same_category and (part.category or "") != (retiring.category or ""):
            return
        seen.add(part.mpn.casefold())
        found.append(Candidate(part=part, origin=origin))

    async def consider(mpn: str | None, origin: str, *, same_category: bool) -> None:
        if not mpn or mpn.casefold() in seen:
            return
        keep(await resolve(mpn), origin, same_category=same_category)

    await consider(notice_replacement, NOTICE_ORIGIN, same_category=False)
    for mpn in approved:
        await consider(mpn, APPROVED_ORIGIN, same_category=True)
    if search is not None:
        for part in await search(retiring):
            keep(part, CATALOGUE_ORIGIN, same_category=True)
    for mpn in named:
        await consider(mpn, NAMED_ORIGIN, same_category=False)
    return tuple(found)
