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

PROCESSED_FOLDER = "Continuity/Processed"
"""Where a message goes once it has become a notice.

**The mailbox is the surface a person checks first, and it said nothing.** A message the
poller had already acted on sat exactly where it was, looking untouched, beside the ones it
had not read — so the only way to know what Continuity had dealt with was to open the
database. Moving it makes the inbox itself the report: what is left in it is what was not
a change notice.

A move rather than a `\\Seen` flag, and the flag is deliberate: the read position is a
stored UID precisely so that marking mail read stays the person's to do, and a poller that
sets `\\Seen` would silently reorder somebody's inbox for them.

A message that held no notice is **left where it is**, which is what makes the report true
rather than tidy.
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
    stored: Callable[[Delivery], None] | None = None,
) -> list[str]:
    """Turn the messages that carry a notice into stored notices. Returns their ids.

    A message that holds no notice is **left alone**: nothing is stored, nothing is
    deleted, and nothing is guessed at. The read position still advances past it, because
    otherwise every poll re-reads the whole inbox and re-reading costs a model call.

    `stored` is told about each message that **did** become a notice, so the caller can
    tell the mailbox which ones it has finished with. It is a callback rather than a second
    return value because the two answer different questions: the ids are what the caller
    acts on, and the deliveries are what the mailbox needs to be told about.
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
        if stored is not None:
            stored(delivery)

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


def move_to_processed(uids: Iterable[int], *, folder: str = PROCESSED_FOLDER) -> int:
    """Move messages that have become notices out of the inbox. Returns how many moved.

    **One connection of its own, and only when there is something to move.** The poll that
    stores a notice is the rare one; every other poll returns here with an empty list and
    does not authenticate at all. That matters more than it looks: a poll is a full login,
    and the incident recorded in `POLL_CEILING_S` was a thousand of them an hour against a
    mailbox that had already stopped answering.

    `imap_tools` sends a server-side `UID MOVE` where the server advertises it and falls
    back to `COPY` plus `STORE \\Deleted` where it does not, so Gmail takes the first path
    and a server without `MOVE` still ends up with the message in the right place.
    """
    from imap_tools import MailBox

    wanted = [str(uid) for uid in uids]
    if not wanted:
        return 0

    host = os.environ["CONTINUITY_MAIL_HOST"]
    user = os.environ["CONTINUITY_MAIL_USER"]
    password = os.environ["CONTINUITY_MAIL_PASSWORD"]

    with MailBox(host, port=IMAP_SSL_PORT, timeout=CONNECT_TIMEOUT_S).login(user, password) as box:
        # Gmail refuses a move into a label that does not exist yet, and a fresh account
        # has never had this one. `exists` first rather than catching the failure, because
        # a create that races another writer is not an error worth reporting.
        if not box.folder.exists(folder):
            box.folder.create(folder)
        box.move(wanted, folder)
    return len(wanted)


def reachable() -> str | None:
    """Sign in and return `None`, or the mailbox's refusal as text.

    **Configured and working are different states, and the preflight used to report the
    first as the second.** The three variables were present all through the hour Google was
    refusing this account, so `./demo.sh --check` printed `mailbox configured` and the first
    thing to discover otherwise was step four of the demonstration.

    One sign-in, at the moment somebody asked, which is cheap enough to do on purpose.
    """
    if not configured():
        return "no mailbox configured"
    try:
        latest_uid()
    except Exception as refusal:  # noqa: BLE001 - the server's own words are the report
        return str(refusal)
    return None


def latest_uid() -> tuple[str | None, int | None]:
    """The folder's `UIDVALIDITY` and the highest UID in it, fetching no message bodies.

    `box.uids()` asks the server for identifiers only, which is the difference between
    learning where the end of the mailbox is and downloading it.
    """
    from imap_tools import MailBox

    host = os.environ["CONTINUITY_MAIL_HOST"]
    user = os.environ["CONTINUITY_MAIL_USER"]
    password = os.environ["CONTINUITY_MAIL_PASSWORD"]

    with MailBox(host, port=IMAP_SSL_PORT, timeout=CONNECT_TIMEOUT_S).login(user, password) as box:
        validity = _validity(box)
        found = [int(uid) for uid in box.uids() if str(uid).isdigit()]
    return validity, (max(found) if found else None)


async def catch_up(store: Any, org_id: str) -> int | None:
    """Move the read position to the end of the mailbox without reading anything.

    **What a reseeded world should do with a mailbox it has never read.** `mail_cursor`
    cascades off the organisation, so a reset wipes the position; the poller then sees a
    mailbox with no history, reads the last run-through's message again, and the demo opens
    on a company that has already received its change notice. The documented workaround was
    to delete the notices afterwards or the message beforehand, and both are a person
    remembering to undo something the machine just did.

    A company that has just been created has not read its mail. Saying so — the position is
    the end of the folder — is the honest state, and it leaves a *newly* forwarded message
    arriving live, which is the thing being demonstrated.
    """
    import asyncio

    validity, highest = await asyncio.to_thread(latest_uid)
    if highest is None:
        return None
    await store.save_mail_cursor(org_id, validity=validity or "", uid=highest)
    return highest


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
"""How often to look **while the mailbox is answering**. Fast enough that a forwarded
notice appears while somebody is still looking at the screen."""

