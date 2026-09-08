"""The notice arrives by email.

Item 22. The IMAP conversation and what we do with a message are kept apart, so almost
everything here runs without a server: `mail.deliveries` is the only function that talks
to a mailbox, and `mail.collect` takes `Delivery` objects and decides what becomes a
notice.
"""

from __future__ import annotations

import asyncio
import email.message
import pathlib

import pytest

from continuity import mail
from continuity.notices import Notice

PDF = (pathlib.Path(__file__).resolve().parent.parent.parent
       / "docs" / "world-finals" / "notices" / "PCN-2026-114.pdf")

NOTICE = Notice(
    mpn="AMS1117-3.3",
    mpn_line="Affected part: AMS1117-3.3 (SOT-223)",
    replacement_mpn="NCP1117ST33T3G",
)


def a_message(*, subject: str = "PCN", attachments: tuple = (), body: str = "") -> email.message.EmailMessage:
    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = "notices@example-supplier.com"
    message.set_content(body or "See attached.")
    for filename, content_type, payload in attachments:
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    return message


class _Store:
    """Only what `collect` touches."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []
        self.cursor: tuple[str, int] | None = None

    async def save_notice(self, org_id, user_id, notice, *, source):
        self.saved.append((notice.mpn, source))
        return f"notice-{len(self.saved)}"

    async def mail_cursor(self, org_id):
        return self.cursor

    async def save_mail_cursor(self, org_id, *, validity, uid):
        self.cursor = (validity, uid)


# ── which parts of a message could be a notice ───────────────────────────────


def test_a_pdf_attachment_is_a_candidate_document():
    found = mail.documents_in(
        a_message(attachments=(("PCN-2026-114.pdf", "application/pdf", b"%PDF-1.4 x"),))
    )
    assert [name for name, _ in found] == ["PCN-2026-114.pdf"]


def test_a_plain_text_attachment_is_a_candidate_document():
    """A supplier that pastes the notice into a .txt is not doing anything unusual."""
    found = mail.documents_in(
        a_message(attachments=(("notice.txt", "text/plain", b"Affected part: X"),))
    )
    assert [name for name, _ in found] == ["notice.txt"]


def test_the_body_is_read_when_nothing_is_attached():
    """PCNs are usually attached and sometimes pasted. Refusing the second would fail on a
    real message for a reason that has nothing to do with the notice."""
    found = mail.documents_in(a_message(body="Affected part: AMS1117-3.3"))
    assert len(found) == 1 and b"AMS1117-3.3" in found[0][1]


def test_an_image_attachment_is_not_offered_as_a_document():
    """A signature logo is on almost every corporate message and is not a notice."""
    found = mail.documents_in(
        a_message(attachments=(("logo.png", "image/png", b"\x89PNG\r\n\x1a\n"),))
    )
    assert "logo.png" not in [name for name, _ in found]


def test_an_attachment_larger_than_the_limit_is_refused_before_it_is_read():
    oversize = b"%PDF-" + b"0" * (mail.MAX_ATTACHMENT_BYTES + 1)
    found = mail.documents_in(a_message(attachments=(("big.pdf", "application/pdf", oversize),)))
    assert "big.pdf" not in [name for name, _ in found]


def test_the_body_is_still_read_when_the_only_attachment_was_unreadable():
    """Deliberate, and the reason the two tests above assert about one filename rather than
    about an empty list. A corporate signature puts a logo on almost every message, and a
    supplier who pastes the notice under it has still sent us the notice."""
    found = mail.documents_in(
        a_message(
            attachments=(("logo.png", "image/png", b"\x89PNG\r\n\x1a\n"),),
            body="Affected part: AMS1117-3.3",
        )
    )
    assert [name for name, _ in found] == ["the message body"]


# ── what becomes a notice ────────────────────────────────────────────────────


def test_a_message_carrying_a_notice_is_stored_with_the_document_that_carried_it():
    async def go():
        store = _Store()
        read = _reader({b"%PDF-1.4 real": NOTICE})
        delivered = [mail.Delivery(uid=7, subject="PCN", sender="s@x.com",
                                   documents=(("PCN-2026-114.pdf", b"%PDF-1.4 real"),))]
        return await mail.collect(store, "org-1", delivered, read=read), store

    saved, store = asyncio.run(go())
    assert saved == ["notice-1"]
    assert store.saved == [("AMS1117-3.3", "PCN-2026-114.pdf")]


def test_a_message_with_no_notice_in_it_is_left_alone_rather_than_guessed_at():
    async def go():
        store = _Store()
        delivered = [mail.Delivery(uid=7, subject="Lunch?", sender="a@b.com",
                                   documents=(("lunch.txt", b"see you at one"),))]
        return await mail.collect(store, "org-1", delivered, read=_reader({})), store

    saved, store = asyncio.run(go())
    assert saved == [] and store.saved == []


def test_the_first_readable_document_wins_and_the_rest_are_not_read():
    """One message is one notice. A signature PDF behind the real one must not become a
    second change notice about the same event."""
    calls: list[bytes] = []

    async def read(document: bytes):
        calls.append(document)
        return NOTICE if document == b"first" else None

    async def go():
        store = _Store()
        delivered = [mail.Delivery(uid=1, subject="PCN", sender="s@x.com",
                                   documents=(("a.pdf", b"first"), ("b.pdf", b"second")))]
        return await mail.collect(store, "org-1", delivered, read=read), store

    saved, store = asyncio.run(go())
    assert len(saved) == 1 and calls == [b"first"]


def test_the_cursor_advances_past_a_message_that_held_no_notice():
    """Otherwise every poll re-reads the whole inbox, and re-reading costs a model call."""

    async def go():
        store = _Store()
        delivered = [mail.Delivery(uid=11, subject="Lunch?", sender="a@b.com",
                                   documents=(("x.txt", b"nothing"),))]
        await mail.collect(store, "org-1", delivered, read=_reader({}), validity="42")
        return store.cursor

    assert asyncio.run(go()) == ("42", 11)


def test_the_cursor_takes_the_highest_uid_seen_not_the_last_one():
    async def go():
        store = _Store()
        delivered = [
            mail.Delivery(uid=9, subject="a", sender="a@b.com", documents=()),
            mail.Delivery(uid=4, subject="b", sender="a@b.com", documents=()),
        ]
        await mail.collect(store, "org-1", delivered, read=_reader({}), validity="42")
        return store.cursor

    assert asyncio.run(go()) == ("42", 9)


def _reader(answers: dict):
    async def read(document: bytes):
        return answers.get(document)

    return read


# ── the search that decides what a poll looks at ─────────────────────────────


def test_a_first_run_asks_for_everything_in_the_mailbox():
    assert mail.search_from(None) == "ALL"


def test_a_later_run_asks_only_for_what_arrived_since():
    assert mail.search_from(41) == "UID 42:*"


def test_a_changed_uidvalidity_makes_every_stored_uid_meaningless():
    """The server may renumber a folder, and the RFC says old UIDs mean nothing when it
    does. Carrying the old cursor across would silently skip real mail."""
    assert mail.resume_at(("42", 100), validity="43") is None
    assert mail.resume_at(("42", 100), validity="42") == 100


@pytest.mark.skipif(not PDF.exists(), reason="the constructed notice is not in the tree")
def test_the_real_notice_pdf_survives_being_an_attachment():
    """End to end through the mail layer, minus the model: the bytes that come back out of
    a MIME attachment have to be the bytes that went in, or the reader gets a broken PDF."""
    original = PDF.read_bytes()
    found = mail.documents_in(
        a_message(attachments=(("PCN-2026-114.pdf", "application/pdf", original),))
    )
    assert found[0][1] == original


# ── when the poller runs at all ──────────────────────────────────────────────


def test_an_unconfigured_install_knows_it_is_unconfigured(monkeypatch):
    for name in ("CONTINUITY_MAIL_HOST", "CONTINUITY_MAIL_USER", "CONTINUITY_MAIL_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    assert mail.configured() is False


def test_two_of_three_variables_is_not_configured(monkeypatch):
    """A half-filled `.env` is the likeliest way to get here, and it must not look ready."""
    monkeypatch.setenv("CONTINUITY_MAIL_HOST", "imap.gmail.com")
    monkeypatch.setenv("CONTINUITY_MAIL_USER", "a@b.com")
    monkeypatch.delenv("CONTINUITY_MAIL_PASSWORD", raising=False)
    assert mail.configured() is False


def test_the_watcher_refuses_to_guess_whose_notice_it_is(monkeypatch, caplog):
    """A mailbox belongs to a company and nothing in a message says which. With more than
    one organisation and no setting, attributing a notice to whichever account came first
    would file real change requests against a stranger's product lines."""

    class _Ambiguous:
        async def only_organisation(self):
            return None

    monkeypatch.delenv("CONTINUITY_MAIL_ORG", raising=False)
    with caplog.at_level("WARNING"):
        asyncio.run(mail.watch(_Ambiguous(), every=0.01))
    assert "CONTINUITY_MAIL_ORG" in caplog.text


