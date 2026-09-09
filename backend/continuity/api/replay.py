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

**One thing the run said cannot be reconstructed, and is not invented.** Each candidate was
narrated with where it came from — *"recommended by the notice"*, *"found in the
distributor's catalogue"* — and only the manufacturer and package are stored per attempt. So
a replayed line reads *"Trying LD1117-3.3."* where the live one read *"Trying LD1117-3.3 —
found in the distributor's catalogue."* Adding an origin here would mean guessing one.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _said(text: str) -> dict[str, Any]:
    return {"type": "reasoning", "text": text, "slot": None}


def _check(verdict: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "check",
        "rule": verdict.get("rule", ""),
        "scope": verdict.get("scope"),
        "status": verdict.get("status", "not_assessed"),
        "detail": verdict.get("detail", ""),
        "margin": verdict.get("margin"),
        "accepted": bool(verdict.get("accepted", False)),
    }


def frames_from(notice: Mapping[str, Any], decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The trace a finished review would show, from the decision it left behind.

    Ordered as the run itself ordered it: what is retiring, what the notice recommends,
    where the part sits, each candidate with the sentence that settled it, then the winner's
    verdicts. A reader following it reaches the proposal the same way the run did.
    """
    document = decision.get("document") or {}
    line_name = document.get("line_name") or "this product line"
    attempts: Sequence[Mapping[str, Any]] = document.get("attempts") or []
    proposal = decision.get("proposal")

    frames: list[dict[str, Any]] = [_said(f"{notice['mpn']} is going end of life.")]
    if notice.get("replacement_mpn"):
        frames.append(
            _said(f"The notice recommends {notice['replacement_mpn']}. Trying that first.")
        )
    slot = (decision.get("slot_id") or "").upper()
    if slot:
        frames.append(_said(f"{notice['mpn']} sits at {slot} on the {line_name}."))

    for attempt in attempts:
        mpn = attempt.get("mpn")
        if not mpn or mpn == notice["mpn"]:
            # The incumbent is in `attempts` as the baseline the others are measured
            # against, and it was never a candidate. Narrating it as one would say the run
            # considered replacing the part with itself.
            continue
        frames.append(_said(f"Trying {mpn}."))
        if attempt.get("narration"):
            frames.append(_said(attempt["narration"]))

    chosen = next((a for a in attempts if a.get("mpn") == proposal), None)
    for verdict in (chosen or {}).get("verdicts") or []:
        frames.append(_check(verdict))

    # The run's own ending, in the frame the reducer already knows. Without it a replayed
    # review reached `done` with no proposal, and a finished run that had chosen a part and
    # had it approved rendered as **NO VIABLE PART** — the loudest possible way to be wrong
    # about a board that shipped.
    frames.append(
        {
            "type": "line_done",
            "line_name": line_name,
            "proposal": proposal,
            "decision_id": decision.get("id"),
            "reason": decision.get("detail") or "",
            "conditional": bool(decision.get("gate_rule")),
            "roles": list(decision.get("roles") or ()),
        }
    )
    return frames
