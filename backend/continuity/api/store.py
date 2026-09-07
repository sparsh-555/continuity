"""Application tables over the same connection pool the checkpointer uses.

## Why this is not an ORM

`langgraph-checkpoint-postgres` already brings psycopg3 and `psycopg_pool`, so a second
driver and a mapping layer would buy nothing: the schema is four tables of flat columns
and the queries are all single-statement. Sharing one pool also means one place where
connection limits, timeouts and shutdown are decided.

## Why the user-scoped lookups take a `user_id` rather than filtering afterwards

`line_for_user` and `thread_for_user` are the authorisation boundary for `/resume`,
`/export` and everything under `/lines`. Fetching by id and comparing the owner in
Python is the same logic with one more place to forget it, so ownership is a `WHERE`
clause and there is no unscoped read to reach for by accident.

A miss returns `None` and the route answers 404 rather than 403 — a 403 confirms that a
thread exists, which is a fact the caller has no business learning.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from .findings import Finding
from ..engine.models import ApprovedLists
from ..parts.dossier import DOSSIER_FIELDS
from ..profile import OperatingProfile

SCHEMA = Path(__file__).with_name("schema.sql")

SESSION_IDLE_SECONDS = 60 * 30
"""How long a session survives with no requests at all.

Sliding, not absolute: every authenticated request pushes `expires_at` out again, so the
window only runs down while nobody is using the app. A design run — including one paused
on an escalation question, because answering it is a request — keeps its own session alive,
which is the property that makes an idle timeout safe to have during a live demo.

Thirty minutes is the shortest window that cannot plausibly expire mid-sentence. Two
minutes was considered and rejected for exactly that: a run that stops to ask a question
while somebody talks over it would 401 its own answer.
"""

SESSION_TTL_SECONDS = 60 * 60 * 24 * 14
"""The absolute ceiling, measured from when the session was minted.

An idle timeout alone can be slid forever, so a stolen cookie that is *used* never expires.
This is the backstop, and it is why `user_for_token` clamps with `LEAST` rather than simply
adding the idle window each time.
"""


class EmailTaken(Exception):
    """Registration hit the unique constraint on `users.email`."""


ROLES = ("engineering", "procurement", "quality")
"""Every role a person can hold. Checked wherever roles are set.

