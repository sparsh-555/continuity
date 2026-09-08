"""What actually gets sent to a person: one change request per affected product line.

Everything built so far converges here. A notice named a part; exposure found the products
carrying it; the matrix checked every candidate against each product's own conditions; the
gates said which of those are qualified and who may approve them. A change request is that
work written down for the person who has to sign it — **per line**, because the answer
differs per line and a single company-wide recommendation is the thing this product exists
to replace.

## Why the rejected alternatives are in the document

A proposal on its own asks to be trusted. A proposal that says *we also tried these three
and here is the sentence that killed each* asks to be checked, which is the only kind of
recommendation an engineer can act on quickly. It is also what stops the same part being
re-proposed on the next notice.

## Why "not assessed" is a field and not a footnote

The engine's coverage boundaries — stability, EMC, signal integrity — are real, and a
change request that omitted them would read as a clean bill of health for questions nobody
asked. Naming them is the difference between a document that can be relied on and one that
merely looks complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .engine.models import Verdict
from .matrix import Cell, Matrix
from .roles import DEFAULT_DECISION_ROLES, decision_roles

QUALIFIED_PART_COST = 1_281.0
"""Typical cost of resolving an end-of-life with a part already on the approved list.

US Department of Defense diminishing-manufacturing-sources figures, as cited in
`docs/world-finals/EOL-RESEARCH.md`. An order-of-magnitude planning number rather than a
quotation, and the document says so wherever it prints one."""

UNQUALIFIED_PART_COST = 15_656.0
"""The same resolution using a substitute qualified from scratch — roughly twelve times as
much. The gap is the entire business argument for keeping an approved list and a memory of
what was decided before."""


@dataclass(frozen=True)
class Alternative:
    """A candidate that was considered, and what happened to it."""

    mpn: str
    rejected_because: str | None
    """The verdict that killed it, verbatim. `None` means it survived and was simply not
    the one chosen — which is worth recording too, because a viable second choice is what
    the next notice starts from."""

    @property
    def viable(self) -> bool:
        return self.rejected_because is None


@dataclass(frozen=True)
class Cost:
    """What the change costs, split the way somebody approving it needs to see it."""

    unit_delta: float | None
    """Per-unit price difference against the part fitted today. `None` when either price
    is unpublished, which is not zero and must not be shown as zero."""

    annual_volume: int | None
    recurring_annual: float | None
    """`unit_delta × annual_volume`, or `None` when the line has not stated a volume. An
    assumed volume would make a plausible number out of nothing."""

    one_time: float
    one_time_basis: str

    def to_json(self) -> dict[str, Any]:
        return {
            "unit_delta": self.unit_delta,
            "annual_volume": self.annual_volume,
            "recurring_annual": self.recurring_annual,
            "one_time": self.one_time,
            "one_time_basis": self.one_time_basis,
        }


@dataclass(frozen=True)
class ChangeRequest:
    """One product line's answer to one notice."""

    line_id: str
    line_name: str
    revision: str | None
    baseline_mpn: str | None

    notice_mpn: str
    notice_id: str | None

    proposal: str | None
    """The candidate recommended for *this* line, or `None` when none survived it. `None`
    is a result, not a failure to produce one: a line with no viable substitute is the
    finding, and burying it would be the worst thing this document could do."""

    proposal_detail: str
    alternatives: tuple[Alternative, ...]
    evidence: tuple[Verdict, ...]

    not_assessed: tuple[str, ...]
    """Rules the engine declares it does not answer — stability, EMC, signal integrity."""

    no_evidence: tuple[str, ...]
    """Rules it tried to answer and could not, which is a different admission and belongs
    beside the first rather than folded into it."""

    cost: Cost
    approvals_required: tuple[str, ...]

    @property
    def viable(self) -> bool:
        return self.proposal is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "line_name": self.line_name,
            "revision": self.revision,
            "baseline_mpn": self.baseline_mpn,
            "notice_mpn": self.notice_mpn,
            "notice_id": self.notice_id,
            "proposal": self.proposal,
            "proposal_detail": self.proposal_detail,
            "alternatives": [
                {"mpn": a.mpn, "rejected_because": a.rejected_because}
                for a in self.alternatives
            ],
            "evidence": [
                {
                    "rule": v.rule,
                    "scope": v.scope,
                    "status": v.status,
                    "detail": v.detail,
                    "margin": v.margin,
                }
                for v in self.evidence
            ],
            "not_assessed": list(self.not_assessed),
            "no_evidence": list(self.no_evidence),
            "cost": self.cost.to_json(),
            "approvals_required": list(self.approvals_required),
        }


def _cost_for(cell: Cell | None, baseline: Cell | None, volume: int | None, qualified: bool) -> Cost:
    if cell is None:
        # Nothing was proposed, so there is nothing to cost. Printing a qualification
        # figure here invoices the reader for a part that does not exist — which the demo
        # did, quoting $15,656 to qualify nobody's candidate.
        return Cost(
            unit_delta=None,
            annual_volume=volume,
            recurring_annual=None,
            one_time=0.0,
            one_time_basis="no candidate to cost",
        )

    basis = (
        "already on the approved manufacturer list"
        if qualified
        else "qualification from scratch"
    )
    one_time = QUALIFIED_PART_COST if qualified else UNQUALIFIED_PART_COST

    new_price = cell.candidate.unit_price if cell is not None else None
    old_price = baseline.candidate.unit_price if baseline is not None else None
    delta = (
        round(new_price - old_price, 4)
        if new_price is not None and old_price is not None
        else None
    )
    recurring = round(delta * volume, 2) if delta is not None and volume else None
    return Cost(
        unit_delta=delta,
        annual_volume=volume,
        recurring_annual=recurring,
        one_time=one_time,
        one_time_basis=basis,
    )