# ── the message we are handed is not the message we can read ─────────────────


def test_a_message_parsed_the_way_imap_tools_parses_one_still_yields_its_attachment():
    """The guard on the trap that would have shipped.

    `imap_tools` calls `email.message_from_bytes(raw)` with no policy, which returns a
    compat32 `Message`: no `iter_attachments`, no `get_body`. Every test above builds an
    `EmailMessage` directly and so never saw it. This one goes through bytes, the way a
    real message does, and fails if `parse` stops normalising the policy.
    """
    import email as email_module

    original = a_message(attachments=(("PCN.pdf", "application/pdf", b"%PDF-1.4 hello"),))
    as_imap_tools_would = email_module.message_from_bytes(original.as_bytes())
    assert not hasattr(as_imap_tools_would, "iter_attachments"), (
        "if this ever fails, imap_tools may have changed policy and `parse` can go"
    )

    found = mail.documents_in(mail.parse(as_imap_tools_would.as_bytes()))
    assert [name for name, _ in found] == ["PCN.pdf"]
    assert found[0][1] == b"%PDF-1.4 hello"


# ── one whole pass, with the server stubbed ──────────────────────────────────


def test_a_poll_reads_what_is_new_stores_the_notice_and_moves_the_position(monkeypatch):
    async def go():
        store = _Store()
        store.cursor = ("42", 100)
        asked: dict = {}

        def fake_deliveries(*, cursor, limit=20):
            asked["cursor"] = cursor
            # What a server actually returns: the search range is inclusive and an empty
            # one comes back with the highest existing message, so the already-handled
            # one arrives too and `deliveries` drops it.
            return "42", [
                mail.Delivery(uid=101, subject="PCN", sender="s@x.com",
                              documents=(("PCN-2026-114.pdf", b"%PDF-1.4 real"),)),
            ]

        monkeypatch.setattr(mail, "deliveries", fake_deliveries)
        monkeypatch.setattr(mail.notices, "read", _reader({b"%PDF-1.4 real": NOTICE}))
        saved = await mail.poll_once(store, "org-1")
        return saved, store, asked

    saved, store, asked = asyncio.run(go())
    assert asked["cursor"] == ("42", 100), "the whole cursor goes in, not a bare UID"
    assert len(saved) == 1
    assert store.saved == [("AMS1117-3.3", "PCN-2026-114.pdf")]
    assert store.cursor == ("42", 101)


