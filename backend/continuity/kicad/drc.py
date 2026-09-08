"""The design rule check, and what a substitution changed about it.

## Three arrays, not one

`kicad-cli pcb drc --format json` reports `violations`, `unconnected_items` and
`schematic_parity` as siblings. A reader that takes only the first calls a board with an
entirely unrouted net clean, and *clean* is the one answer nobody checks. All three are
read, and a **missing key is an error** rather than an empty list, because an empty list
renders exactly like a board with nothing wrong.

## The delta is the finding, not the count

Real boards arrive with violations already on them — the upstream board used to verify this
carries fifty-four of them and one unconnected item before anything is touched. So the
question is never "how many", it is *what did this substitution add*. Findings are matched
by rule and by the items they name, which are stable across runs of the same board, and the
answer is the set that appeared.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .runner import Runner

CATEGORIES = ("violations", "unconnected_items", "schematic_parity")


class UnreadableReport(RuntimeError):
    """The report was not the shape this KiCad is documented to produce."""


@dataclass(frozen=True)
class Finding:
    """One thing KiCad objects to, and the items it objects about."""

    rule: str
    description: str
    severity: str
    items: tuple[str, ...]

    @property
    def key(self) -> tuple[str, tuple[str, ...]]:
        """What makes this finding the same finding on another run of the same board."""
        return (self.rule, self.items)


@dataclass(frozen=True)
class Report:
    violations: tuple[Finding, ...]
    unconnected: tuple[Finding, ...]
    parity: tuple[Finding, ...]

    @property
    def all(self) -> tuple[Finding, ...]:
        return self.violations + self.unconnected + self.parity

    def counts(self) -> dict[str, int]:
        counted: dict[str, int] = {}
        for finding in self.all:
            counted[finding.rule] = counted.get(finding.rule, 0) + 1
        return counted


@dataclass(frozen=True)
class Delta:
    """What a substitution did to a board, in the check's own terms."""

    added: tuple[Finding, ...]
    removed: tuple[Finding, ...]
    before: Report
    after: Report

    @property
    def added_unconnected(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.added if f.rule == "unconnected_items")

    @property
    def broke_connections(self) -> bool:
        return bool(self.added_unconnected)

    def by_rule(self) -> dict[str, tuple[int, int]]:
        """Every rule either side mentions, as `(before, after)` counts."""
        before, after = self.before.counts(), self.after.counts()
        return {
            rule: (before.get(rule, 0), after.get(rule, 0))
            for rule in sorted(set(before) | set(after))
        }


def _finding(entry: Mapping[str, Any], fallback_rule: str) -> Finding:
    items = tuple(
        str(item.get("description") or "").strip()
        for item in entry.get("items") or []
        if isinstance(item, Mapping)
    )
    return Finding(
        rule=str(entry.get("type") or fallback_rule),
        description=str(entry.get("description") or "").strip(),
        severity=str(entry.get("severity") or "unknown"),
        items=items,
    )


def parse(payload: Mapping[str, Any]) -> Report:
    for category in CATEGORIES:
        if category not in payload:
            raise UnreadableReport(
                f"the DRC report has no {category!r} key. An absent category is not an "
                f"empty one: it would read as a board with nothing wrong."
            )
    return Report(
        violations=tuple(_finding(e, "violation") for e in payload["violations"]),
        unconnected=tuple(_finding(e, "unconnected_items") for e in payload["unconnected_items"]),
        parity=tuple(_finding(e, "schematic_parity") for e in payload["schematic_parity"]),
    )


def run(runner: Runner, *, workdir: Path, board: str, out: str) -> Report:
    """Check one board. Violations are an outcome, not a failure, so the exit code is not
    treated as one — `--exit-code-violations` is deliberately not passed."""
    runner.cli_run(
        ["pcb", "drc", "--format", "json", "--severity-all", "-o", out, board],
        workdir=workdir,
    )
    return parse(json.loads((workdir / out).read_text(encoding="utf-8")))


def _surplus(these: tuple[Finding, ...], those: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """The findings in `these` that `those` does not already account for.

    Counted rather than set-subtracted: a board can carry the same finding twice — two
    identical clearance complaints about two pairs of items KiCad describes the same way —
    and set arithmetic would report a second one appearing as nothing at all.
    """
    remaining = Counter(finding.key for finding in those)
    surplus = []
    for finding in these:
        if remaining.get(finding.key):
            remaining[finding.key] -= 1
            continue
        surplus.append(finding)
    return tuple(surplus)


def compare(before: Report, after: Report) -> Delta:
    return Delta(
        added=_surplus(after.all, before.all),
        removed=_surplus(before.all, after.all),
        before=before,
        after=after,
    )
