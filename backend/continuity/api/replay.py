"""A finished review, read back out of what it recorded.

## Why this exists

A design run is replayable and a review was not. Every frame a design run emits is written
to `run_events`, so reopening a product line's design shows the whole trace; a review
streamed its reasoning to whoever was watching and kept only its conclusions. Reopening the
product line afterwards showed *"already decided here"*, a part number and a date — the
answer with none of the working.

That asymmetry is the wrong way round for this product. The claim is that a person can see
why a substitution was chosen, and the place they will look is the product it changed.

## Nothing new is stored

`decisions.document` already holds every candidate the run tried, the sentence that killed
each one, and the winner's verdicts — `api/review._run_line` writes it so that applying a
decision does not have to source the part again. This reassembles the trace from that, in
the frames the client already renders.

**What the run said is stored with it.** Each candidate is narrated with where it came from —
*"recommended by the notice"*, *"found in the distributor's catalogue"* — and the attempt
carries that origin beside its manufacturer and package, so a replayed line reads what the
live one read. A decision written before 11 September carries no origin, and those replay
with the bare part number rather than a source invented for them.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..roles import roles_for_rule


def _said(text: str, line_id: str | None = None) -> dict[str, Any]:
    """One narration line. `line_id` says whose it is, and its absence is a statement.

    **The notice is stated once and the boards are stated each.** The two opening lines —
    what is retiring and what the notice recommends — are true of every affected product, and
    the live run says them above the lanes rather than three times inside them. The lines
    that follow name a board, and belong to it. A company view replaying three decisions has
    to be able to tell those apart, and guessing from position would break the moment the
    preamble gained a line.
    """
    frame: dict[str, Any] = {"type": "reasoning", "text": text, "slot": None}
    if line_id is not None:
        frame["line_id"] = line_id
    return frame


def _check(verdict: Mapping[str, Any], line_id: str | None = None) -> dict[str, Any]:
    rule = verdict.get("rule", "")
    frame = {
        "type": "check",
        "rule": rule,
        "scope": verdict.get("scope"),
        "status": verdict.get("status", "evidence_missing"),
        "detail": verdict.get("detail", ""),
        "margin": verdict.get("margin"),
        "accepted": bool(verdict.get("accepted", False)),
        # A lookup rather than a stored field, so a decision recorded before departments
        # existed replays with them and cannot disagree with the live stream.
        "departments": list(roles_for_rule(rule)),
    }
    if line_id is not None:
        frame["line_id"] = line_id
    # `frame` is a dict of mixed value types; the literal above is the contract.
    return frame


def _trying(attempt: Mapping[str, Any]) -> str:
    """`Trying LD1117-3.3 — found in the distributor's catalogue.`

    The live run says where each candidate came from, and the difference it names is not
    decoration: *recommended by the notice* and *found in the distributor's catalogue* are
    different claims about the same part number, and a desk weighs them differently when it
    decides whether to sign. The attempt records the origin now, so the replay can repeat it.

    A decision stored before it did keeps the bare part number. A record that does not say
    where a candidate came from is not a record to invent a source for.
    """
    origin = attempt.get("origin")
    if isinstance(origin, str) and origin.strip():
        return f"Trying {attempt.get('mpn')} — {origin.strip()}."
    return f"Trying {attempt.get('mpn')}."


def frames_from(notice: Mapping[str, Any], decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The trace a finished review would show, from the decision it left behind.

    Ordered as the run itself ordered it: what is retiring, what the notice recommends,
    where the part sits, each candidate with the sentence that settled it, then the winner's
    verdicts. A reader following it reaches the proposal the same way the run did.
    """
    document = decision.get("document") or {}
    line_name = document.get("line_name") or "this product line"
    line_id = decision.get("line_id")
    attempts: Sequence[Mapping[str, Any]] = document.get("attempts") or []
    proposal = decision.get("proposal")

    frames: list[dict[str, Any]] = [_said(f"{notice['mpn']} is going end of life.")]
    if notice.get("replacement_mpn"):
        frames.append(
            _said(f"The notice recommends {notice['replacement_mpn']}. Trying that first.")
        )
    slot = (decision.get("slot_id") or "").upper()
    if slot:
        frames.append(_said(f"{notice['mpn']} sits at {slot} on the {line_name}.", line_id))

    for attempt in attempts:
        mpn = attempt.get("mpn")
        if not mpn or mpn == notice["mpn"]:
            # The incumbent is in `attempts` as the baseline the others are measured
            # against, and it was never a candidate. Narrating it as one would say the run
            # considered replacing the part with itself.
            continue
        frames.append(_said(_trying(attempt), line_id))
        if attempt.get("narration"):
            frames.append(_said(attempt["narration"], line_id))

    chosen = next((a for a in attempts if a.get("mpn") == proposal), None)
    for verdict in (chosen or {}).get("verdicts") or []:
        frames.append(_check(verdict, line_id))

    # The run's own ending, in the frame the reducer already knows. Without it a replayed
    # review reached `done` with no proposal, and a finished run that had chosen a part and
    # had it approved rendered as **NO VIABLE PART** — the loudest possible way to be wrong
    # about a board that shipped.
    ending = {
        "type": "line_done",
        "line_name": line_name,
        "proposal": proposal,
        "decision_id": decision.get("id"),
        "reason": decision.get("detail") or "",
        "conditional": bool(decision.get("gate_rule")),
        "roles": list(decision.get("roles") or ()),
    }
    if line_id is not None:
        ending["line_id"] = line_id
    frames.append(ending)
    return frames