def test_a_poll_after_the_folder_was_renumbered_starts_again_from_the_beginning(monkeypatch):
    async def go():
        store = _Store()
        store.cursor = ("42", 100)

        def fake_deliveries(*, cursor, limit=20):
            return "99", [
                mail.Delivery(uid=1, subject="PCN", sender="s@x.com",
                              documents=(("PCN.pdf", b"%PDF-1.4 real"),)),
            ]

        monkeypatch.setattr(mail, "deliveries", fake_deliveries)
        monkeypatch.setattr(mail.notices, "read", _reader({b"%PDF-1.4 real": NOTICE}))
        saved = await mail.poll_once(store, "org-1")
        return saved, store

    saved, store = asyncio.run(go())
    assert len(saved) == 1, "UID 1 is below the stored 100 and must not be filtered out"
    assert store.cursor == ("99", 1)


def test_the_already_handled_message_a_server_returns_is_dropped_inside_deliveries():
    """`UID n:*` is inclusive and a server answers an empty range with the highest
    existing message, so a poll with no new mail comes back holding the last one already
    turned into a notice. Filtering it out is what stops one notice being filed twice."""
    kept = [d for d in _as_returned_by_a_server(since=100) if d.uid > 100]
    assert [d.uid for d in kept] == [101]


def _as_returned_by_a_server(*, since: int):
    return [
        mail.Delivery(uid=since, subject="already handled", sender="a@b.com", documents=()),
        mail.Delivery(uid=since + 1, subject="new", sender="a@b.com", documents=()),
    ]


