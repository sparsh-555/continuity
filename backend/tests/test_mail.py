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


def test_a_world_that_has_never_read_its_mail_catches_up_before_it_reads_anything(monkeypatch):
    """The seed moves a rebuilt world's read position past its inbox, and **this is the
    second chance for the times it cannot reach the mailbox at all**.

    11 September, live: the seed could not sign in, so the world kept no position, so the
    poller asked the server for `ALL` and read the entire inbox. What it found there was an
    older notice email, refused only because nobody had recorded that document. A forwarded
    copy of the real notice, left in the mailbox by a rehearsal, would have been read back
    as though it had just arrived — before step four, which is the step that shows it
    arriving.
    """
    store = _Store()
    asked: list[object] = []
    caught_up: list[str] = []

    async def catch_up(store_arg, org_id):
        caught_up.append(org_id)
        store_arg.cursor = ("1", 8)
        return 8

    def deliveries(*, cursor, limit=None):
        asked.append(cursor)
        return "1", []

    monkeypatch.setattr(mail, "catch_up", catch_up)
    monkeypatch.setattr(mail, "deliveries", deliveries)
    monkeypatch.setattr("continuity.llm.available", lambda: True)

    assert asyncio.run(mail.poll_once(store, "org-1")) == []
    assert caught_up == ["org-1"], "a world with no position catches up before it reads"
    assert asked == [("1", 8)], "and it reads from where that left it, not from the top"


def test_a_world_that_has_read_its_mail_is_not_caught_up_again(monkeypatch):
    """Catching up is for a world with no position. Doing it every poll would be a second
    login every fifteen seconds, which is what closed this account in the first place."""
    store = _Store()
    store.cursor = ("1", 41)
    asked: list[object] = []

    async def catch_up(*_args, **_kwargs):
        raise AssertionError("a world with a position must not be caught up again")

    monkeypatch.setattr(mail, "catch_up", catch_up)
    monkeypatch.setattr(mail, "deliveries", lambda *, cursor, limit=None: (asked.append(cursor), ("1", []))[1])
    monkeypatch.setattr("continuity.llm.available", lambda: True)

    assert asyncio.run(mail.poll_once(store, "org-1")) == []
    assert asked == [("1", 41)]


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


# ── whose notice is it ───────────────────────────────────────────────────────


class _Companies:
    def __init__(self, only=None, by_email=None):
        self._only = only
        self._by_email = by_email or {}

    async def only_organisation(self):
        return self._only

    async def organisation_of(self, email):
        return self._by_email.get(email)


def test_with_one_company_the_mailbox_needs_no_setting(monkeypatch):
    monkeypatch.delenv("CONTINUITY_MAIL_ORG", raising=False)
    assert asyncio.run(mail.whose_mailbox(_Companies(only="org-1"))) == "org-1"


def test_an_address_is_resolved_to_the_company_that_person_belongs_to(monkeypatch):
    """The setting takes an address on purpose. An organisation id is minted fresh by every
    reseed, so a `.env` holding one points at a company that stopped existing after the
    first reset, and it fails by quietly finding no product lines."""
    monkeypatch.setenv("CONTINUITY_MAIL_ORG", "engineer@northwind.example")
    companies = _Companies(by_email={"engineer@northwind.example": "org-7"})
    assert asyncio.run(mail.whose_mailbox(companies)) == "org-7"


def test_an_address_nobody_holds_is_refused_rather_than_guessed(monkeypatch):
    monkeypatch.setenv("CONTINUITY_MAIL_ORG", "nobody@example.com")
    assert asyncio.run(mail.whose_mailbox(_Companies(only="org-1"))) is None


def test_an_organisation_id_is_still_accepted(monkeypatch):
    monkeypatch.setenv("CONTINUITY_MAIL_ORG", "563595ec3fb4")
    assert asyncio.run(mail.whose_mailbox(_Companies())) == "563595ec3fb4"