def _headline(cell: Cell) -> str:
    """The one sentence that decided this cell, for a document somebody skims."""
    failures = cell.failures
    if failures:
        return failures[0].detail
    if cell.margin:
        return f"Clears every check on this board, with {cell.margin} to spare."
    return "Clears every check on this board."


def for_line(
    matrix: Matrix,
    line_id: str,
    *,
    notice_mpn: str,
    notice_id: str | None = None,
    revision: str | None = None,
    annual_volume: int | None = None,
    approved_mpns: Sequence[str] | None = None,
    prefer: Sequence[str] = (),
    excluded: Mapping[str, str] | None = None,
) -> ChangeRequest:
    """One line's change request, out of the matrix that was already computed.

    The proposal is chosen from the candidates that actually survive **this** line, in the
    caller's stated order of preference — a part already on the approved list saves roughly
    twelve times its qualification cost, so preference is a real input rather than a tie
    break. A line where nothing survives yields a request with no proposal, which is the
    finding rather than an absence of one.

    `excluded` is what this board already ruled out, mpn to the reason. Such a part is
    never proposed again, and still appears among the alternatives carrying that reason —
    dropping it silently would make the document look as though it had never been
    considered, which is exactly the question its reader would ask next.
    """
    cells = [cell for cell in matrix.cells if cell.line_id == line_id]
    if not cells:
        raise KeyError(f"the matrix holds no cells for {line_id!r}")

    baseline = next((cell for cell in cells if cell.is_incumbent), None)
    candidates = [cell for cell in cells if not cell.is_incumbent]

    ruled_out = dict(excluded or {})
    order = {mpn: index for index, mpn in enumerate(prefer)}
    viable = sorted(
        (cell for cell in candidates if cell.ok and cell.candidate.mpn not in ruled_out),
        key=lambda cell: (order.get(cell.candidate.mpn, len(order)), cell.candidate.mpn),
    )
    chosen = viable[0] if viable else None

    alternatives = tuple(
        Alternative(
            mpn=cell.candidate.mpn,
            rejected_because=(
                cell.failures[0].detail
                if cell.failures
                else ruled_out.get(cell.candidate.mpn)
            ),
        )
        for cell in candidates
        if chosen is None or cell.candidate.mpn != chosen.candidate.mpn
    )

    source = chosen if chosen is not None else baseline
    verdicts = source.verdicts if source is not None else ()
    approved = {mpn.upper() for mpn in (approved_mpns or ())}

    return ChangeRequest(
        line_id=line_id,
        line_name=cells[0].line_name,
        revision=revision,
        baseline_mpn=baseline.candidate.mpn if baseline is not None else None,
        notice_mpn=notice_mpn,
        notice_id=notice_id,
        proposal=chosen.candidate.mpn if chosen is not None else None,
        proposal_detail=(
            _headline(chosen)
            if chosen is not None
            else "No candidate offered clears this product line's own operating conditions."
        ),
        alternatives=alternatives,
        # Only what the proposal rests on. A document that reprinted every satisfied check
        # would bury the three that decided it.
        evidence=tuple(
            v for v in verdicts if v.status == "failed" or (v.status == "satisfied" and v.margin)
        ),
        not_assessed=tuple(
            sorted({v.rule for v in verdicts if v.status == "not_assessed"})
        ),
        no_evidence=tuple(
            sorted({v.rule for v in verdicts if v.status == "evidence_missing"})
        ),
        cost=_cost_for(
            chosen,
            baseline,
            annual_volume,
            qualified=chosen is not None and chosen.candidate.mpn.upper() in approved,
        ),
        approvals_required=_approvals_for(chosen, verdicts),
    )


def _approvals_for(chosen: Cell | None, verdicts: Sequence[Verdict]) -> tuple[str, ...]:
    """Who has to sign this request.

    Every desk that owns a failing rule — and **engineering when nothing failed at all**,
    because a change to a released design is approved before it is implemented rather than
    after. A request proposing a part and claiming nobody needs to sign it is not a lighter
    process, it is an unauthorised change. A request with no proposal asks for nothing and
    needs nobody: it is a finding, not a change.
    """
    owed = tuple(
        dict.fromkeys(
            role for v in verdicts if v.status == "failed" for role in decision_roles(v)
        )
    )
    if owed or chosen is None:
        return owed
    return DEFAULT_DECISION_ROLES


def for_every_line(
    matrix: Matrix,
    *,
    notice_mpn: str,
    lines: Mapping[str, Mapping[str, Any]],
    excluded: Mapping[str, Mapping[str, str]] | None = None,
    **shared: Any,
) -> tuple[ChangeRequest, ...]:
    """One request per affected line, in the matrix's own row order.

    Per line rather than one document for the company, because the answer differs per line —
    which is the finding a single manufacturer-wide recommendation cannot express, and the
    reason any of this exists.
    """
    return tuple(
        for_line(
            matrix,
            line_id,
            notice_mpn=notice_mpn,
            excluded=(excluded or {}).get(line_id),
            **{**shared, **dict(lines.get(line_id, {}))},
        )
        for line_id in matrix.lines
    )
