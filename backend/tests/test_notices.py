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
from tools.pdf import simple

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


@pytest.fixture(autouse=True)
def reading_goes_to_the_model(monkeypatch):
    """These tests are about what the reader believes, not about the recording net.

    `CONTINUITY_FIXTURES=1` in the environment would send every read to `fixtures/` and
    never reach the stubbed model, so a suite run under replay tested nothing here. The
    three tests that *are* about the net set the variable themselves.
    """
    monkeypatch.delenv("CONTINUITY_FIXTURES", raising=False)


def reply(**overrides):
    base = {
        "reference": "PCN 2026-114",
        "reference_line": "PCN 2026-114 · Advanced Monolithic Systems",
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


def test_a_notice_keeps_its_document_reference_with_the_line_it_was_read_from(model):
    """Two notices can retire the same part; their own reference distinguishes them."""
    model(reply())

    notice = run(notices.read(PCN.encode()))

    assert notice.reference == "PCN 2026-114"
    assert notice.reference_line == "PCN 2026-114 · Advanced Monolithic Systems"


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


def test_a_reference_whose_number_is_not_on_its_own_line_is_dropped(model):
    """The same rule the replacement part number lives under, for the same reason.

    The reference labels a notice in the list, so a model that quotes a real line and hangs
    a different number off it puts a citation on screen that sources nothing. The notice
    survives without a reference; it does not survive an invented one, because the invented
    one is indistinguishable from a real one on screen.
    """
    model(reply(reference="PCN 2026-999", reference_line="Issued 1 September 2026"))

    notice = run(notices.read(PCN.encode()))

    assert notice is not None, "the rest of the notice is unaffected"
    assert notice.reference is None
    assert notice.reference_line is None


def test_a_reference_line_that_is_not_in_the_document_is_dropped(model):
    model(reply(reference_line="Reference: PCN-2026-114 (a line the document does not carry)"))

    notice = run(notices.read(PCN.encode()))

    assert notice is not None
    assert notice.reference is None


def test_a_notice_with_no_reference_at_all_is_still_a_notice(model):
    """Preliminary notices often carry no number. Absent is not a failure."""
    model(reply(reference=None, reference_line=None))

    notice = run(notices.read(PCN.encode()))

    assert notice is not None
    assert notice.reference is None


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


# ── the safety net reaches the first step ─────────────────────────────────────


@pytest.fixture
def recordings(monkeypatch, scratch_recordings):
    """Read from where the suite already writes, so a recording made here replays here.

    `scratch_recordings` in `conftest` redirects every write; pointing reads at the same
    directory is what makes a round trip testable without going near the committed set.
    """
    monkeypatch.setattr(notices.fixtures, "FIXTURE_DIR", scratch_recordings)
    monkeypatch.delenv("CONTINUITY_FIXTURES", raising=False)
    return scratch_recordings


def test_reading_a_notice_is_recorded_and_then_replayed(model, recordings, monkeypatch):
    """The one step that must work first was the one step with no recorded path.

    Everything after the notice replays from `fixtures/` and never touches the network. The
    read itself went to the model every time, so the demo's first move depended on a live
    call that nothing had rehearsed.
    """
    calls = []

    async def complete(system, user, **_kwargs):
        calls.append((system, user))
        return reply()

    monkeypatch.setattr(notices.llm, "available", lambda: True)
    monkeypatch.setattr(notices.llm, "complete_json", complete)

    first = run(notices.read(PCN.encode()))
    assert first is not None and first.mpn == "AMS1117-3.3"
    assert len(calls) == 1, "recorded on the way past, exactly as a distributor call is"
    assert list(recordings.glob("notice_read.*.json")), "and written where replay looks"

    monkeypatch.setenv("CONTINUITY_FIXTURES", "1")
    replayed = run(notices.read(PCN.encode()))

    assert len(calls) == 1, "replaying does not call the model again"
    assert replayed == first, "and the same document reads the same way"


def test_a_notice_nobody_recorded_is_refused_rather_than_fetched(model, recordings, monkeypatch):
    """The contract the rest of the fixture net keeps. A run that quietly reaches the
    network is worse than no fixture mode at all, because it looks offline right up until
    the connection fails."""
    called = []

    async def complete(_system, _user, **_kwargs):
        called.append(1)
        return reply()

    monkeypatch.setattr(notices.llm, "available", lambda: True)
    monkeypatch.setattr(notices.llm, "complete_json", complete)
    monkeypatch.setenv("CONTINUITY_FIXTURES", "1")

    with pytest.raises(notices.fixtures.MissingFixture):
        run(notices.read(PCN.encode()))

    assert called == [], "and it did not ask the model on the way to failing"


def test_a_different_document_is_a_different_recording(model, recordings, monkeypatch):
    """Keyed on what was read, so one recording cannot answer for another notice."""

    async def complete(_system, user, **_kwargs):
        if "AMS1117" in user:
            return reply()
        return reply(
            mpn="LD1117S33TR",
            mpn_line="Affected part: LD1117S33TR (SOT-223)",
        )

    monkeypatch.setattr(notices.llm, "available", lambda: True)
    monkeypatch.setattr(notices.llm, "complete_json", complete)

    run(notices.read(PCN.encode()))
    other = PCN.replace("AMS1117-3.3", "LD1117S33TR")
    run(notices.read(other.encode()))

    assert len(list(recordings.glob("notice_read.*.json"))) == 2

    monkeypatch.setenv("CONTINUITY_FIXTURES", "1")
    assert run(notices.read(other.encode())).mpn == "LD1117S33TR"


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
                    json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
                )
                return posted, (await http.get("/notices")).json()

    posted, listed = run(go())

    assert posted.status_code == 201
    body = posted.json()
    assert body["notice"]["mpn"] == "AMS1117-3.3"
    assert body["notice"]["reference"] == "PCN 2026-114"
    assert {row["name"] for row in body["affected"]} == {"Gateway", "Sensor node"}
    assert all(row["refdes"] == ["u1"] for row in body["affected"])

    assert len(listed) == 1
    assert listed[0]["mpn"] == "AMS1117-3.3"
    assert listed[0]["reference"] == "PCN 2026-114"
    assert listed[0]["source"] == "PCN-2026-114.pdf", (
        "how it arrived is the first thing anybody asks, and the document's own name is an "
        "answer a person recognises where the literal string `api` was not"
    )


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_the_same_notice_arriving_twice_is_one_notice(model):
    """Forwarded to the mailbox and uploaded through the page is one change, not two.

    The product line drew a banner per stored notice, so the same PCN arriving both ways
    put two identical banners and two REVIEW THIS LINE buttons on the board. Nothing
    deduped, and it will happen to anybody who mails the notice after seeding a world that
    already carries it.
    """
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
                line = (await http.post("/lines", json={"name": "Gateway"})).json()
                await http.put(
                    f"/lines/{line['id']}/bom",
                    json={"rows": [{"refdes": "u1", "mpn": "AMS1117-3.3"}]},
                )
                document = base64.b64encode(PCN.encode()).decode()
                mailed = await http.post(
                    "/notices", json={"document": document, "filename": "forwarded.eml"}
                )
                uploaded = await http.post(
                    "/notices", json={"document": document, "filename": "PCN-2026-114.pdf"}
                )
                return mailed.json(), uploaded.json(), (await http.get("/notices")).json()

    mailed, uploaded, listed = run(go())

    assert len(listed) == 1, "one change, however many copies of the document arrive"
    assert uploaded["id"] == mailed["id"], (
        "and the second arrival opens the one already there rather than a new one"
    )
    assert {row["name"] for row in uploaded["affected"]} == {"Gateway"}, (
        "answered in full, because the caller asked a real question"
    )
    assert listed[0]["source"] == "forwarded.eml", "how it first arrived is the record"


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_a_preliminary_and_a_full_notice_about_one_part_are_two_notices(model):
    """`PCN-2026-118` and `PCN-2026-114` both retire AMS1117-3.3, and they say different
    things: one names a last-time-buy date and a replacement, the other names neither.
    Collapsing them would lose the second half of a real story."""
    model(reply())

    async def go():
        async with a_store() as store:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
            ) as http:
                await http.post(
                    "/auth/register",
                    json={"email": "pcn@example.com", "password": "a-good-password"},
                )
                me = (await http.get("/auth/me")).json()

                class Preliminary:
                    mpn = "AMS1117-3.3"
                    mpn_line = "Affected part: AMS1117-3.3 (SOT-223)"
                    reference = "AMS-PCN-2026-118"
                    reference_line = "AMS-PCN-2026-118 · Advanced Monolithic Systems"
                    manufacturer = "Advanced Monolithic Systems"
                    effective_date = None
                    effective_date_line = None
                    replacement_mpn = None
                    replacement_line = None
                    reason = "Wafer fabrication line closure."

                first = await store.save_notice(
                    me["org_id"], me["id"], Preliminary(), source="PCN-2026-118.pdf"
                )
                again = await store.save_notice(
                    me["org_id"], me["id"], Preliminary(), source="PCN-2026-118.pdf"
                )
                full = await http.post(
                    "/notices",
                    json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
                )
                return first, again, full.json(), (await http.get("/notices")).json()

    first, again, full, listed = run(go())

    assert again == first, "a notice with no date is still the same notice twice"
    assert full["id"] != first, "and a date and a replacement make it a different one"
    assert len(listed) == 2


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
def test_a_review_works_when_the_boards_disagree_about_the_position(monkeypatch, model):
    """Real boards put the same part at different reference designators, and that is normal.

    This endpoint applied one position to every affected line, so a company whose regulator
    sits at U3 on one board and U1 on another was told to name one — for a question the
    product can already answer per line. The streaming run has always looked the slot up on
    each board from its own bill; only this path could not, and it refused rather than
    guessing, which was right and still left the common case unanswerable.
    """
    from continuity.api import matrix as matrix_api
    from tools.eol_differential import AMS1117, LINE_A, NCP1117, OUTPUT_CAPACITOR

    specs = {part.mpn: part for part in (AMS1117, NCP1117, OUTPUT_CAPACITOR, LINE_A.load_part)}

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
                    json={"email": "pcn@example.com", "password": "a-good-password"},
                )
                # Two boards that carry the regulator at a different position, which is what
                # the demo's own seeded world does.
                for name, refdes, ambient in (
                    ("Gateway", "u1", 45.0), ("Sensor node", "u3", 25.0)
                ):
                    line = (await http.post("/lines", json={"name": name})).json()
                    await http.put(
                        f"/lines/{line['id']}/bom",
                        json={
                            "rows": [
                                {"refdes": refdes, "mpn": AMS1117.mpn},
                                {"refdes": "u2", "mpn": LINE_A.load_part.mpn},
                                {"refdes": "c1", "mpn": OUTPUT_CAPACITOR.mpn},
                            ]
                        },
                    )
                    await http.put(
                        f"/lines/{line['id']}/profile",
                        json={
                            "revision": "C",
                            "profile": {
                                "ambient_c": ambient,
                                "ambient_source": "test",
                                "mounting": "1000 mm\u00b2 top and back copper, 1/16in FR-4, 1 oz",
                                "rails": {
                                    "vin": {
                                        "voltage": 5.0, "i_limit": 3000,
                                        "basis": "test", "members": [refdes],
                                    },
                                    "3v3": {
                                        "source": refdes, "members": ["u2", "c1"],
                                        "i_load": LINE_A.load,
                                        "i_load_basis": LINE_A.load_basis,
                                    },
                                },
                            },
                        },
                    )
                posted = (
                    await http.post(
                        "/notices",
                        json={
                            "document": base64.b64encode(PCN.encode()).decode(),
                            "filename": "PCN-2026-114.pdf",
                        },
                    )
                ).json()
                return await http.post(
                    f"/notices/{posted['id']}/review", json={"candidates": [NCP1117.mpn]}
                )

    reviewed = run(go())

    # **The 409 is what this row was.** Naming one position and applying it to both boards
    # was the only thing the endpoint could do, so it refused — and a company whose
    # regulator sits at U1 on one product and U3 on another could not review a notice.
    assert reviewed.status_code == 201, reviewed.text
    requests = {r["line_name"]: r for r in reviewed.json()["requests"]}
    assert set(requests) == {"Gateway", "Sensor node"}

    # Each board was substituted at its own position: a candidate only becomes a proposal if
    # the replacement happened in the slot that board actually carries the part in.
    for name, request in requests.items():
        assert request["proposal"] == NCP1117.mpn, f"{name}: {request['proposal_detail']}"
        assert request["baseline_mpn"] == AMS1117.mpn



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
                    json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
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
                    json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
                )

    response = run(go())

    assert response.status_code == 422
    assert "backed by a line of the document" in response.json()["detail"]


@pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB")
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

    `tools.pdf` writes it, which is the same writer the constructed notices in
    `tools/make_notice.py` are built with. Every test above feeds plain text, which left
    the branch that actually matters — a PCN arrives as an attachment — unexercised.
    """
    return simple(lines)


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
                        json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
                    )
                ).json()

                reviewed = await http.post(
                    f"/notices/{posted['id']}/review",
                    json={
                        "candidates": [TLV1117.mpn, LD1117.mpn, NCP1117.mpn],
                    },
                )
                # Reviewed twice, which is what a person does when they think of another
                # candidate. Every document is kept; the listing returns the current one.
                await http.post(
                    f"/notices/{posted['id']}/review",
                    json={"candidates": [NCP1117.mpn]},
                )
                listed = (await http.get(f"/notices/{posted['id']}/review")).json()
                return reviewed, listed

    reviewed, listed = run(go())

    assert reviewed.status_code == 201, reviewed.text
    requests = reviewed.json()["requests"]

    assert len(requests) == 3, "three affected lines, three requests"
    assert len(listed) == 3, (
        "and the listing carries the current request per line, not one per review — "
        "two documents for one product line is a document that contradicts itself"
    )

    by_line = {r["line_name"]: r for r in requests}
    assert set(by_line) == {"Sensor node", "Gateway", "Cabinet controller"}

    for request in requests:
        assert "not_assessed" not in request, f"{request['line_name']} contains a retired coverage status"
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
                        json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
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
                        json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
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
                        json={
                        "document": base64.b64encode(PCN.encode()).decode(),
                        "filename": "PCN-2026-114.pdf",
                    },
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