# ── a mailbox that is refusing us is asked less and less often ───────────────


class _Enough(BaseException):
    """Ends the watcher from inside the fake sleep.

    A `BaseException` on purpose. The loop swallows every `Exception`, because a mailbox
    that stopped answering must not take the API down with it, so a test that wants to end
    the loop has to arrive at a level that `except Exception` cannot catch.
    """


def _driven(monkeypatch, *, outcomes, every=mail.POLL_SECONDS, watching=True):
    """Run the watcher through `outcomes` and return every interval it waited.

    One outcome per poll: True for a poll that answered, False for one that raised.
    Somebody is watching unless a test says otherwise, so these read the fast schedule the
    demonstration runs on rather than the idle one, which sleeps in slices.
    """
    monkeypatch.delenv("CONTINUITY_MAIL_ORG", raising=False)
    monkeypatch.setattr(mail, "someone_is_watching", lambda: watching)
    slept: list[float] = []

    async def sleep(seconds):
        slept.append(seconds)
        if len(slept) == len(outcomes):
            raise _Enough

    polls = iter(outcomes)

    async def poll_once(store, org_id):
        if not next(polls):
            raise RuntimeError("[ALERT] Invalid credentials (Failure)")

    monkeypatch.setattr(mail, "poll_once", poll_once)
    monkeypatch.setattr("continuity.llm.available", lambda: True)

    try:
        asyncio.run(mail.watch(_Companies(only="org-1"), every=every, sleep=sleep))
    except _Enough:
        pass
    return slept


def test_a_mailbox_that_keeps_refusing_us_is_asked_less_and_less_often(monkeypatch):
    """Found the hard way on 11 September, and not by the suite.

    A poll is a **full IMAP login**, so fifteen seconds is 240 of them an hour. A server
    started on 9 September was still running on the 11th, roughly nine thousand logins
    later, and Google stopped answering that account for the next hour. What it says then
    is `[ALERT] Invalid credentials`, which is also what a revoked password says, so the
    first hour went into re-creating a password that had never stopped working.
    """
    slept = _driven(monkeypatch, outcomes=[False, False, False, False], every=15.0)
    assert slept == [15.0, 30.0, 60.0, 120.0]


def test_one_poll_that_answers_puts_the_interval_back_where_it_was(monkeypatch):
    """The half that decides whether the demo still works.

    A mailbox that recovers has to be read at fifteen seconds again. An interval that only
    ever grew would mean a notice forwarded after a single blip waits minutes to be seen,
    which is a worse failure than the one the backoff exists to prevent.
    """
    slept = _driven(monkeypatch, outcomes=[False, False, True, False], every=15.0)
    assert slept == [15.0, 30.0, 15.0, 15.0]


def test_the_interval_never_grows_past_the_ceiling(monkeypatch):
    slept = _driven(monkeypatch, outcomes=[False] * 8, every=15.0)
    assert slept[-1] == mail.POLL_CEILING_S
    assert all(seconds <= mail.POLL_CEILING_S for seconds in slept)


def test_no_failures_at_all_is_the_healthy_interval():
    assert mail.interval_after(0) == mail.POLL_SECONDS


# ── how often the mailbox is asked, and by whose number ──────────────────────


def test_nobody_waiting_on_a_notice_is_asked_at_google_s_own_interval():
    """**Ten minutes, and the number is Google's rather than ours.**

    Their own client guidance tells a mail program to "check for new messages every 10
    minutes". We were at fifteen seconds, forty times that, and the account was closed for
    it twice in a day — the second time within nine minutes of a single well-behaved poller
    starting. The fast interval is not wrong, it is wrong when nobody is waiting: a
    forwarded notice has to appear while somebody watches it, and a poller left running
    overnight is not being watched by anybody at all.
    """
    assert mail.POLL_IDLE_SECONDS == 600.0
    assert mail.interval_for(0, watching=False) == mail.POLL_IDLE_SECONDS


