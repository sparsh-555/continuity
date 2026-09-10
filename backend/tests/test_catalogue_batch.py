"""The review's distributor shortlist remains deterministic under concurrent normalisation."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from continuity.api import review as review_api
from continuity.parts.search import Candidate as SearchCandidate
from tools.eol_differential import AMS1117, TLV1117


def test_catalogue_normalisation_is_bounded_concurrent_and_keeps_pool_order(monkeypatch):
    """One slow datasheet does not serialize the shortlist or reorder its answer."""
    parts = {
        mpn: replace(TLV1117, mpn=mpn, vout_min=3.3, vout_max=3.3)
        for mpn in "ABCDEFGHIZ"
    }
    parts["C"] = replace(parts["C"], vout_min=5.0, vout_max=5.0)
    hits = [
        SearchCandidate(
            lcsc=f"C-{mpn}", mpn=mpn, manufacturer="Test", description="LDO",
            package="SOT-223", category="Regulator", subcategory="LDO", stock=1,
            unit_price=0.1, library_type="basic",
        )
        for mpn in parts
    ]

    async def go():
        started: list[str] = []
        first_batch_started = asyncio.Event()
        release_first_batch = asyncio.Event()

        async def find(*_args, **_kwargs):
            return hits

        async def choose(hit):
            started.append(hit.mpn)
            if len(started) == 4:
                first_batch_started.set()
            if hit.mpn in "ABCD":
                await release_first_batch.wait()
            return parts[hit.mpn]

        monkeypatch.setattr(review_api.sourcing, "find", find)
        monkeypatch.setattr(review_api.sourcing, "choose", choose)
        search = asyncio.create_task(review_api._catalogue_search(AMS1117))
        try:
            await asyncio.wait_for(first_batch_started.wait(), timeout=0.1)
        except TimeoutError:
            search.cancel()
            await asyncio.gather(search, return_exceptions=True)
            raise
        before_releasing = list(started)
        release_first_batch.set()
        return before_releasing, started, await search

    before_releasing, started, found = asyncio.run(go())

    assert before_releasing == ["A", "B", "C", "D"]
    assert started == ["A", "B", "C", "D", "E", "F", "G", "H"]
    assert [part.mpn for part in found] == ["A", "B", "D", "E"]
