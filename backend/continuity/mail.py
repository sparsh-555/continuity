"""The notice arrives by email.

A change notice reaches a company as an unstructured PDF attached to a message in
somebody's inbox. Item 22 makes that the trigger, so nothing has to be uploaded for the
work to start, and the upload path stays exactly as it was for the times this cannot run.

## Two halves, and only one of them needs a server

`deliveries` is the whole IMAP conversation and returns plain `Delivery` records.
`collect` takes those records and decides what becomes a notice. Everything worth getting
wrong is in the second half, and it is tested without a mailbox.

## Polling rather than IDLE

IDLE holds a connection open and needs reconnect handling for a saving of a few seconds.
Polling needs an account and no public URL, which is what keeps the venue's network off
the critical path.

## Why the read position is a stored UID and not the \\Seen flag

Marking messages read is the obvious way to remember what has been handled, and it breaks
the moment anybody opens the mailbox in a browser, which is the first thing a person does
when they want to check that the message arrived. Reading it there sets \\Seen, and the
poller then skips the message the demo is about.

So the position is a UID stored against the organisation, and it travels with the folder's
`UIDVALIDITY`. The RFC allows a server to renumber a folder, and says every UID a client
remembers means nothing when it does.
"""

from __future__ import annotations

import email
import email.message
import email.policy
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Sequence

from . import notices

log = logging.getLogger(__name__)

IMAP_SSL_PORT = 993
CONNECT_TIMEOUT_S = 20.0

MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
"""The same ceiling the upload endpoint applies, for the same reason.

A notice is a few pages. Anything larger is a catalogue, a slide deck or a mistake, and
reading it costs a model call whose input we would have to truncate anyway.
"""

READABLE_TYPES = ("application/pdf", "text/plain")
"""What `notices.text_of` can actually turn into text.

Deliberately not "every attachment". A corporate signature carries a logo on almost every
message, and offering a PNG to the reader spends a model call to be told it is not a
notice.
"""

MAX_PER_POLL = 20
"""How many unseen messages one poll will look at.

A bounded amount of work per tick. A mailbox that has been sitting unread for a month
should not turn the first poll into fifty model calls.
"""


@dataclass(frozen=True)
class Delivery:
    """One message, reduced to what a notice reader needs."""

    uid: int
    subject: str
    sender: str
    documents: tuple[tuple[str, bytes], ...]
    """`(filename, bytes)`, in the order they should be tried."""


def configured() -> bool:
    return all(
        os.environ.get(name)
        for name in ("CONTINUITY_MAIL_HOST", "CONTINUITY_MAIL_USER", "CONTINUITY_MAIL_PASSWORD")
    )


def parse(raw: bytes) -> email.message.EmailMessage:
    """A message on the modern API, whatever the sender did to it.

    `email.message_from_bytes` with no policy returns a compat32 `Message`, which has
    neither `iter_attachments` nor `get_body`, and `imap_tools` parses that way. Left
    alone, every real message would have produced no documents at all while every test
    here passed, because a test builds an `EmailMessage` directly. Parsing once, here,
    with the default policy is what makes the two the same thing.
    """
    return email.message_from_bytes(raw, policy=email.policy.default)  # type: ignore[return-value]


def documents_in(message: email.message.EmailMessage) -> list[tuple[str, bytes]]:
    """Every part of a message that could be a change notice, attachments first.

    The body comes last and only when nothing was attached, because a message that carries
    a PCN as a PDF usually also says "please see attached" in the body, and reading that
    sentence would cost a model call to learn nothing.
    """
    found: list[tuple[str, bytes]] = []
    for part in message.iter_attachments():
        content_type = part.get_content_type()
        if content_type not in READABLE_TYPES:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        if len(payload) > MAX_ATTACHMENT_BYTES:
            log.info("skipping %s: %d bytes is over the limit", part.get_filename(), len(payload))
            continue
        found.append((part.get_filename() or "attachment", payload))

    if found:
        return found

    body = message.get_body(preferencelist=("plain",))
    if body is None:
        return []
    text = body.get_payload(decode=True)
    if not text or len(text) > MAX_ATTACHMENT_BYTES:
        return []
    return [("the message body", text)]


def search_from(uid: int | None) -> str:
    """What to ask the server for.

    `UID n:*` is the standard way to say "everything since", and it is inclusive, so the
    stored position is the last UID *handled* and the search starts one past it. A server
    returns the highest existing UID when the range is empty rather than nothing, so the
    caller still has to filter what comes back.
    """
    return "ALL" if uid is None else f"UID {uid + 1}:*"


def resume_at(cursor: tuple[str, int] | None, *, validity: str | None) -> int | None:
    """The stored position, or nothing when the server has renumbered the folder."""
    if cursor is None:
        return None
    stored_validity, uid = cursor
    if validity is not None and stored_validity != validity:
        log.warning(
            "the mailbox reports UIDVALIDITY %s and we stored %s, so every stored UID is "
            "meaningless and the folder is read from the start",
            validity, stored_validity,
        )
        return None
    return uid


