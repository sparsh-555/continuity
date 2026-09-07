"""Reading a change notice, and finding what it reaches.

Two properties. **Nothing is believed that the document does not say** — every value comes
back with the line it was read from, and a line that is not in the text is refused outright,
because a notice whose part number was invented starts a review of a part nobody sells. And
**the notice answers the question it raises**: which of the products we ship carry this part.
"""

from __future__ import annotations

import asyncio
import base64
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from continuity import notices
from continuity.api.app import app
from continuity.api.store import Store

PCN = """\
PRODUCT CHANGE NOTIFICATION
PCN 2026-114 · Advanced Monolithic Systems
Issued 1 September 2026

Affected part: AMS1117-3.3 (SOT-223)
Last time buy: 2027-03-31
Reason: wafer fabrication line closure.
Recommended replacement: NCP1117ST33T3G.
"""


def run(coro):
    return asyncio.run(coro)


def reply(**overrides):
    base = {
        "mpn": "AMS1117-3.3",
        "mpn_line": "Affected part: AMS1117-3.3 (SOT-223)",
        "manufacturer": "Advanced Monolithic Systems",
        "effective_date": "2027-03-31",
        "effective_date_line": "Last time buy: 2027-03-31",
        "replacement_mpn": "NCP1117ST33T3G",
        "replacement_line": "Recommended replacement: NCP1117ST33T3G.",
        "reason": "Wafer fabrication line closure.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def model(monkeypatch):
    """Stub the read, keeping the verification this module exists to do."""
    def answer_with(payload):
        async def complete(_system, _user, **_kwargs):
            return payload

        monkeypatch.setattr(notices.llm, "available", lambda: True)
        monkeypatch.setattr(notices.llm, "complete_json", complete)

    return answer_with


# ── what the document says ────────────────────────────────────────────────────


def test_a_notice_is_read_with_the_lines_it_was_read_from(model):
    model(reply())

    notice = run(notices.read(PCN.encode()))

    assert notice.mpn == "AMS1117-3.3"
    assert notice.mpn_line == "Affected part: AMS1117-3.3 (SOT-223)"
    assert notice.effective_date == "2027-03-31"
    assert notice.replacement_mpn == "NCP1117ST33T3G"
    assert notice.manufacturer == "Advanced Monolithic Systems"


def test_a_part_number_the_document_does_not_contain_is_refused(model):
    """The failure that matters: a review opened on a part nobody sells."""
    model(reply(mpn="INVENTED-PART-9000", mpn_line="Affected part: INVENTED-PART-9000"))

    assert run(notices.read(PCN.encode())) is None


def test_a_quoted_line_that_is_not_in_the_document_is_refused(model):
    model(reply(mpn_line="Affected part: AMS1117-3.3, effective immediately"))

    assert run(notices.read(PCN.encode())) is None


def test_a_real_line_with_the_wrong_part_number_attached_is_refused(model):
    """Quoting *a* line is not sourcing *this* value.

    Without this check a reply can cite any true sentence from the document and hang any
    part number off it, which satisfies containment while sourcing nothing.
    """
    model(reply(mpn="LM317T", mpn_line="Reason: wafer fabrication line closure."))

    assert run(notices.read(PCN.encode())) is None


def test_an_unsourced_date_is_dropped_and_the_rest_survives(model):
    """A notice is still useful without a date. It is useless with an invented one."""
    model(reply(effective_date_line="Last time buy: 2026-01-01"))

    notice = run(notices.read(PCN.encode()))

    assert notice is not None, "one bad field must not discard the whole notice"
    assert notice.effective_date is None
    assert notice.mpn == "AMS1117-3.3"


def test_a_date_that_is_not_a_date_is_dropped(model):
    model(reply(effective_date="soon", effective_date_line="Last time buy: 2027-03-31"))

    assert run(notices.read(PCN.encode())).effective_date is None


def test_a_notice_recommending_nothing_is_still_a_notice(model):
    model(reply(replacement_mpn=None, replacement_line=None))

    notice = run(notices.read(PCN.encode()))

    assert notice.replacement_mpn is None
    assert notice.mpn == "AMS1117-3.3"


def test_a_document_with_no_readable_text_is_refused(model):
    model(reply())

    assert run(notices.read(b"\x00\x01\x02")) is None
    assert run(notices.read(b"")) is None


def test_without_a_model_nothing_is_guessed(monkeypatch):
    monkeypatch.setattr(notices.llm, "available", lambda: False)

    assert run(notices.read(PCN.encode())) is None


# ── which products it reaches ─────────────────────────────────────────────────

DB_URL = os.environ.get("CONTINUITY_TEST_DB")


@asynccontextmanager
async def a_store():
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=3, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute(
                "TRUNCATE users, organisations, sessions, product_lines, threads CASCADE"
            )
        previous = app.state.store
        app.state.store = store
        try:
            yield store
        finally:
            app.state.store = previous


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_a_posted_notice_names_the_products_that_carry_the_part(model):
    """The question a notice raises and never answers."""
    model(reply())

    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "pcn@example.com", "password": "a-good-password"},
                )
                for name, mpn in (
                    ("Gateway", "AMS1117-3.3"),
                    ("Sensor node", "AMS1117-3.3"),
                    ("Unrelated", "SOMETHING-ELSE"),
                ):
                    line = (await http.post("/lines", json={"name": name})).json()
                    await http.put(
                        f"/lines/{line['id']}/bom",
                        json={"rows": [{"refdes": "u1", "mpn": mpn}]},
                    )

                posted = await http.post(
                    "/notices",
                    json={"document": base64.b64encode(PCN.encode()).decode()},
                )
                return posted, (await http.get("/notices")).json()

    posted, listed = run(go())

    assert posted.status_code == 201
    body = posted.json()
    assert body["notice"]["mpn"] == "AMS1117-3.3"
    assert {row["name"] for row in body["affected"]} == {"Gateway", "Sensor node"}
    assert all(row["refdes"] == ["u1"] for row in body["affected"])

    assert len(listed) == 1
    assert listed[0]["mpn"] == "AMS1117-3.3"
    assert listed[0]["source"] == "api", "how it arrived is the first thing anybody asks"


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_a_notice_for_a_part_we_do_not_ship_says_so_rather_than_failing(model):
    """An empty answer is a real result: this does not reach anything we make."""
    model(reply())

    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "none@example.com", "password": "a-good-password"},
                )
                return await http.post(
                    "/notices",
                    json={"document": base64.b64encode(PCN.encode()).decode()},
                )

    response = run(go())

    assert response.status_code == 201
    assert response.json()["affected"] == []


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_an_unreadable_document_is_refused_with_a_reason(model):
    model(reply(mpn="INVENTED", mpn_line="Affected part: INVENTED"))

    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "bad@example.com", "password": "a-good-password"},
                )
                return await http.post(
                    "/notices",
                    json={"document": base64.b64encode(PCN.encode()).decode()},
                )

    response = run(go())

    assert response.status_code == 422
    assert "backed by a line of the document" in response.json()["detail"]


