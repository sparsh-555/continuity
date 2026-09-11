"""A finished review, read back out of what it recorded.

Replay is the default mode of the demonstration, so a sentence the live run says and the
replay cannot is a sentence a judge does not hear. These are the frames that make up a
line's trace, assembled from a decision and nothing else.
"""

from __future__ import annotations

from typing import Any

from continuity.api import replay

NOTICE = {"mpn": "AMS1117-3.3", "replacement_mpn": "NCP1117ST33T3G"}


def _decision(**attempt: Any) -> dict[str, Any]:
    return {
        "id": "decision-1",
        "line_id": "line-1",
        "slot_id": "u1",
        "proposal": attempt.get("mpn"),
        "detail": "",
        "roles": ["engineering"],
        "document": {"line_name": "Sensor node", "attempts": [attempt]},
    }


def _texts(frames: list[dict[str, Any]]) -> list[str]:
    return [frame["text"] for frame in frames if frame.get("type") == "reasoning"]


def test_a_replayed_candidate_says_where_it_came_from():
    """The live run says it, and it is not decoration.

    *Recommended by the notice* and *found in the distributor's catalogue* are different
    claims about the same part number, and the difference is what a desk weighs when it
    decides whether to sign.
    """
    frames = replay.frames_from(
        NOTICE, _decision(mpn="LD1117-3.3", origin="found in the distributor's catalogue")
    )

    assert "Trying LD1117-3.3 — found in the distributor's catalogue." in _texts(frames)


def test_a_decision_stored_before_the_origin_was_recorded_still_replays():
    """Every change request written before 11 September carries no origin, and inventing one
    for them is what this module's own comment refused to do. The bare part number is the
    honest reading of a record that does not say."""
    frames = replay.frames_from(NOTICE, _decision(mpn="LD1117-3.3"))

    said = _texts(frames)
    assert "Trying LD1117-3.3." in said
    assert not [text for text in said if text.startswith("Trying") and "—" in text]


def test_an_empty_origin_is_not_a_statement():
    """A blank field is a field nobody filled in, not a provenance."""
    frames = replay.frames_from(NOTICE, _decision(mpn="LD1117-3.3", origin="   "))

    assert "Trying LD1117-3.3." in _texts(frames)


def test_the_incumbent_is_still_not_narrated_as_a_candidate():
    """It is in `attempts` as the baseline everything else is measured against, and
    narrating it as a candidate would say the run considered replacing a part with itself."""
    decision = _decision(mpn="AMS1117-3.3", origin="on the board today")
    decision["document"]["attempts"] = [
        {"mpn": "AMS1117-3.3", "origin": "on the board today"},
        {"mpn": "TLV1117LV33DCYR", "origin": "found in the distributor's catalogue"},
    ]

    said = _texts(replay.frames_from(NOTICE, decision))

    assert "Trying TLV1117LV33DCYR — found in the distributor's catalogue." in said
    assert not [text for text in said if text.startswith("Trying AMS1117")]