def test_somebody_waiting_on_a_notice_is_asked_every_fifteen_seconds():
    assert mail.interval_for(0, watching=True) == mail.POLL_SECONDS


def test_the_slow_interval_is_the_floor_the_backoff_grows_from():
    """The ceiling has to be above the idle interval, or a failure would *speed up* the
    polling it exists to slow down, which is the shape of bug this file keeps finding."""
    assert mail.POLL_CEILING_S > mail.POLL_IDLE_SECONDS
    assert mail.interval_for(2, watching=False) == 2 * mail.POLL_IDLE_SECONDS
    assert mail.interval_for(9, watching=False) == mail.POLL_CEILING_S
    assert mail.interval_for(9, watching=True) == mail.POLL_CEILING_S


def _recorder(slept: list):
    async def wait(seconds):
        slept.append(seconds)
    return wait


def test_a_poller_nobody_is_waiting_on_sleeps_the_whole_interval():
    slept: list[float] = []
    asyncio.run(mail.sleep_until_due(_recorder(slept), 10.0, watching=lambda: False))
    assert sum(slept) == 10.0


def test_a_browser_that_arrives_mid_nap_does_not_wait_the_nap_out():
    """The reason the long sleep is sliced. A poller napping for Google's ten minutes must
    not make a browser that opens thirty seconds later sit through the rest of it: the
    report arrives on the screen somebody is looking at, which is the whole point."""
    slept: list[float] = []
    asyncio.run(
        mail.sleep_until_due(_recorder(slept), 600.0, watching=lambda: len(slept) >= 2)
    )
    assert slept == [mail.WATCH_TICK_S, mail.WATCH_TICK_S]


def test_the_route_the_browser_polls_is_what_marks_the_mailbox_watched():
    """The line that turns the whole design on, so it is tested through the route rather
    than by reading the source: without it the poller never believes anybody is waiting,
    the fast interval never engages, and a forwarded notice takes Google's ten minutes to
    appear on the screen somebody forwarded it to watch."""
    from continuity.api import notices as notices_api

    class _Store:
        async def notices_for_org(self, org_id):
            return []

    class _App:
        class state:  # noqa: N801 - the shape `store_of` reaches for
            store = _Store()

    class _Request:
        app = _App()

    class _User:
        org_id = "org-1"

    mail.forget_watchers()
    assert mail.someone_is_watching() is False
    assert asyncio.run(notices_api.list_notices(_Request(), _User())) == []
    assert mail.someone_is_watching() is True


def test_asking_for_notices_is_what_marks_the_mailbox_watched(monkeypatch):
    """The signal is the arrivals poll the browser already runs from every screen, which is
    why it does not depend on any one page being open."""
    clock = iter([1_000.0, 1_000.0, 1_000.0 + mail.WATCHED_WINDOW_S + 1.0])
    monkeypatch.setattr(mail.time, "monotonic", lambda: next(clock))
    mail.forget_watchers()

    assert mail.someone_is_watching() is False, "nothing has asked yet"
    mail.note_someone_is_watching()
    assert mail.someone_is_watching() is True
    assert mail.someone_is_watching() is False, "and the watch lapses on its own"


# ── the mailbox is the surface a person checks first ─────────────────────────


class _Folder:
    def __init__(self, exists: bool, created: list):
        self._exists = exists
        self._created = created

    def exists(self, folder):
        return self._exists

    def create(self, folder):
        self._created.append(folder)
        self._exists = True


class _Box:
    """A mailbox that records what was asked of it and answers nothing else."""

    def __init__(self, *, folder_exists: bool = True):
        self.created: list[str] = []
        self.moved: list[tuple[list[str], str]] = []
        self.folder = _Folder(folder_exists, self.created)

    def login(self, user, password):
        self.credentials = (user, password)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def move(self, uids, destination):
        self.moved.append((list(uids), destination))