# ── the stored read position, against a real database ────────────────────────

import os
from contextlib import asynccontextmanager

from continuity.api.store import Store

DB_URL = os.environ.get("CONTINUITY_TEST_DB")
database = pytest.mark.skipif(not DB_URL, reason="set CONTINUITY_TEST_DB to run these")


@asynccontextmanager
async def a_store():
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool(DB_URL, min_size=1, max_size=2, open=False) as pool:
        await pool.open()
        store = Store(pool)
        await store.setup()
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE users, organisations CASCADE")
        yield store


@database
def test_the_read_position_round_trips():
    async def go():
        async with a_store() as store:
            org = await store.create_organisation("Northwind")
            assert await store.mail_cursor(org.id) is None
            await store.save_mail_cursor(org.id, validity="42", uid=100)
            return await store.mail_cursor(org.id)

    assert asyncio.run(go()) == ("42", 100)


@database
def test_the_read_position_never_moves_backwards():
    """Two polls overlapping must not rewind the mailbox and re-read what is already
    stored, which would file the same change notice twice."""

    async def go():
        async with a_store() as store:
            org = await store.create_organisation("Northwind")
            await store.save_mail_cursor(org.id, validity="42", uid=100)
            await store.save_mail_cursor(org.id, validity="42", uid=90)
            return await store.mail_cursor(org.id)

    assert asyncio.run(go()) == ("42", 100)


@database
def test_a_renumbered_folder_replaces_the_position_rather_than_keeping_the_highest():
    """Under a new UIDVALIDITY the old number is not a smaller position, it is a number
    about a different folder, so `GREATEST` would be comparing two unrelated things."""

    async def go():
        async with a_store() as store:
            org = await store.create_organisation("Northwind")
            await store.save_mail_cursor(org.id, validity="42", uid=100)
            await store.save_mail_cursor(org.id, validity="43", uid=3)
            return await store.mail_cursor(org.id)

    assert asyncio.run(go()) == ("43", 3)


@database
def test_one_company_is_answered_and_two_are_not():
    async def go():
        async with a_store() as store:
            first = await store.create_organisation("Northwind")
            alone = await store.only_organisation()
            await store.create_organisation("Someone else")
            return alone, first.id, await store.only_organisation()

    alone, first_id, ambiguous = asyncio.run(go())
    assert alone == first_id
    assert ambiguous is None, "with two companies the mailbox cannot say whose notice it is"