POLL_CEILING_S = 300.0
"""The longest the watcher will wait between attempts after a run of failures.

A poll is a **full IMAP login**: `deliveries` opens a session, authenticates, reads and
closes it, so fifteen seconds is 240 logins an hour. That is fine for the length of a
demonstration and not fine for a process somebody forgot about, which is how this was
found: a server started on 9 September was still polling on the 11th, an estimated nine
thousand logins later, and Google stopped answering that account altogether. Its refusal
arrives as `[ALERT] Invalid credentials (Failure)`, the same alert a revoked password
gives, so the first hour of the incident went into regenerating a password that had never
stopped working.

Backing off costs nothing while the mailbox is healthy, because a healthy mailbox never
reaches for it, and it bounds the damage when it is not: five minutes is twelve logins an
hour instead of two hundred and forty."""


def interval_after(failures: int, *, every: float = POLL_SECONDS) -> float:
    """How long to wait before the next poll, after this many consecutive failures.

    None is the healthy interval and each failure doubles it up to the ceiling. The count
    is of *consecutive* failures, so one blip costs thirty seconds and not a permanent
    slowdown: the caller clears it the moment a poll answers.
    """
    if failures <= 0:
        return every
    return min(every * 2 ** (failures - 1), POLL_CEILING_S)


async def poll_once(store: Any, org_id: str) -> list[str]:
    """One pass: read what is new, store any notices in it, move the position.

    A notice that was read and stored is then moved out of the inbox, which is the only
    step here allowed to fail: the notice is already durable by then, and a mailbox that
    will not accept the move is a tidiness problem rather than a lost change notice.
    """
    import asyncio

    cursor = await store.mail_cursor(org_id)
    if cursor is None:
        # **Nothing has been read yet, and the honest position for a company that has just
        # been created is the end of the folder.** The seed says so when it rebuilds a
        # world; this is the same statement made again when the seed could not reach the
        # mailbox to make it. Without it the poller asks the server for `ALL` and reads the
        # entire inbox, which on 11 September is exactly what happened — and a forwarded
        # copy of the notice left behind by a rehearsal would have been read back as though
        # it had just arrived, before the step whose whole job is showing it arrive.
        #
        # A catch-up that fails raises, so a mailbox that is still unreachable is not read
        # from the top either; the poll fails and backs off, as it should.
        await catch_up(store, org_id)
        cursor = await store.mail_cursor(org_id)

    validity, delivered = await asyncio.to_thread(deliveries, cursor=cursor)
    if not delivered:
        return []

    dealt_with: list[Delivery] = []
    saved = await collect(
        store, org_id, delivered, validity=validity, stored=dealt_with.append
    )
    if dealt_with:
        try:
            await asyncio.to_thread(move_to_processed, [item.uid for item in dealt_with])
        except Exception as failure:  # noqa: BLE001
            log.warning(
                "read %d notice(s) but could not move them out of the inbox: %s",
                len(dealt_with),
                failure,
            )
    return saved


async def whose_mailbox(store: Any) -> str | None:
    """Which company a message in this mailbox is about.

    `CONTINUITY_MAIL_ORG` accepts **a person's email address** as well as an organisation
    id, and the address is the one worth using: an organisation id is minted fresh every
    time the demo world is reseeded, so a `.env` holding one points at a company that no
    longer exists after the first reset, and it fails by finding no product lines rather
    than by saying anything.

    With nothing set, the answer is the only company there is, and no answer at all when
    there is more than one.
    """
    named = os.environ.get("CONTINUITY_MAIL_ORG")
    if not named:
        return await store.only_organisation()
    if "@" in named:
        org_id = await store.organisation_of(named)
        if not org_id:
            log.warning("CONTINUITY_MAIL_ORG names %s, who has no account here", named)
        return org_id
    return named


async def watch(store: Any, *, every: float = POLL_SECONDS, sleep: Any = None) -> None:
    """Poll the mailbox for as long as the app is running.

    Started only when the three variables are set, so an unconfigured install does nothing
    and says so once. Every failure inside the loop is logged and swallowed: a mailbox that
    is unreachable, or credentials that stopped working, must not take the API down with
    them, and the upload path still works while it is broken.

    A mailbox that keeps failing is asked **less and less often**, up to `POLL_CEILING_S`,
    and the count is cleared by the first poll that answers. `sleep` is a seam for the test
    that drives that schedule; nothing in the app passes it.
    """
    import asyncio

    from . import llm

    wait = sleep or asyncio.sleep
    org_id = await whose_mailbox(store)
    if not org_id:
        log.warning(
            "the mailbox is configured but there is more than one organisation and "
            "CONTINUITY_MAIL_ORG is not set, so there is no way to say whose notice this "
            "is. Not polling."
        )
        return

    log.info("watching %s for change notices, every %.0fs",
             os.environ.get("CONTINUITY_MAIL_USER"), every)
    failures = 0
    while True:
        try:
            # Reading a notice needs the model. Polling without it would walk the whole
            # inbox returning nothing and move the read position past mail nobody looked
            # at, which loses notices rather than delaying them.
            if llm.available():
                await poll_once(store, org_id)
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as failure:  # noqa: BLE001
            failures += 1
            log.warning(
                "mailbox poll failed, will try again in %.0fs: %s",
                interval_after(failures, every=every),
                failure,
            )
        await wait(interval_after(failures, every=every))