async def collect(
    store: Any,
    org_id: str,
    delivered: Iterable[Delivery],
    *,
    read: Callable[[bytes], Awaitable[notices.Notice | None]] | None = None,
    validity: str | None = None,
) -> list[str]:
    """Turn the messages that carry a notice into stored notices. Returns their ids.

    A message that holds no notice is **left alone**: nothing is stored, nothing is
    deleted, and nothing is guessed at. The read position still advances past it, because
    otherwise every poll re-reads the whole inbox and re-reading costs a model call.
    """
    read = read or notices.read
    saved: list[str] = []
    highest: int | None = None

    for delivery in delivered:
        highest = delivery.uid if highest is None else max(highest, delivery.uid)
        notice = None
        source = None
        for filename, document in delivery.documents:
            notice = await read(document)
            if notice is not None:
                source = filename
                break

        if notice is None:
            log.info("nothing readable as a change notice in %r from %s",
                     delivery.subject, delivery.sender)
            continue

        notice_id = await store.save_notice(org_id, None, notice, source=source)
        log.info("read %s out of %s, sent by %s", notice.mpn, source, delivery.sender)
        saved.append(notice_id)

    if highest is not None:
        await store.save_mail_cursor(org_id, validity=validity or "", uid=highest)
    return saved


def deliveries(
    *, cursor: tuple[str, int] | None, limit: int = MAX_PER_POLL
) -> tuple[str | None, list[Delivery]]:
    """Read the mailbox. Returns its `UIDVALIDITY` and everything the cursor has not seen.

    The cursor goes in rather than a bare UID, because whether that UID means anything
    depends on the folder's `UIDVALIDITY` and only this function can see it. An earlier
    version searched with the stored UID and checked validity afterwards, which on a
    renumbered folder asks the server for everything above a number from a different
    folder: real mail, silently skipped.

    Blocking, because `imap_tools` wraps the standard library's blocking `imaplib`. The
    caller runs it off the event loop.
    """
    from imap_tools import MailBox

    host = os.environ["CONTINUITY_MAIL_HOST"]
    user = os.environ["CONTINUITY_MAIL_USER"]
    password = os.environ["CONTINUITY_MAIL_PASSWORD"]

    found: list[Delivery] = []
    with MailBox(host, port=IMAP_SSL_PORT, timeout=CONNECT_TIMEOUT_S).login(user, password) as box:
        validity = _validity(box)
        since = resume_at(cursor, validity=validity)
        # `mark_seen=False` so that what the poller has read is invisible in the mailbox.
        # The read position is ours to remember, and leaving the flags alone means a person
        # opening the inbox sees exactly what a person would expect to see.
        for message in box.fetch(search_from(since), mark_seen=False, limit=limit, bulk=True):
            uid = int(message.uid) if message.uid else 0
            # `UID n:*` returns the highest existing message when nothing is newer, so a
            # poll with no new mail comes back with the last one we already handled.
            if since is not None and uid <= since:
                continue
            found.append(
                Delivery(
                    uid=uid,
                    subject=message.subject or "",
                    sender=message.from_ or "",
                    # Re-parsed rather than using `message.obj`, which `imap_tools`
                    # builds on the compat32 policy. See `parse`.
                    documents=tuple(documents_in(parse(message.obj.as_bytes()))),
                )
            )
    return validity, found


def _validity(box: Any) -> str | None:
    """The folder's `UIDVALIDITY`, or nothing when the server does not volunteer it."""
    try:
        status = box.folder.status(box.folder.get(), ["UIDVALIDITY"])
        value = status.get("UIDVALIDITY")
        return str(value) if value is not None else None
    except Exception as unavailable:  # noqa: BLE001
        log.info("could not read UIDVALIDITY: %s", unavailable)
        return None


POLL_SECONDS = 15.0
"""How often to look. Fast enough that a forwarded notice appears while somebody is still
looking at the screen, slow enough that an idle app is not hammering a mailbox."""


async def poll_once(store: Any, org_id: str) -> list[str]:
    """One pass: read what is new, store any notices in it, move the position."""
    import asyncio

    cursor = await store.mail_cursor(org_id)
    validity, delivered = await asyncio.to_thread(deliveries, cursor=cursor)
    if not delivered:
        return []
    return await collect(store, org_id, delivered, validity=validity)


async def watch(store: Any, *, every: float = POLL_SECONDS) -> None:
    """Poll the mailbox for as long as the app is running.

    Started only when the three variables are set, so an unconfigured install does nothing
    and says so once. Every failure inside the loop is logged and swallowed: a mailbox that
    is unreachable, or credentials that stopped working, must not take the API down with
    them, and the upload path still works while it is broken.
    """
    import asyncio

    from . import llm

    org_id = os.environ.get("CONTINUITY_MAIL_ORG") or await store.only_organisation()
    if not org_id:
        log.warning(
            "the mailbox is configured but there is more than one organisation and "
            "CONTINUITY_MAIL_ORG is not set, so there is no way to say whose notice this "
            "is. Not polling."
        )
        return

    log.info("watching %s for change notices, every %.0fs",
             os.environ.get("CONTINUITY_MAIL_USER"), every)
    while True:
        try:
            # Reading a notice needs the model. Polling without it would walk the whole
            # inbox returning nothing and move the read position past mail nobody looked
            # at, which loses notices rather than delaying them.
            if llm.available():
                await poll_once(store, org_id)
        except asyncio.CancelledError:
            raise
        except Exception as failure:  # noqa: BLE001
            log.warning("mailbox poll failed, will try again: %s", failure)
        await asyncio.sleep(every)