def test_the_endpoint_needs_an_account():
    async def go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            return await http.post("/notices", json={"document": "eA=="})

    assert run(go()).status_code == 401


# ── a notice arrives as a PDF, which is how they actually arrive ──────────────


def a_pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF with genuinely extractable text.

    Built by hand rather than with a library because the project has no PDF *writer* and
    should not gain a dependency to test a reader. Every test above feeds plain text, which
    left the branch that actually matters — a PCN arrives as an attachment — unexercised.
    """
    content = "BT /F1 11 Tf 40 760 Td 14 TL\n"
    for line in lines:
        content += f"({line}) Tj T*\n"
    content += "ET"
    stream = content.encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n".encode()
        + b"%%EOF\n"
    )
    return bytes(out)


PDF_LINES = [
    "PRODUCT CHANGE NOTIFICATION",
    "PCN 2026-114 - Advanced Monolithic Systems",
    "Affected part: AMS1117-3.3 (SOT-223)",
    "Last time buy: 2027-03-31",
    "Recommended replacement: NCP1117ST33T3G.",
]


def test_text_is_extracted_from_a_real_pdf():
    extracted = notices.text_of(a_pdf(PDF_LINES))

    assert extracted is not None
    for line in PDF_LINES:
        assert line in extracted, f"{line!r} did not survive extraction"


def test_a_pdf_notice_is_verified_against_its_own_extracted_text(model):
    """The whole point of the quoted lines: they have to survive the PDF, not the fixture.

    A test that only ever feeds plain text proves the verification logic and nothing about
    whether a real attachment reaches it — which is exactly how a green suite ends up
    sitting on top of an extractor that refuses every real document.
    """
    model(reply(mpn_line="Affected part: AMS1117-3.3 (SOT-223)"))

    notice = notices.read(a_pdf(PDF_LINES))
    notice = asyncio.run(notice) if asyncio.iscoroutine(notice) else notice

    assert notice is not None, "a real PDF was refused"
    assert notice.mpn == "AMS1117-3.3"
    assert notice.effective_date == "2027-03-31"


def test_a_pdf_whose_text_does_not_back_the_claim_is_still_refused(model):
    """Extraction must not become a way round the verification."""
    model(reply(mpn="LM317T", mpn_line="Affected part: LM317T (TO-220)"))

    assert run(notices.read(a_pdf(PDF_LINES))) is None


def test_a_pdf_with_no_extractable_text_is_refused(model):
    model(reply())

    assert run(notices.read(b"%PDF-1.4\nnot really a pdf\n")) is None


# ── a notice becomes change requests ──────────────────────────────────────────


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_a_notice_yields_one_change_request_per_affected_line(model, monkeypatch):
    """The whole flow in one call: notice, exposure, matrix, request — per line.

    Per line because the answer differs per line, which is the finding a single
    manufacturer-wide recommendation cannot express and the reason any of this exists.
    """
    from continuity.api import matrix as matrix_api
    from tools.eol_differential import (
        AMS1117, LD1117, LINES, NCP1117, OUTPUT_CAPACITOR, TLV1117,
    )

    specs = {
        part.mpn: part
        for part in (AMS1117, TLV1117, LD1117, NCP1117, OUTPUT_CAPACITOR,
                     *(line.load_part for line in LINES))
    }

    async def resolve(mpn: str, manufacturer: str | None = None):
        return specs.get(mpn)

    monkeypatch.setattr(matrix_api, "resolve", resolve)
    model(reply())

    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "flow@example.com", "password": "a-good-password"},
                )
                for line in LINES:
                    created = (await http.post("/lines", json={"name": line.label})).json()
                    await http.put(
                        f"/lines/{created['id']}/bom",
                        json={
                            "rows": [
                                {"refdes": "u1", "mpn": AMS1117.mpn},
                                {"refdes": "u2", "mpn": line.load_part.mpn},
                                {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn},
                            ]
                        },
                    )
                    await http.put(
                        f"/lines/{created['id']}/profile",
                        json={
                            "revision": "C",
                            "profile": {
                                "ambient_c": line.ambient_c,
                                "ambient_source": line.ambient_basis,
                                "mounting": "1000 mm² top and back copper, 1/16in FR-4, 1 oz",
                                "rails": {
                                    "vin": {
                                        "voltage": line.input_voltage,
                                        "i_limit": line.input_limit,
                                        "basis": line.input_basis,
                                        "members": ["u1"],
                                    },
                                    "3v3": {
                                        "source": "u1",
                                        "members": ["u2", "c1"],
                                        "i_load": line.load,
                                        "i_load_basis": line.load_basis,
                                    },
                                },
                            },
                        },
                    )

                posted = (
                    await http.post(
                        "/notices",
                        json={"document": base64.b64encode(PCN.encode()).decode()},
                    )
                ).json()

                reviewed = await http.post(
                    f"/notices/{posted['id']}/review",
                    json={
                        "candidates": [TLV1117.mpn, LD1117.mpn, NCP1117.mpn],
                        "annual_volume": 20_000,
                    },
                )
                listed = (await http.get(f"/notices/{posted['id']}/review")).json()
                return reviewed, listed

    reviewed, listed = run(go())

    assert reviewed.status_code == 201, reviewed.text
    requests = reviewed.json()["requests"]

    assert len(requests) == 3, "three affected lines, three requests"
    assert len(listed) == 3, "and they were persisted"

    by_line = {r["line_name"]: r for r in requests}
    assert set(by_line) == {"Sensor node", "Gateway", "Cabinet controller"}

    for request in requests:
        assert request["not_assessed"] == [
            "emc", "output_capacitor_stability", "signal_integrity"
        ], f"{request['line_name']} does not say what it left unchecked"
        assert request["baseline_mpn"] == AMS1117.mpn
        assert request["revision"] == "C"
        assert request["notice_mpn"] == AMS1117.mpn
        assert request["cost"]["one_time"] > 0

    # The notice recommends NCP1117 and the gateway cannot take it.
    gateway = by_line["Gateway"]
    assert gateway["proposal"] != NCP1117.mpn
    rejected = {a["mpn"]: a["rejected_because"] for a in gateway["alternatives"]}
    assert "159 °C" in (rejected.get(NCP1117.mpn) or ""), "the sentence that killed it"

    # And the lines that can take it, do — which is exactly the per-line finding.
    assert by_line["Sensor node"]["proposal"] == NCP1117.mpn


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_reviewing_a_notice_for_a_part_we_do_not_ship_is_refused_with_a_reason(model):
    model(reply())

    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "nothing@example.com", "password": "a-good-password"},
                )
                posted = (
                    await http.post(
                        "/notices",
                        json={"document": base64.b64encode(PCN.encode()).decode()},
                    )
                ).json()
                return await http.post(
                    f"/notices/{posted['id']}/review", json={"candidates": ["ANY-PART"]}
                )

    response = run(go())

    assert response.status_code == 409
    assert "not on any product line you ship" in response.json()["detail"]


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_another_organisations_notice_is_a_404():
    async def go():
        async with a_store():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "stranger@example.com", "password": "a-good-password"},
                )
                return await http.post(
                    "/notices/does-not-exist/review", json={"candidates": ["X"]}
                )

    assert run(go()).status_code == 404


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_an_older_notice_can_still_be_reviewed(model):
    """It was found by scanning the recent ones, which fails on a notice plainly on screen."""
    model(reply())

    async def go():
        async with a_store() as store:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "old@example.com", "password": "a-good-password"},
                )
                me = (await http.get("/auth/me")).json()
                first = (
                    await http.post(
                        "/notices",
                        json={"document": base64.b64encode(PCN.encode()).decode()},
                    )
                ).json()["id"]

                # Bury it under more notices than any listing page would return.
                async with store.pool.connection() as conn:
                    for index in range(250):
                        await conn.execute(
                            "INSERT INTO notices (id, org_id, mpn, mpn_line, source) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (f"filler-{index}", me["org_id"], "X", "X", "api"),
                        )

                return await store.notice_for_org(first, me["org_id"])

    found = run(go())

    assert found is not None, "a notice older than one page became unreachable"
    assert found["mpn"] == "AMS1117-3.3"


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_a_second_notice_does_not_re_propose_what_the_first_ruled_out(model, monkeypatch):
    """BUILD item 15a, end to end: the review remembers, so the reader does not have to.

    Two reviews of the same notice. The first learns that the manufacturer's own
    recommendation cooks the gateway; the second must not put it back in front of the same
    person — while still listing it, with the reason, so the document does not look as
    though it was never considered.
    """
    from continuity.api import matrix as matrix_api
    from tools.eol_differential import (
        AMS1117, LD1117, LINES, NCP1117, OUTPUT_CAPACITOR, TLV1117,
    )

    specs = {
        part.mpn: part
        for part in (AMS1117, TLV1117, LD1117, NCP1117, OUTPUT_CAPACITOR,
                     *(line.load_part for line in LINES))
    }

    async def resolve(mpn: str, manufacturer: str | None = None):
        return specs.get(mpn)

    monkeypatch.setattr(matrix_api, "resolve", resolve)
    model(reply())

    gateway = next(line for line in LINES if line.id == "B")

    async def go():
        async with a_store() as store:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "memory@example.com", "password": "a-good-password"},
                )
                me = (await http.get("/auth/me")).json()
                created = (await http.post("/lines", json={"name": gateway.label})).json()
                await http.put(
                    f"/lines/{created['id']}/bom",
                    json={
                        "rows": [
                            {"refdes": "u1", "mpn": AMS1117.mpn},
                            {"refdes": "u2", "mpn": gateway.load_part.mpn},
                            {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn},
                        ]
                    },
                )
                await http.put(
                    f"/lines/{created['id']}/profile",
                    json={
                        "revision": "C",
                        "profile": {
                            "ambient_c": gateway.ambient_c,
                            "ambient_source": gateway.ambient_basis,
                            "mounting": "1000 mm² copper",
                            "rails": {
                                "vin": {
                                    "voltage": gateway.input_voltage,
                                    "i_limit": gateway.input_limit,
                                    "basis": gateway.input_basis,
                                    "members": ["u1"],
                                },
                                "3v3": {
                                    "source": "u1", "members": ["u2", "c1"],
                                    "i_load": gateway.load,
                                    "i_load_basis": gateway.load_basis,
                                },
                            },
                        },
                    },
                )

                notice = (
                    await http.post(
                        "/notices",
                        json={"document": base64.b64encode(PCN.encode()).decode()},
                    )
                ).json()

                body = {"candidates": [NCP1117.mpn, LD1117.mpn]}
                first = (await http.post(f"/notices/{notice['id']}/review", json=body)).json()
                remembered = await store.rejected_on(me["org_id"], created["id"])
                second = (await http.post(f"/notices/{notice['id']}/review", json=body)).json()
                return first, remembered, second

    first, remembered, second = run(go())

    [first_request] = first["requests"]
    [second_request] = second["requests"]

    assert first_request["proposal"] != NCP1117.mpn, "it cooks the gateway on the first look"
    assert NCP1117.mpn in remembered, "the rejection was never written down"
    assert "159 °C" in remembered[NCP1117.mpn]

    assert second_request["proposal"] != NCP1117.mpn
    listed = {a["mpn"]: a["rejected_because"] for a in second_request["alternatives"]}
    assert NCP1117.mpn in listed, "a part dropped in silence looks like one never considered"
    assert listed[NCP1117.mpn]
