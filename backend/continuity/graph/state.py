"""The single checkpointed object the graph carries. Design doc §8."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from ..engine.models import Rail, Requirements, Slot, Verdict


def _replace(_old: Any, new: Any) -> Any:
    """Last write wins. Nodes return whole collections, not deltas."""
    return new


class DesignState(TypedDict, total=False):
    prompt: str

    profile: dict | None
    """The product line's stored operating conditions, as `OperatingProfile.to_json()`.

    A brief describes a board somebody wants; a profile describes the one that already
    ships. When a run belongs to a line that has recorded its ambient, that ambient is a
    measured property of the product and beats anything inferred from a sentence — so
    `parse_requirements` lays it over what the planner read, and says on the trace that
    it did.
    """

    approved: Any
    """The organisation's AML and AVL, as `engine.models.ApprovedLists`.

    Loaded once when the run starts rather than per node: the gates ask whether a part is
    on a list, and a list that changed underneath a run would let two verdicts in the same
    trace disagree with each other about the same part."""

    rationale: str | None
    """Why the last decision was made, in the answerer's own words. See `ResumeRequest`."""

    answered_by: dict | None
    """Who answered the run's last open decision — id, email and roles.

    Set by `/resume` alongside the answer itself, because only the request that carried the
    answer knows who gave it: the graph is resumed by whichever process serves the call,
    and a checkpoint written yesterday cannot say who is at the keyboard today.
    """

    revision: str | None
    """The product line's revision, as item 10b stores it against the line.

    Carried so a waiver can be scoped to it: an approval given under one set of operating
    conditions is not an approval under the next. `None` for a scratch run, which has no
    revision to change, so those behave exactly as they did."""

    requirements: Requirements

    plan: Any
    """The planner's board layout: slots, rails, search queries, bus links."""

    slots: Annotated[dict[str, Slot], _replace]
    rails: Annotated[dict[str, Rail], _replace]

    pending: Annotated[list[str], _replace]
    """Slots with no part yet, in placement order. Empty means the board is complete."""

    current: str | None
    """The slot being placed or repaired."""

    revalidate_all: bool
    """Set by a node that changed something board-wide. `validate` then reports every
    verdict rather than only the slot it just touched, and clears the flag."""

    candidates: Annotated[dict[str, list], _replace]
    """Raw search hits per slot. Only the selected one is ever normalised."""

    cursor: Annotated[dict[str, int], _replace]
    """Which candidate is currently in each slot."""

    constraint: dict | None
    """Set by `review`, consumed by `apply`. A constraint means re-search rather than
    advance — the next part in the old list is not an answer to a topology change."""

    repair_action: str | None
    """The reviewed action consumed by `apply`; needed to distinguish `add_part` from a
    category constraint on an ordinary replacement."""

    source_next: bool
    """An added slot must be filled before the graph may revalidate the board."""

    verdicts: Annotated[list[Verdict], _replace]
    conflicts_resolved: int
    added_slots: int
    """How many late slots this run has declared. Bounded by `policy.MAX_ADDED_SLOTS`."""
    started_at: float

    accepted: Annotated[list, _replace]
    """`(rule, subject, mpn, revision)` tuples a person waived.

    Scoped to the *candidate* and the *revision*, not just to `(rule, subject)`. A waiver
    on the rule alone silently covered the next regulator a repair dropped into that slot
    — a part nobody looked at, carrying a temperature nobody approved. A repair changes
    the mpn and the waiver evaporates, which is the behaviour an approval should have.

    `validate` marks these `accepted` rather than relabelling them: a waiver is not a pass
    and not a gap in the evidence, so the finding stays on screen with its evidence and
    its status, and only stops blocking the run."""

    stopped: bool
    """The user chose to stop rather than accept. Ends the run at `finalize`."""

    escalation: str | None
    """Set when the fence closed and the user has to decide. Drives a `question`."""

    supply_attempts: int
    """How many times `clarify` has been answered without resolving the supply.

    `clarify` cannot tell "first ask" from "re-ask" by looking at `input_source`: it is
    `UNRESOLVED` in both cases, because an unrecognised answer is exactly why we are back
    here. Without a counter the dialog returns identical and the Send button looks dead."""

    guidance: str | None
    """What the user typed at an escalation, for the reviewer's next attempt.

    Anything that is not one of the offered options is guidance, never a waiver. The
    two used to be the same branch, so typed reasoning was filed as consent."""

    replan_source: str | None
    """A user-named replacement input supply, consumed by `replan` before validation."""

    unfilled: Annotated[list[str], _replace]
    """Slots whose search returned nothing.

    Kept separately from `pending` because they are neither waiting nor placed: the run
    can finish with one, but the board is short a part and `finalize` has to say so.
    Without this they left `pending` and vanished from every count."""
