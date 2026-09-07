"""The sweep harness reads the same vocabulary the engine writes.

`brief_sweep` exists to find defects on boards nobody has run before, and its two headline
detectors — a run that finished with a failing check nothing acted on, and one whose repair
was never re-stated — both filtered `status == "fail"`. That label was retired with the
three-state vocabulary, so both returned `[]` on every run, silently, for as long as the
five coverage labels have existed.

A tool that reports nothing is indistinguishable from a clean result. These tests compare
the spellings the tool looks for against `CheckStatus` itself, so the next vocabulary
change fails here rather than quietly switching the harness off.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from continuity.engine.models import CheckStatus

SOURCE = Path(__file__).resolve().parent.parent / "tools" / "brief_sweep.py"


def status_literals() -> set[str]:
    """Every string this tool compares a check's `status` against."""
    text = SOURCE.read_text()
    return set(re.findall(r'event\.get\("status"\)\s*(?:==|in)\s*\(?((?:"[a-z_]+",?\s*)+)\)?', text)) and {
        literal
        for group in re.findall(r'event\.get\("status"\)\s*(?:==|in)\s*(\(?(?:"[a-z_]+"[,\s]*)+\)?)', text)
        for literal in re.findall(r'"([a-z_]+)"', group)
    }


def test_brief_sweep_reads_the_labels_the_engine_emits():
    compared = status_literals()

    assert compared, "no status comparisons found — this test is no longer reading the tool"
    unknown = compared - set(get_args(CheckStatus))
    assert not unknown, (
        f"brief_sweep compares against {sorted(unknown)}, which the engine never emits — "
        "those detectors match nothing and report a clean run"
    )


def test_the_headline_detector_still_looks_for_a_failure():
    """The one check the file's own comment calls the reason it exists."""
    assert '"failed"' in SOURCE.read_text()
