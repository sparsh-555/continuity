"""The review's distributor shortlist remains deterministic under concurrent normalisation."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from continuity.api import review as review_api
from continuity.parts.search import Candidate as SearchCandidate
from tools.eol_differential import AMS1117, TLV1117


def test_catalogue_search_filters_the_retiring_output_before_normalising(monkeypatch):
    """A catalogue's 5 V regulator never spends a costly normalisation slot for 3.3 V."""
    wrong_rail = SearchCandidate(
        lcsc="C-WRONG", mpn="WRONG-5V", manufacturer="Test", description="LDO",
        package="SOT-223", category="Regulator", subcategory="LDO", stock=1,
        unit_price=0.1, library_type="basic", specs={"Output Voltage": "5V"},
    )
    right_rail = SearchCandidate(
        lcsc="C-RIGHT", mpn="RIGHT-3V3", manufacturer="Test", description="LDO",
        package="SOT-223", category="Regulator", subcategory="LDO", stock=1,
        unit_price=0.1, library_type="basic", specs={"Output Voltage": "3.3V"},
    )

    async def go():
        chosen: list[str] = []

        async def find(*_args, constraint, **_kwargs):
            assert constraint == {"package": "SOT-223", "vout": 3.3}
            return [right_rail]

        async def choose(hit):
            chosen.append(hit.mpn)
            return replace(TLV1117, mpn=hit.mpn, vout_min=3.3, vout_max=3.3)

        monkeypatch.setattr(review_api.sourcing, "find", find)
        monkeypatch.setattr(review_api.sourcing, "choose", choose)
        found = await review_api._catalogue_search(AMS1117)
        return chosen, found

    chosen, found = asyncio.run(go())

    assert wrong_rail.mpn not in chosen
    assert chosen == [right_rail.mpn]
    assert [part.mpn for part in found] == [right_rail.mpn]


def test_catalogue_normalisation_is_bounded_concurrent_and_keeps_pool_order(monkeypatch):
    """One slow datasheet does not serialize the shortlist or reorder its answer."""
    mpns = [f"P{number}" for number in range(1, 10)]
    parts = {
        mpn: replace(TLV1117, mpn=mpn, vout_min=3.3, vout_max=3.3)
        for mpn in mpns
    }
    parts["P3"] = replace(parts["P3"], vout_min=5.0, vout_max=5.0)
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
            if hit.mpn in {"P1", "P2", "P3", "P4"}:
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

    assert before_releasing == ["P1", "P2", "P3", "P4"]
    assert started == ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]
    assert [part.mpn for part in found] == ["P1", "P2", "P4", "P5"]