A role nobody validates is a permission that silently never applies: a typo in
`{"enginering"}` grants nothing and reports nothing, and the first sign of it is a person
who cannot answer a question they are supposed to own.
"""


class UnknownRole(Exception):
    """A role outside `ROLES` reached a write."""


@dataclass(frozen=True)
class Organisation:
    id: str
    name: str


@dataclass(frozen=True)
class User:
    id: str
    email: str
    password_hash: str
    onboarded_at: datetime | None
    org_id: str
    """The company this person works for, and the authorisation boundary for everything
    they can see. Not nullable: the schema back-fills an organisation of one for every
    account that predates the column, so there is no such thing as a user without one and
    no code path should be written as though there were."""

    roles: tuple[str, ...] = ("engineering",)


@dataclass(frozen=True)
class Line:
    id: str
    user_id: str
    """Who created this line. No longer who may see it — that is `org_id`."""

    org_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    revision: str | None = None
    profile: dict[str, Any] | None = None

    part_count: int = 0
    """How many populated rows the line's BOM holds.

    Counted in SQL beside the row rather than fetched per line by the dashboard, which is
    what it did first: rendering "187 parts" cost one request and one whole BOM per line
    on screen. The count is what the dashboard needs; the BOM is what the line page needs."""


@dataclass(frozen=True)
class Thread:
    id: str
    line_id: str
    user_id: str
    """Who started this run. No longer who may see it — that is `org_id`."""

    org_id: str
    prompt: str
    status: str
    last_seq: int
    bom: list[dict[str, Any]] | None
    summary: dict[str, Any] | None


def new_id() -> str:
    """Same shape as the thread ids already in the wire format."""
    return uuid.uuid4().hex[:12]


def _fold(email: str) -> str:
    """One spelling per account. Folded before every read and every write."""
    return email.strip().lower()


WALKTHROUGH_LINE_NAME = "Welcome to Continuity"
SCRATCH_LINE_NAME = "Scratch designs"


def _derived_id(user_id: str, purpose: str) -> str:
    """A stable id for a row an account may only have one of.

    Same shape as `new_id()`, but reproducible — which is what lets two concurrent
    requests insert the same row instead of two different ones.
    """
    return hashlib.sha256(f"{purpose}:{user_id}".encode()).hexdigest()[:12]


def _hash_token(token: str) -> str:
    """What is stored. The cookie value itself never reaches the database."""
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def setup(self) -> None:
        """Apply the schema. Idempotent, like `checkpointer.setup()`."""
        async with self.pool.connection() as conn:
            await conn.execute(SCHEMA.read_text())

    # ── users ────────────────────────────────────────────────────────────────

    async def create_user(self, email: str, password_hash: str) -> User:
        """A new account and the organisation it works for, in one transaction.

        Signing up is joining a company of one. There is no account without an
        organisation — the schema back-fills one for every account that predates the
        column — so minting them apart would create a window in which a user exists and
        can see nothing, including their own board.

        Joining an *existing* organisation is `add_user_to_organisation`, which has no
        screen yet: item 16 seeds the demo world and item 11b's tests build the situation
        directly. An invite button that did nothing would be worse than no button.
        """
        user_id = new_id()
        org_id = _derived_id(user_id, "org")
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO organisations (id, name) VALUES (%s, %s)",
                        (org_id, _fold(email)),
                    )
                    await conn.execute(
                        "INSERT INTO users (id, email, password_hash, org_id) "
                        "VALUES (%s, %s, %s, %s)",
                        (user_id, _fold(email), password_hash, org_id),
                    )
        except psycopg.errors.UniqueViolation as exc:
            raise EmailTaken(email) from exc

        return User(
            id=user_id, email=_fold(email), password_hash=password_hash,
            onboarded_at=None, org_id=org_id, roles=("engineering",),
        )

    async def create_organisation(self, name: str) -> Organisation:
        org_id = new_id()
        async with self.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO organisations (id, name) VALUES (%s, %s)", (org_id, name)
            )
        return Organisation(id=org_id, name=name)

    async def add_user_to_organisation(
        self, user_id: str, org_id: str, roles: Sequence[str]
    ) -> None:
        """Move a person into a company and set the hats they wear.

        Everything they created stays theirs to have created and moves with them, because
        `user_id` records authorship and `org_id` decides visibility — leaving their lines
        behind in the old organisation would strand rows nobody can reach.
        """
        unknown = sorted(set(roles) - set(ROLES))
        if unknown:
            raise UnknownRole(f"unknown roles: {unknown}; known roles are {list(ROLES)}")
        if not roles:
            raise UnknownRole("a user with no roles can answer nothing")

        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE users SET org_id = %s, roles = %s WHERE id = %s",
                    (org_id, list(roles), user_id),
                )
                for table in ("product_lines", "threads", "findings", "line_parts"):
                    await conn.execute(
                        f"UPDATE {table} SET org_id = %s WHERE user_id = %s", (org_id, user_id)
                    )

    async def user_by_email(self, email: str) -> User | None:
        return await self._one_user("WHERE email = %s", (_fold(email),))

    async def user_by_id(self, user_id: str) -> User | None:
        return await self._one_user("WHERE id = %s", (user_id,))

    async def update_password_hash(self, user_id: str, password_hash: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id)
            )

    async def mark_onboarded(self, user_id: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE users SET onboarded_at = now() WHERE id = %s AND onboarded_at IS NULL",
                (user_id,),
            )

    async def _one_user(self, where: str, params: tuple[Any, ...]) -> User | None:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                f"SELECT id, email, password_hash, onboarded_at, org_id, roles FROM users {where}", params
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return User(**{**row, "roles": tuple(row["roles"] or ())})

    # ── sessions ─────────────────────────────────────────────────────────────

    async def create_session(
        self, user_id: str, ttl_seconds: int = SESSION_IDLE_SECONDS
    ) -> str:
        """Mint a session and return the raw token. Only its hash is kept.

        It starts with one idle window in front of it, not the absolute ceiling — the
        ceiling is a limit on how far the window may later be slid, not a grant.
        """
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        async with self.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (_hash_token(token), user_id, expires),
            )
        return token

    async def user_for_token(self, token: str) -> User | None:
        """The whole auth check *and* the sliding renewal, in one statement.

        Validating and renewing separately would be two round trips and a race — a request
        arriving in the last moments of a window could read it live and renew it dead. As
        one `UPDATE … RETURNING`, a session is renewed exactly when it is found valid.

        `LEAST` is what keeps the absolute ceiling meaningful: without it, a session that is
        used every twenty minutes would be renewed for ever.

        **Every authenticated request writes a row.** That is a deliberate trade at this
        scale — the alternative, only renewing once a window is half spent, needs the read
        and the write in separate branches and reintroduces the race this shape removes.
        """
        idle = timedelta(seconds=SESSION_IDLE_SECONDS)
        absolute = timedelta(seconds=SESSION_TTL_SECONDS)
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                WITH slid AS (
                    UPDATE sessions
                       SET expires_at = LEAST(now() + %(idle)s, created_at + %(absolute)s)
                     WHERE token_hash = %(token_hash)s
                       AND expires_at > now()
                       AND created_at + %(absolute)s > now()
                 RETURNING user_id
                )
                SELECT u.id, u.email, u.password_hash, u.onboarded_at, u.org_id, u.roles
                  FROM slid
                  JOIN users u ON u.id = slid.user_id
                """,
                {"idle": idle, "absolute": absolute, "token_hash": _hash_token(token)},
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return User(**{**row, "roles": tuple(row["roles"] or ())})

    async def delete_session(self, token: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "DELETE FROM sessions WHERE token_hash = %s", (_hash_token(token),)
            )

    async def delete_expired_sessions(self) -> int:
        async with self.pool.connection() as conn:
            cursor = await conn.execute("DELETE FROM sessions WHERE expires_at <= now()")
            return cursor.rowcount

    # ── lines ─────────────────────────────────────────────────────────────

    async def create_line(
        self, user_id: str, org_id: str, name: str, *, is_walkthrough: bool = False
    ) -> Line:
        """Both ids: `user_id` is who made it, `org_id` is who may see it."""
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                INSERT INTO product_lines (id, user_id, org_id, name, is_walkthrough)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, user_id, org_id, name, created_at, updated_at, revision, profile
                """,
                (new_id(), user_id, org_id, name, is_walkthrough),
            )
            row = await cursor.fetchone()
        return Line(**row)

    async def lines_for_user(self, org_id: str) -> list[Line]:
        """The organisation's lines. **The walkthrough is not one of them.**

        `is_walkthrough` marks scaffolding, not user data: `ensure_walkthrough` creates it,
        `/design/demo` replays into it, and the help button in the rail is how anyone
        reaches it. Listing it beside real work offered a delete affordance on a row the
        product depends on — and deleting it is exactly what was done while tidying the
        demo account before a live pitch.

        Nothing breaks when it goes: `ensure_walkthrough` recreates the line and thread
        from ids derived off the user, so the tour still works after a delete. But a
        dashboard whose first row is a tour the user has already finished is also just
        noise, and hiding it is what makes a fresh account's dashboard honestly empty.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_id, org_id, name, created_at, updated_at, revision, profile,
                       (SELECT count(*) FROM line_parts lp
                        WHERE lp.line_id = product_lines.id AND lp.populated) AS part_count
                  FROM product_lines WHERE org_id = %s AND NOT is_walkthrough
                 ORDER BY updated_at DESC
                """,
                (org_id,),
            )
            rows = await cursor.fetchall()
        return [Line(**row) for row in rows]

    async def line_for_user(self, line_id: str, org_id: str) -> Line | None:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_id, org_id, name, created_at, updated_at, revision, profile,
                       (SELECT count(*) FROM line_parts lp
                        WHERE lp.line_id = product_lines.id AND lp.populated) AS part_count
                  FROM product_lines WHERE id = %s AND org_id = %s
                """,
                (line_id, org_id),
            )
            row = await cursor.fetchone()
        return None if row is None else Line(**row)

    async def save_bom_rows(
        self, line_id: str, user_id: str, org_id: str, rows: Sequence[Mapping[str, Any]]
    ) -> None:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM line_parts WHERE line_id = %s AND org_id = %s",
                    (line_id, org_id),
                )
                cursor = conn.cursor()
                await cursor.executemany(
                    """INSERT INTO line_parts
                       (line_id, user_id, org_id, refdes, mpn, manufacturer, footprint, populated)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (
                            line_id, user_id, org_id, row["refdes"], row["mpn"],
                            row.get("manufacturer"), row.get("footprint"),
                            row.get("populated", True),
                        )
                        for row in rows
                    ],
                )

    async def bom_for_line(self, line_id: str, org_id: str) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """SELECT refdes, mpn, manufacturer, footprint, populated
                     FROM line_parts WHERE line_id = %s AND org_id = %s ORDER BY refdes""",
                (line_id, org_id),
            )
            return await cursor.fetchall()

    async def save_profile(
        self, line_id: str, org_id: str, profile: OperatingProfile, revision: str
    ) -> bool:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """UPDATE product_lines SET profile = %s, revision = %s, updated_at = now()
                   WHERE id = %s AND org_id = %s""",
                (Json(profile.to_json()), revision, line_id, org_id),
            )
            return cursor.rowcount > 0

    async def lines_exposed_to(self, org_id: str, mpn: str) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """SELECT p.id AS line_id, p.name, p.revision,
                          array_agg(lp.refdes ORDER BY lp.refdes) AS refdes
                     FROM line_parts lp
                     JOIN product_lines p ON p.id = lp.line_id AND p.org_id = lp.org_id
                    WHERE lp.org_id = %s AND lp.mpn = %s AND lp.populated
                 GROUP BY p.id, p.name, p.revision ORDER BY p.name""",
                (org_id, mpn),
            )
            return await cursor.fetchall()

    async def ensure_scratch_line(self, user_id: str, org_id: str) -> str:
        """The account's visible, reusable home for runs started without a line.

        Keyed by the *person*, not the company: a scratch pad is where you try something
        before it is anyone else's business, and one shared scratch line per organisation
        would put a colleague's half-finished experiment on your dashboard. It still
        carries `org_id`, because a row an org-scoped read cannot see is a row that has
        effectively vanished.

        The id is derived from the account, so React's development double requests use
        the same insert and `ON CONFLICT DO NOTHING` keeps them to one line.
        """
        line_id = _derived_id(user_id, "scratch-line")

        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO product_lines (id, user_id, org_id, name)
                VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
                (line_id, user_id, org_id, SCRATCH_LINE_NAME),
            )

        return line_id

    async def ensure_walkthrough(self, user_id: str, org_id: str, prompt: str) -> str:
        """The account's one walkthrough thread, creating it if it is not there yet.

        Returns the thread id. **Safe to call concurrently**, which it has to be: React
        re-runs effects in development, so two requests arrive within a millisecond of
        each other and a find-then-create loses the race with itself — every new account
        ended up with two "Welcome to Continuity" lines, the first abandoned mid-stream.

        Both ids are derived from the user id rather than random, so the two callers
        compute the *same* rows and `ON CONFLICT DO NOTHING` settles it without a lock.
        """
        line_id = _derived_id(user_id, "walkthrough-line")
        thread_id = _derived_id(user_id, "walkthrough-thread")

        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO product_lines (id, user_id, org_id, name, is_walkthrough)
                VALUES (%s, %s, %s, %s, true) ON CONFLICT (id) DO NOTHING
                """,
                (line_id, user_id, org_id, WALKTHROUGH_LINE_NAME),
            )
            await conn.execute(
                """
                INSERT INTO threads (id, line_id, user_id, org_id, prompt)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
                (thread_id, line_id, user_id, org_id, prompt),
            )

        return thread_id

    async def walkthrough_thread_for_user(self, user_id: str) -> Thread | None:
        """The walkthrough this *person* has already been given, if any.

        `user_id`, deliberately, where its neighbours moved to `org_id`: everyone is shown
        the tour once, and finding a colleague's would hand a new starter a finished
        walkthrough and skip the only run the product explains itself with.

        `/design/demo` is reached more than once — React re-runs effects in development,
        and a refresh mid-tour would do it too — so it looks here first and replays into
        the thread it already made rather than creating another.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT t.id, t.line_id, t.user_id, t.org_id, t.prompt, t.status,
                       t.last_seq, t.bom, t.summary
                  FROM threads t
                  JOIN product_lines p ON p.id = t.line_id
                 WHERE t.user_id = %s AND p.is_walkthrough
                 ORDER BY t.created_at
                 LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
        return None if row is None else Thread(**row)

    async def rename_line(self, line_id: str, org_id: str, name: str) -> bool:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "UPDATE product_lines SET name = %s, updated_at = now() "
                "WHERE id = %s AND org_id = %s",
                (name, line_id, org_id),
            )
            return cursor.rowcount > 0

    async def delete_line(self, line_id: str, org_id: str) -> bool:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM product_lines WHERE id = %s AND org_id = %s", (line_id, org_id)
            )
            return cursor.rowcount > 0

    # ── threads ──────────────────────────────────────────────────────────────

    async def create_thread(
        self, thread_id: str, line_id: str, user_id: str, org_id: str, prompt: str
    ) -> None:
        """Both ids: `user_id` is who started this run, `org_id` is who may see it."""
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO threads (id, line_id, user_id, org_id, prompt)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (thread_id, line_id, user_id, org_id, prompt),
            )
            await conn.execute(
                "UPDATE product_lines SET updated_at = now() WHERE id = %s", (line_id,)
            )

    async def thread_for_user(self, thread_id: str, org_id: str) -> Thread | None:
        """The authorisation boundary for `/resume`, `/export` and `/board`.

        Organisation, not person: an end-of-life review is three departments looking at
        one run, and this returning `None` for the second of them was the whole reason
        the concept had to move. **Membership is necessary and not sufficient** — item 11b
        adds the check for whether this particular person may answer this particular
        question, which membership alone cannot decide.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, line_id, user_id, org_id, prompt, status, last_seq, bom, summary
                  FROM threads WHERE id = %s AND org_id = %s
                """,
                (thread_id, org_id),
            )
            row = await cursor.fetchone()
        return None if row is None else Thread(**row)

    async def threads_for_line(self, line_id: str, org_id: str) -> list[Thread]:
        """Most relevant run first — which is not always the newest one.

        React's development double-invoke starts two runs half a millisecond apart. The
        second is cancelled immediately and ends `abandoned` at `last_seq = -1`, having
        emitted nothing, while the first goes on to do the actual work. Ordering by
        `created_at` alone therefore hands the caller the empty twin: a line sitting on
        an unanswered question opened to *"this run has no board to restore"*, because the
        run being restored was the phantom rather than the one holding the board.

        So: a run in flight first, then any run that actually emitted a frame, then newest.
        `last_seq = -1` means nothing was ever sent, which is the honest definition of a
        thread with no run behind it.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, line_id, user_id, org_id, prompt, status, last_seq, bom, summary
                  FROM threads WHERE line_id = %s AND org_id = %s
                 ORDER BY (status = 'running') DESC, (last_seq >= 0) DESC, created_at DESC
                """,
                (line_id, org_id),
            )
            rows = await cursor.fetchall()
        return [Thread(**row) for row in rows]

    async def save_progress(self, thread_id: str, last_seq: int, status: str) -> None:
        """Written when a stream ends — which is exactly when a resume becomes possible."""
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                UPDATE threads SET last_seq = %s, status = %s, updated_at = now()
                 WHERE id = %s
                """,
                (last_seq, status, thread_id),
            )

    async def save_summary(self, thread_id: str, summary: dict[str, Any]) -> None:
        """What the engine said about the finished board, stored as it was emitted.

        Not recomputed here and not recomputed by whoever reads it. `conflicts_resolved`
        counts repairs the graph actually applied — a waived fault is deliberately not in
        it — and a dashboard that re-derived any of this from the BOM would be inventing
        a second opinion the engine never gave.
        """
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE threads SET summary = %s, updated_at = now() WHERE id = %s",
                (Json(summary), thread_id),
            )

    async def save_bom(self, thread_id: str, rows: list[dict[str, Any]]) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE threads SET bom = %s, updated_at = now() WHERE id = %s",
                (Json(rows), thread_id),
            )

    async def save_run_events(self, thread_id: str, events: Sequence[dict[str, Any]]) -> None:
        """Append compact stream frames once; duplicate sequence numbers are harmless."""
        rows = [
            (thread_id, event["seq"], Json(event))
            for event in events
            if event.get("type") != "bom" and isinstance(event.get("seq"), int)
        ]
        if not rows:
            return
        async with self.pool.connection() as conn:
            cursor = conn.cursor()
            await cursor.executemany(
                """
                INSERT INTO run_events (thread_id, seq, event) VALUES (%s, %s, %s)
                ON CONFLICT (thread_id, seq) DO NOTHING
                """,
                rows,
            )

    async def run_events(self, thread_id: str) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                "SELECT event FROM run_events WHERE thread_id = %s ORDER BY seq", (thread_id,)
            )
            rows = await cursor.fetchall()
        return [row["event"] for row in rows]

    async def save_findings(self, thread_id: str, findings: list[Finding]) -> None:
        """Replace this completed run's recorded observations atomically enough to retry."""
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM findings WHERE thread_id = %s", (thread_id,))
            for finding in findings:
                await conn.execute(
                    """
                    INSERT INTO findings (
                        id, thread_id, line_id, user_id, org_id, rule, slot, mpn, manufacturer,
                        lifecycle, verdict, outcome, action, replacement_mpn, signature, worked
                    )
                    SELECT %s, t.id, t.line_id, t.user_id, t.org_id,
                           %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                      FROM threads t
                     WHERE t.id = %s
                    """,
                    (
                        new_id(),
                        finding.rule,
                        finding.slot,
                        finding.mpn,
                        finding.manufacturer,
                        finding.lifecycle,
                        finding.verdict,
                        finding.outcome,
                        finding.action,
                        finding.replacement_mpn,
                        finding.signature,
                        finding.worked,
                        thread_id,
                    ),
                )

    async def precedents_for_user(
        self, org_id: str, signature: str, *, exclude_thread: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Repairs this *company* has already made to a structurally identical conflict.

        Widened from the person to the organisation with the ownership move, and that is
        the point rather than a consequence: a precedent is worth more the more boards it
        was drawn from, and "somebody here solved this exact conflict before" is the
        question a company can answer and a desk cannot.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT f.rule, f.action, f.signature, p.name AS line_name
                  FROM findings f
                  JOIN product_lines p ON p.id = f.line_id AND p.org_id = f.org_id
                 WHERE f.org_id = %s
                   AND f.signature = %s
                   AND f.thread_id <> %s
                   AND f.worked IS TRUE
                   AND f.outcome = 'repaired'
              ORDER BY f.created_at DESC
                 LIMIT %s
                """,
                (org_id, signature, exclude_thread, limit),
            )
            return await cursor.fetchall()

    async def memory_for_user(self, org_id: str, *, part_limit: int) -> dict[str, Any]:
        """The bounded line/part graph, with every read constrained at the boundary."""
        async with self.pool.connection() as conn:
            lines_cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT p.id, p.name, COUNT(t.id)::integer AS boards
                  FROM product_lines p
             LEFT JOIN threads t ON t.line_id = p.id AND t.org_id = p.org_id
                 WHERE p.org_id = %s
              GROUP BY p.id, p.name
              ORDER BY p.updated_at DESC
                """,
                (org_id,),
            )
            line_rows = await lines_cursor.fetchall()
            bom_cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT t.line_id, p.name AS line_name,
                       item->>'mpn' AS mpn, item->>'manufacturer' AS manufacturer,
                       item->>'lifecycle' AS lifecycle
                  FROM threads t
                  JOIN product_lines p ON p.id = t.line_id AND p.org_id = t.org_id
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.bom, '[]'::jsonb)) AS item
                 WHERE t.org_id = %s AND NULLIF(item->>'mpn', '') IS NOT NULL
                """,
                (org_id,),
            )
            bom_rows = await bom_cursor.fetchall()
            findings_cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT f.thread_id, f.line_id, p.name AS line_name, f.rule, f.slot,
                       f.mpn, f.manufacturer, f.lifecycle, f.verdict, f.outcome, f.action,
                       f.replacement_mpn
                  FROM findings f
                  JOIN threads t ON t.id = f.thread_id AND t.org_id = f.org_id
                  JOIN product_lines p ON p.id = f.line_id AND p.org_id = f.org_id
                 WHERE f.org_id = %s
                """,
                (org_id,),
            )
            finding_rows = await findings_cursor.fetchall()
            mpns = sorted(
                {
                    row["mpn"]
                    for row in [*bom_rows, *finding_rows]
                    if isinstance(row["mpn"], str) and row["mpn"]
                }
            )
            fact_rows: list[dict[str, Any]] = []
            if mpns:
                facts_cursor = await conn.cursor(row_factory=dict_row).execute(
                    """
                    SELECT mpn, field, value, source
                      FROM part_facts
                     WHERE mpn = ANY(%s)
                  ORDER BY mpn, field
                    """,
                    (mpns,),
                )
                fact_rows = await facts_cursor.fetchall()

        facts_by_mpn: dict[str, list[dict[str, Any]]] = {}
        for row in fact_rows:
            facts_by_mpn.setdefault(row["mpn"], []).append(
                {"field": row["field"], "value": row["value"], "source": row["source"]}
            )
        parts: dict[str, dict[str, Any]] = {}
        for row in bom_rows:
            part = parts.setdefault(
                row["mpn"],
                {
                    "mpn": row["mpn"],
                    "manufacturer": row["manufacturer"],
                    "lifecycle": row["lifecycle"],
                    "used_in": {},
                    "findings": [],
                    "facts": facts_by_mpn.get(row["mpn"], []),
                },
            )
            if part["manufacturer"] is None:
                part["manufacturer"] = row["manufacturer"]
            if part["lifecycle"] is None:
                part["lifecycle"] = row["lifecycle"]
            part["used_in"][row["line_id"]] = {
                "line_id": row["line_id"],
                "line_name": row["line_name"],
            }
        for row in finding_rows:
            part = parts.setdefault(
                row["mpn"],
                {
                    "mpn": row["mpn"],
                    "manufacturer": row["manufacturer"],
                    "lifecycle": row["lifecycle"],
                    "used_in": {},
                    "findings": [],
                    "facts": facts_by_mpn.get(row["mpn"], []),
                },
            )
            if part["manufacturer"] is None:
                part["manufacturer"] = row["manufacturer"]
            if part["lifecycle"] is None:
                part["lifecycle"] = row["lifecycle"]
            part["findings"].append(
                {
                    "thread_id": row["thread_id"],
                    "line_id": row["line_id"],
                    "line_name": row["line_name"],
                    "rule": row["rule"],
                    "slot": row["slot"],
                    "verdict": row["verdict"],
                    "outcome": row["outcome"],
                    "action": row["action"],
                    "replacement_mpn": row["replacement_mpn"],
                }
            )

        ordered = sorted(
            parts.values(),
            key=lambda part: (-bool(part["findings"]), -len(part["used_in"]), part["mpn"]),
        )
        capped = len(ordered) > part_limit
        return {
            "lines": line_rows,
            "parts": [
                {
                    **part,
                    "used_in": sorted(part["used_in"].values(), key=lambda edge: edge["line_name"]),
                }
                for part in ordered[:part_limit]
            ],
            "parts_capped": capped,
            "part_limit": part_limit,
        }
    # ── the standing lists, and what was decided against them ────────────────

    async def approved_lists(self, org_id: str) -> ApprovedLists:
        """The AML and AVL in force for this organisation.

        `None` for a list the organisation does not keep, and an empty `frozenset` for one
        it keeps and has approved nothing on. Those are different answers and the rules
        report them differently — an organisation that has never set an AML must not have
        every part on every board reported unqualified.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                "SELECT keeps_aml, keeps_avl FROM organisations WHERE id = %s", (org_id,)
            )
            keeps = await cursor.fetchone()
            if keeps is None:
                return ApprovedLists()

            parts = vendors = None
            if keeps["keeps_aml"]:
                cursor = await conn.execute(
                    "SELECT mpn FROM approved_parts WHERE org_id = %s", (org_id,)
                )
                parts = frozenset(row[0].upper() for row in await cursor.fetchall())
            if keeps["keeps_avl"]:
                cursor = await conn.execute(
                    "SELECT distributor FROM approved_vendors WHERE org_id = %s", (org_id,)
                )
                vendors = frozenset(row[0].upper() for row in await cursor.fetchall())

        return ApprovedLists(parts=parts, vendors=vendors)

    async def keep_lists(
        self, org_id: str, *, aml: bool | None = None, avl: bool | None = None
    ) -> None:
        """Declare that this organisation keeps a list, which is what turns the gate on."""
        sets, params = [], []
        if aml is not None:
            sets.append("keeps_aml = %s")
            params.append(aml)
        if avl is not None:
            sets.append("keeps_avl = %s")
            params.append(avl)
        if not sets:
            return
        async with self.pool.connection() as conn:
            await conn.execute(
                f"UPDATE organisations SET {', '.join(sets)} WHERE id = %s", (*params, org_id)
            )

    async def qualify_part(
        self, org_id: str, mpn: str, *, manufacturer: str | None = None,
        by: str | None = None, note: str | None = None,
    ) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO approved_parts (org_id, mpn, manufacturer, qualified_by, note)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (org_id, mpn) DO UPDATE
                   SET manufacturer = EXCLUDED.manufacturer, note = EXCLUDED.note
                """,
                (org_id, mpn, manufacturer, by, note),
            )

    async def approve_vendor(
        self, org_id: str, distributor: str, *, by: str | None = None, note: str | None = None
    ) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO approved_vendors (org_id, distributor, approved_by, note)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (org_id, distributor) DO UPDATE SET note = EXCLUDED.note
                """,
                (org_id, distributor, by, note),
            )

    async def record_approval(
        self,
        *,
        org_id: str,
        thread_id: str,
        user_id: str | None,
        user_email: str,
        roles: Sequence[str],
        rule: str,
        subject: str,
        mpn: str | None,
        revision: str | None,
        rationale: str,
    ) -> str:
        """Who decided, when, on what, and why — the four things a waiver has to carry.

        Written where the decision is *made* rather than derived from a trace afterwards:
        a run's frames say a finding was accepted, and only the request that accepted it
        knows who was holding the keyboard.
        """
        approval_id = new_id()
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO approvals (
                    id, org_id, thread_id, user_id, user_email, roles,
                    rule, subject, mpn, revision, rationale
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    approval_id, org_id, thread_id, user_id, user_email, list(roles),
                    rule, subject, mpn, revision, rationale,
                ),
            )
        return approval_id

    async def approvals_for_thread(self, thread_id: str, org_id: str) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_email, roles, rule, subject, mpn, revision, rationale,
                       created_at
                  FROM approvals WHERE thread_id = %s AND org_id = %s
                 ORDER BY created_at
                """,
                (thread_id, org_id),
            )
            return await cursor.fetchall()

    # ── change notices ───────────────────────────────────────────────────────

    async def save_notice(
        self, org_id: str, user_id: str | None, notice: Any, *, source: str
    ) -> str:
        """Persist what a notice said, with the lines it was believed on.

        `source` records how it arrived — a mailbox, or the endpoint the demo posts to —
        because "where did this come from" is the first question anybody asks of a change
        that a machine started.
        """
        notice_id = new_id()
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO notices (
                    id, org_id, user_id, mpn, mpn_line, manufacturer, effective_date,
                    effective_date_line, replacement_mpn, replacement_line, reason, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    notice_id, org_id, user_id, notice.mpn, notice.mpn_line,
                    notice.manufacturer, notice.effective_date, notice.effective_date_line,
                    notice.replacement_mpn, notice.replacement_line, notice.reason, source,
                ),
            )
        return notice_id

    async def notice_for_org(self, notice_id: str, org_id: str) -> dict[str, Any] | None:
        """One notice, by id, scoped to the organisation that received it.

        A direct read rather than a scan of the recent ones: reviewing a notice older than
        whatever page size the listing happened to use would fail with "no such notice"
        about a notice plainly on screen.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, mpn, mpn_line, manufacturer, effective_date, replacement_mpn,
                       reason, source, created_at
                  FROM notices WHERE id = %s AND org_id = %s
                """,
                (notice_id, org_id),
            )
            return await cursor.fetchone()

    async def notices_for_org(self, org_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, mpn, mpn_line, manufacturer, effective_date, replacement_mpn,
                       reason, source, created_at
                  FROM notices WHERE org_id = %s ORDER BY created_at DESC LIMIT %s
                """,
                (org_id, limit),
            )
            return await cursor.fetchall()

    # ── change requests ──────────────────────────────────────────────────────

    async def save_change_requests(
        self, org_id: str, user_id: str | None, notice_id: str | None, requests: Sequence[Any]
    ) -> list[str]:
        """Persist one request per line, together, so a set is never half-written."""
        ids: list[str] = []
        async with self.pool.connection() as conn:
            async with conn.transaction():
                for request in requests:
                    request_id = new_id()
                    ids.append(request_id)
                    await conn.execute(
                        """
                        INSERT INTO change_requests
                            (id, org_id, notice_id, line_id, user_id, proposal, document)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            request_id, org_id, notice_id, request.line_id, user_id,
                            request.proposal, Json(request.to_json()),
                        ),
                    )
        return ids

    async def change_requests_for_org(
        self, org_id: str, *, notice_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        where = "org_id = %s" + (" AND notice_id = %s" if notice_id else "")
        params: tuple[Any, ...] = (org_id, notice_id) if notice_id else (org_id,)
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                f"""
                SELECT id, notice_id, line_id, proposal, document, created_at
                  FROM change_requests WHERE {where}
                 ORDER BY created_at DESC LIMIT %s
                """,
                (*params, limit),
            )
            return await cursor.fetchall()

    async def save_part_facts(
        self, facts: Iterable[tuple[str, str, str, str | None]]
    ) -> None:
        """Upsert board-independent part properties learned during a run."""
        permitted = [
            (mpn, field, value, source)
            for mpn, field, value, source in facts
            if field in DOSSIER_FIELDS and value != ""
        ]
        if not permitted:
            return
        async with self.pool.connection() as conn:
            for mpn, field, value, source in permitted:
                await conn.execute(
                    """
                    INSERT INTO part_facts (mpn, field, value, source)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (mpn, field) DO UPDATE
                       SET value = EXCLUDED.value,
                           source = EXCLUDED.source,
                           observed_at = now()
                    """,
                    (mpn, field, value, source),
                )

    async def part_facts(self, mpns: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
        """Known facts for these parts, keyed by MPN."""
        requested = list(dict.fromkeys(mpn for mpn in mpns if mpn))
        if not requested:
            return {}
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT mpn, field, value, source
                  FROM part_facts
                 WHERE mpn = ANY(%s)
              ORDER BY mpn, field
                """,
                (requested,),
            )
            rows = await cursor.fetchall()
        facts: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            facts.setdefault(row["mpn"], []).append(
                {"field": row["field"], "value": row["value"], "source": row["source"]}
            )
        return facts
