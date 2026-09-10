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

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .engine import rules
from .engine.models import Board, PartSpec, Verdict
from .matrix import substitute
from .roles import ANSWERABLE_RULES, decision_roles, desks_that_must_sign, roles_for_rule

GATE_RULES = ANSWERABLE_RULES
"""Rules a department owns rather than physics. A failure here is a decision, not a wall.

Defined in `roles.py`, beside the table that says which desk owns each one. Kept under this
name because `Attempt.gates` and `Attempt.physical` read better against it.
"""


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
    def accepted(self) -> tuple[Verdict, ...]:
        """Failures a responsible desk accepted; eligible, but never a pass."""
        return tuple(
            verdict
            for verdict in self.verdicts
            if verdict.status == "failed" and verdict.accepted
        )

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
    needs. A rule here means the part works and one of the desks below has something to
    accept rather than merely approve."""

    @property
    def owner_of_the_gate(self) -> tuple[str, ...]:
        """The desk being asked to accept a failure, as opposed to the desks approving.

        Empty when nothing failed, which is the ordinary case and reads as such.
        """
        return roles_for_rule(self.gate_rule) if self.gate_rule else ()

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


def accepted_verdicts(
    verdicts: Sequence[Verdict],
    *,
    waivers: Sequence[Mapping[str, Any]],
    parts: Mapping[str, str | None],
    revision: str | None,
) -> tuple[Verdict, ...]:
    """Keep an accepted EOL failure visible, but stop routing it as unfinished work.

    A waiver is only for the failing rule the owning desk accepted, on the candidate it
    saw, under the released revision it signed. It is deliberately an attribute of a
    failed verdict, never a new pass label or a deletion of the evidence.
    """
    if not waivers:
        return tuple(verdicts)

    def accepted(verdict: Verdict) -> bool:
        if verdict.status != "failed":
            return False
        owners = set(roles_for_rule(verdict.rule))
        candidate_mpn = parts.get(verdict.subject)
        return any(
            waiver.get("rule") == verdict.rule
            and waiver.get("subject") == verdict.subject
            and isinstance(candidate_mpn, str)
            and isinstance(waiver.get("mpn"), str)
            and waiver["mpn"].strip().upper() == candidate_mpn.strip().upper()
            and waiver.get("revision") == revision
            and owners.intersection(waiver.get("roles") or ())
            for waiver in waivers
        )

    return tuple(
        replace(verdict, accepted=True) if accepted(verdict) else verdict
        for verdict in verdicts
    )


def attempt(
    board: Board,
    slot_id: str,
    candidate: PartSpec,
    *,
    waivers: Sequence[Mapping[str, Any]] = (),
    revision: str | None = None,
) -> Attempt:
    """Place the candidate and re-check the whole board.

    The whole board, not the slot: a regulator moves the rail it makes, and a substitution
    that only re-checked its own position would clear a part that browns out everything
    downstream of it.
    """
    substituted = substitute(board, slot_id, candidate)
    placed = substituted.slots[slot_id]
    # Read the part back off the board rather than trusting what was handed in, exactly as
    # the matrix does: the attempt reports what was actually evaluated.
    parts = {
        subject: slot.part.mpn if slot.part is not None else None
        for subject, slot in substituted.slots.items()
    }
    return Attempt(
        candidate=placed.part,
        verdicts=accepted_verdicts(
            rules.evaluate(substituted), waivers=waivers, parts=parts, revision=revision
        ),
    )


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
            accepted = candidate.accepted
            detail = (
                f"{accepted[0].rule.replace('_', ' ')} failed and accepted — {accepted[0].detail}"
                if accepted
                else f"Clears every check on this board{margin}."
            )
            return Proposal(
                mpn=candidate.mpn,
                # Every department that examined this change, not engineering by default.
                # The standard the scenario is held to is the field's own: *any change to a
                # released design must be approved before implementation, no exceptions*.
                # A substitution affects design electrically, procurement commercially,
                # production on the line and quality on the approved list, and a real change
                # board is signed by all of them whether or not anything failed. Hardcoding
                # engineering here meant a desk was consulted only when the answer was a
                # compromise, and never when it was good.
                roles=desks_that_must_sign(candidate.verdicts),
                detail=detail,
            )

    for candidate in usable:
        if candidate.gated:
            gate = candidate.gates[0]
            return Proposal(
                mpn=candidate.mpn,
                # The same desks, and one of them has something to accept rather than
                # merely approve. `gate_rule` says which; `decision_roles(gate)` is the
                # owner and is always among these, because a failed verdict is one the
                # engine looked at.
                roles=desks_that_must_sign(candidate.verdicts),
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
    if attempt_made.accepted:
        verdict = attempt_made.accepted[0]
        return (
            f"{attempt_made.mpn} has {verdict.rule.replace('_', ' ')} failed and accepted "
            f"— {verdict.detail}"
        )
    if attempt_made.clear:
        margin = f" — {attempt_made.margin} to spare" if attempt_made.margin else ""
        return f"{attempt_made.mpn} clears every check on this board{margin}."
    first = attempt_made.blocking[0]
    if attempt_made.gated:
        # True of all five answerable rules: none of them is an electrical failure. A
        # footprint gate reads correctly too — the circuit is fine and the land pattern is
        # not, which is two sentences that agree.
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


@dataclass(frozen=True)
class SkippedCandidate:
    """A candidate the review could name, but could not honestly check."""

    mpn: str
    reason: str


async def candidates_for(
    *,
    retiring: PartSpec,
    resolve,
    notice_replacement: str | None = None,
    worked: Mapping[str, str] | None = None,
    approved: Sequence[str] = (),
    search=None,
    named: Sequence[str] = (),
    manufacturers: Mapping[str, str] | None = None,
    skipped: list[SkippedCandidate] | None = None,
) -> tuple[Candidate, ...]:
    """What to try, in the order to try it, and why each one is on the list.

    **The manufacturer's own recommendation first.** It is the answer the notice puts in
    front of everybody, it is what a reader asks about if it is missing, and on a board it
    does not suit, watching it fail is the point.

    **Then the parts that already resolved this retirement elsewhere**, because they are
    the cheapest known answer on this board.

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

    **Only the approved list is filtered by category.** It is an arbitrary list of the
    company's part numbers, resolved through the same path, so the comparison is sound and an
    approved list of a hundred parts would otherwise offer capacitors as substitutes for a
    regulator. The catalogue was constrained by the search itself; the notice's recommendation
    and a typed part are deliberate choices, and refusing either because our category strings
    disagree would be the tool overruling a person.

    **Every part is asked for by number and manufacturer where the company records one.**
    An MPN alone does not name a part: JLCPCB lists `TLV1117LV33DCYR` under Texas
    Instruments and under JSMSEMI, whose listing states a 12 V supply ceiling where TI's
    states 5.5 V, and only TI's fails the 12 V cabinet controller. Asking by number took
    whichever listing came back first, so a part this company had qualified as TI's was
    evaluated, proposed and written onto a bill under a clone's name. `manufacturers` is
    what the company itself records — its own bills first, then its approved list — and it
    is an improvement on the question rather than a precondition for asking it: a part
    nobody here has bought is still asked for by number.

    The part being retired is never a candidate to replace itself.
    """
    recorded = {mpn.upper(): maker for mpn, maker in (manufacturers or {}).items()}
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
        try:
            part = await resolve(mpn, recorded.get(mpn.upper()))
        except Exception as error:
            # `Ambiguous` belongs to the distributor-facing API, rather than this domain
            # module. Recognise it by contract without importing that API and creating a
            # core-to-HTTP dependency. Other failures still belong to the caller.
            if type(error).__name__ != "Ambiguous":
                raise
            if skipped is not None:
                skipped.append(SkippedCandidate(mpn=mpn, reason=str(error)))
            return
        if part is None:
            if skipped is not None:
                skipped.append(SkippedCandidate(mpn=mpn, reason="could not be sourced"))
            return
        keep(part, origin, same_category=same_category)

    await consider(notice_replacement, NOTICE_ORIGIN, same_category=False)
    for mpn, line_name in (worked or {}).items():
        await consider(mpn, f"resolved this on the {line_name}", same_category=False)
    for mpn in approved:
        await consider(mpn, APPROVED_ORIGIN, same_category=True)
    if search is not None:
        # **Not category-filtered.** The search was already constrained — the kind of part in
        # the query, the package in the constraint — and re-filtering its results against the
        # retiring part's category string compares two taxonomies that only agree by luck.
        # JLCPCB says "Voltage Regulators - Linear, Low Drop Out (LDO) Regulators" where
        # another source says "LDO Regulator", and an exact match silently empties this leg.
        # A part of the wrong kind that survives the search is caught where everything else
        # is caught: the engine evaluates it and it fails, visibly, as a rejected alternative.
        for part in await search(retiring):
            keep(part, CATALOGUE_ORIGIN, same_category=False)
    for mpn in named:
        await consider(mpn, NAMED_ORIGIN, same_category=False)
    return tuple(found)