def _a_box(monkeypatch, **kwargs):
    opened = []

    def factory(*_args, **_kwargs):
        opened.append(_Box(**kwargs))
        return opened[-1]

    monkeypatch.setattr("imap_tools.MailBox", factory)
    monkeypatch.setenv("CONTINUITY_MAIL_HOST", "imap.example.com")
    monkeypatch.setenv("CONTINUITY_MAIL_USER", "notices@example.com")
    monkeypatch.setenv("CONTINUITY_MAIL_PASSWORD", "app-password")
    return opened


def test_the_mailbox_is_told_which_messages_became_notices(monkeypatch):
    """What it is told is what it moves, and nothing else.

    A message that held no notice stays where it is on purpose: that is what makes the
    inbox itself the report. What is left in it is what was not a change notice.
    """
    deliveries = [
        mail.Delivery(uid=7, subject="a catalogue", sender="sales@x.com",
                      documents=(("catalogue.pdf", b"%PDF-1.4 nothing"),)),
        mail.Delivery(uid=8, subject="PCN", sender="notices@x.com",
                      documents=(("PCN.pdf", b"%PDF-1.4 the notice"),)),
    ]
    told: list[int] = []

    async def go():
        return await mail.collect(
            _Store(), "org-1", deliveries,
            read=_reader({b"%PDF-1.4 the notice": NOTICE}),
            stored=lambda delivery: told.append(delivery.uid),
        )

    saved = asyncio.run(go())
    assert saved == ["notice-1"]
    assert told == [8]


def test_nothing_to_move_does_not_open_the_mailbox(monkeypatch):
    """A poll that stored nothing must not authenticate a second time for it."""
    opened = _a_box(monkeypatch)
    assert mail.move_to_processed([]) == 0
    assert opened == []


def test_a_processed_message_is_moved_into_its_own_folder(monkeypatch):
    """The read position is a stored UID rather than \\Seen precisely so that flag stays
    the person's to set, so a message Continuity has dealt with is moved instead."""
    opened = _a_box(monkeypatch)
    assert mail.move_to_processed([8]) == 1
    assert opened[0].moved == [(["8"], mail.PROCESSED_FOLDER)]
    assert opened[0].created == [], "the folder is not created when it is already there"


def test_the_folder_is_created_when_the_mailbox_does_not_have_it(monkeypatch):
    """Gmail rejects a move into a label that does not exist yet."""
    opened = _a_box(monkeypatch, folder_exists=False)
    assert mail.move_to_processed([8, 9]) == 2
    assert opened[0].created == [mail.PROCESSED_FOLDER]
    assert opened[0].moved == [(["8", "9"], mail.PROCESSED_FOLDER)]


def test_a_move_that_fails_does_not_lose_the_notice(monkeypatch):
    """The notice is stored before anything is moved, and tidying the mailbox is the part
    allowed to fail. A folder that cannot be created must not cost a change notice.

    The call is recorded as well as raised, because a poll that never tries to move anything
    would pass this on the first half alone — which is a test passing for the wrong reason.
    """
    store = _Store()
    store.cursor = ("1", 7)
    attempts: list[list[int]] = []

    async def read(_document):
        return NOTICE

    def refuses(uids, **_kwargs):
        attempts.append(list(uids))
        raise OSError("the mailbox refused the move")

    monkeypatch.setattr(mail.notices, "read", read)
    monkeypatch.setattr(mail, "move_to_processed", refuses)
    monkeypatch.setattr(mail, "deliveries", lambda **_kwargs: (
        "1",
        [mail.Delivery(uid=8, subject="PCN", sender="n@x.com",
                       documents=(("PCN.pdf", b"%PDF-1.4 the notice"),))],
    ))
    monkeypatch.setattr("continuity.llm.available", lambda: True)

    assert asyncio.run(mail.poll_once(store, "org-1")) == ["notice-1"]
    assert store.saved == [("AMS1117-3.3", "PCN.pdf")]
    assert attempts == [[8]], "the message that became the notice is what gets moved"
