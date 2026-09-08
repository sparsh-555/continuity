"""Record the run the landing page animates.

    ../.venv/bin/python tools/record_walkthrough.py

Writes `continuity/api/walkthrough.jsonl`, which Vite bundles into the client.

**The onboarding tour this was built for is gone**, deleted 8 Sep: it taught a story the
product no longer tells, and a finals demo does not open with a guided tour of itself. The
recording outlived it because the landing page replays these frames as its hero animation,
and because a recorded run against real part data is a better thing to animate than an
invented one.

## Why this run and not a live one

The recording has to contain a **conflict and its repair**, because that is the part of
the product worth watching — a board that passes every check animates nothing. It also has
to be identical every time, and a live run would put the distributor and the model on the
critical path of a page load.

The recording is driven through the same HTTP route as any other run, against the offline
catalogue: real manufacturer part numbers, real specs, engine-computed verdicts. Nothing
in the file is written by hand.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import httpx

from continuity import llm
from continuity.api.app import app
from continuity.graph import sourcing
from continuity.planner import plan as planner
from continuity import reviewer
from tests.conftest import _BY_QUERY, _as_candidate
from continuity.graph import catalogue

BRIEF = "temp and humidity sensor, wifi and ble, usb-c powered with li-ion backup, small oled"
OUT = pathlib.Path(__file__).resolve().parent.parent / "continuity" / "api" / "walkthrough.jsonl"


async def find(query: str, *, constraint=None, **_context):
    slot = _BY_QUERY.get(query)
    if slot is None:
        slot = "regulator" if "regulator" in query or "converter" in query else None
    if slot is None:
        return []
    parts = catalogue.CATALOGUE[slot]
    if constraint and constraint.get("topology") == "buck":
        parts = [p for p in parts if p.is_switching]
    return [_as_candidate(p) for p in parts]


async def choose(candidate):
    for options in catalogue.CATALOGUE.values():
        for part in options:
            if part.mpn == candidate.mpn:
                return part
    raise AssertionError(f"no catalogue part for {candidate.mpn}")


async def main() -> None:
    llm.available = lambda: False
    planner.llm.available = lambda: False
    reviewer.llm.available = lambda: False
    sourcing.find = find
    sourcing.choose = choose

    frames = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://record", timeout=60.0
    ) as http:
        async with http.stream("POST", "/design", json={"prompt": BRIEF}) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    frames.append(json.loads(line[6:]))

    kinds: dict[str, int] = {}
    for frame in frames:
        kinds[frame["type"]] = kinds.get(frame["type"], 0) + 1

    if "conflict" not in kinds:
        raise SystemExit("refusing to record: the walkthrough must contain a conflict")

    # `seq` and `thread_id` are stripped: the replay renumbers onto whichever thread it
    # is streaming into, and a recorded identity would be handed to the wrong one.
    body = [{"type": "prompt", "text": BRIEF}]
    body += [
        {k: v for k, v in frame.items() if k not in ("seq", "thread_id")} for frame in frames
    ]

    OUT.write_text("".join(json.dumps(item, separators=(",", ":")) + "\n" for item in body))
    print(f"{OUT.relative_to(pathlib.Path.cwd())}: {len(frames)} frames")
    print("  " + ", ".join(f"{n}× {k}" for k, n in sorted(kinds.items(), key=lambda i: -i[1])))


if __name__ == "__main__":
    asyncio.run(main())
