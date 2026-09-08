"""Prove the mailbox credentials work, before anything is built on top of them.

    ../.venv/bin/python tools/check_mail.py

Reads `CONTINUITY_MAIL_HOST`, `CONTINUITY_MAIL_USER` and `CONTINUITY_MAIL_PASSWORD` from
`backend/.env` and does the smallest useful thing: connect, authenticate, open the inbox,
and say how many messages are in it.

## Why this exists separately from the poller

Item 22's poller has two ways to fail and they need different fixes. Either the mailbox
will not let us in, which is an account problem, or it lets us in and we read the message
wrongly, which is ours. Running this first settles the first question on its own, so the
poller is only ever debugged against a connection already known to work.

**Nothing here prints the password**, and neither should anything you paste into a
terminal to debug it. The output is a host, an address and a count.
"""

from __future__ import annotations

import imaplib
import os
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from continuity import env

IMAP_SSL_PORT = 993

REQUIRED = ("CONTINUITY_MAIL_HOST", "CONTINUITY_MAIL_USER", "CONTINUITY_MAIL_PASSWORD")


def main() -> int:
    env.load()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f"not configured: {', '.join(missing)}")
        print("Put them in backend/.env. See BUILD.md item 22.")
        return 1

    host = os.environ["CONTINUITY_MAIL_HOST"]
    user = os.environ["CONTINUITY_MAIL_USER"]
    print(f"connecting to {host}:{IMAP_SSL_PORT} as {user}")

    try:
        mailbox = imaplib.IMAP4_SSL(host, IMAP_SSL_PORT, ssl_context=ssl.create_default_context())
    except OSError as unreachable:
        # Separated from an authentication failure on purpose. A blocked port and a wrong
        # password are the same red cross in a mail client and completely different jobs.
        print(f"could not reach the server: {unreachable}")
        return 1

    try:
        mailbox.login(user, os.environ["CONTINUITY_MAIL_PASSWORD"])
    except imaplib.IMAP4.error as refused:
        print(f"the server refused the credentials: {refused}")
        print("For Gmail this is almost always the account password rather than a")
        print("16-character app password, or spaces left in when it was pasted.")
        return 1

    try:
        status, counts = mailbox.select("INBOX", readonly=True)
        if status != "OK":
            print(f"signed in, but INBOX could not be opened: {status}")
            return 1
        print(f"signed in. INBOX holds {int(counts[0])} messages.")
        status, unseen = mailbox.search(None, "UNSEEN")
        if status == "OK":
            print(f"{len(unseen[0].split())} of them are unread.")
    finally:
        mailbox.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
