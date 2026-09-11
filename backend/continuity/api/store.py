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
import json
import secrets
import uuid
from dataclasses import dataclass
from functools import partial
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from . import recall
from .findings import Finding
from ..engine.models import ApprovedLists
from ..parts.dossier import DOSSIER_FIELDS
from ..profile import OperatingProfile
from ..roles import roles_for_rule

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


ROLES = ("engineering", "procurement", "production", "quality")
"""Every role a person can hold. Checked wherever roles are set.

**Four desks, ordered as Scenario B orders them.** The topic names design, procurement and
production; quality is the fourth because the approved manufacturer list has to have an owner
and `part_qualification` is addressed to it. `production` was absent until 10 September, so
`roles.py` could route a rule to a department nobody could hold — `tests/test_roles.py` now
asserts both directions of that.

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

    exposed_count: int = 0
    """How many change notices reach a part this line has fitted.

    Also counted beside the row, and for a stronger reason than the parts were: this is the
    only thing on a dashboard of shipping products that is *about to change*, so it decides
    what the row says. The dashboard used to caption every product with whether somebody had
    designed it from a brief inside our tool, which is not a fact about the product."""


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


LEGACY_WALKTHROUGH_LINE_NAME = "Welcome to Continuity"
"""The name the replayed tour's line was created under, before the tour was removed.

Kept only so the filter below reads as something rather than as a magic column."""
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
                cursor = await conn.execute(
                    "SELECT org_id FROM users WHERE id = %s", (user_id,)
                )
                row = await cursor.fetchone()
                previous = row[0] if row else None

                await conn.execute(
                    "UPDATE users SET org_id = %s, roles = %s WHERE id = %s",
                    (org_id, list(roles), user_id),
                )
                # `line_access` is on this list for the same reason the rest are: a grant
                # whose `org_id` still names the company they left is a row that says
                # something untrue. The visibility query matches on `user_id`, so leaving it
                # behind would not hide anything today — which is exactly the kind of stale
                # field that gets trusted later.
                for table in ("product_lines", "threads", "findings", "line_parts", "line_access"):
                    await conn.execute(
                        f"UPDATE {table} SET org_id = %s WHERE user_id = %s", (org_id, user_id)
                    )
                if previous is not None and previous != org_id:
                    await self._drop_if_vacated(conn, previous)

    async def _drop_if_vacated(self, conn: Any, org_id: str) -> None:
        """Remove an organisation the last person just left, if nothing is left in it.

        Signing up creates a company of one, so joining a real one abandons it — an empty
        organisation with no members and no work, accumulating one per join and visible to
        nobody. The seed found this by leaving three behind for two people.

        Every check is explicit rather than left to the foreign keys, because most of them
        cascade: a `DELETE` that guessed wrong would take the lines, threads, decisions and
        notices with it rather than being refused.
        """
        cursor = await conn.execute(
            """
            SELECT (SELECT count(*) FROM users WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM product_lines WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM threads WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM findings WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM line_parts WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM line_access WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM approvals WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM notices WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM change_requests WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM precedents WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM approved_parts WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM approved_vendors WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM line_boards WHERE org_id = %(org)s)
                 + (SELECT count(*) FROM decisions WHERE org_id = %(org)s)
            """,
            {"org": org_id},
        )
        (remaining,) = await cursor.fetchone()
        if remaining == 0:
            await conn.execute("DELETE FROM organisations WHERE id = %s", (org_id,))

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
        self, user_id: str, org_id: str, name: str
    ) -> Line:
        """Both ids: `user_id` is who made it, `org_id` is who may see it.

        **Whoever makes a line is on it.** The grant is written in the same transaction as
        the line, because a product line its own author cannot open is a row that has
        effectively vanished — and it is the failure this would have had, since visibility
        is a grant now rather than a property of the company. Sharing it onward is
        `grant_lines`.
        """
        line_id = new_id()
        async with self.pool.connection() as conn:
            async with conn.transaction():
                cursor = await conn.cursor(row_factory=dict_row).execute(
                    """
                    INSERT INTO product_lines (id, user_id, org_id, name)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, user_id, org_id, name, created_at, updated_at, revision, profile
                    """,
                    (line_id, user_id, org_id, name),
                )
                row = await cursor.fetchone()
                await conn.execute(
                    "INSERT INTO line_access (line_id, user_id, org_id) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (line_id, user_id, org_id),
                )
        return Line(**row)

    async def lines_for_user(self, org_id: str, user_id: str) -> list[Line]:
        """The lines this person was brought in on.

        **`NOT is_walkthrough` outlives the walkthrough itself.** The replayed tour is gone
        — it taught a story the product no longer tells — and nothing writes that column any
        more, but an account created before it went still carries a "Welcome to Continuity"
        row. The filter keeps those hidden; dropping the column would be a migration against
        production data for a change nobody would see.

        **`user_id` is required, and that is the point.** It used to be `org_id` alone, which
        answers *is this your company's work* and cannot answer *is this yours*. Every caller
        has to say whose eyes it is asking for, so a caller that forgot cannot quietly widen
        what somebody sees — it stops at the type error instead.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_id, org_id, name, created_at, updated_at, revision, profile,
                       (SELECT count(*) FROM line_parts lp
                        WHERE lp.line_id = product_lines.id AND lp.populated) AS part_count,
                       (SELECT count(DISTINCT n.id)
                          FROM notices n
                          JOIN line_parts lp ON lp.mpn = n.mpn AND lp.org_id = n.org_id
                                            AND lp.populated
                         WHERE n.org_id = product_lines.org_id
                           AND lp.line_id = product_lines.id) AS exposed_count
                  FROM product_lines
                 WHERE org_id = %s AND NOT is_walkthrough
                   AND EXISTS (SELECT 1 FROM line_access a
                                WHERE a.line_id = product_lines.id AND a.user_id = %s)
                 ORDER BY updated_at DESC
                """,
                (org_id, user_id),
            )
            rows = await cursor.fetchall()
        return [Line(**row) for row in rows]

    async def line_for_user(self, line_id: str, org_id: str, user_id: str) -> Line | None:
        """One line, if this person was brought in on it. The authorisation boundary.

        `None` covers both "no such line" and "not yours", deliberately: a caller who has not
        been invited to a project should not be able to tell it apart from one that does not
        exist, because the difference is a list of somebody else's projects.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_id, org_id, name, created_at, updated_at, revision, profile,
                       (SELECT count(*) FROM line_parts lp
                        WHERE lp.line_id = product_lines.id AND lp.populated) AS part_count
                  FROM product_lines
                 WHERE id = %s AND org_id = %s
                   AND EXISTS (SELECT 1 FROM line_access a
                                WHERE a.line_id = product_lines.id AND a.user_id = %s)
                """,
                (line_id, org_id, user_id),
            )
            row = await cursor.fetchone()
        return None if row is None else Line(**row)

    async def lines_in_org(self, org_id: str) -> list[Line]:
        """Every line this company ships, whoever holds it.

        For the startup warm and nothing else: it checks every product line so the first
        person to open one is not the person who waits. No route may use this.
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

    async def line_in_org(self, line_id: str, org_id: str) -> Line | None:
        """One line with no access question asked.

        **For the two callers that legitimately mean the whole company**, and for nothing
        else. The startup warm checks every product line so the first person to open one is
        not the person who waits; the engine's own cached check is asked about a line whose
        access was already decided at the route above it. Neither is speaking for a person,
        which is why neither may use `line_for_user`.
        """
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

    async def grant_lines(self, line_ids: Sequence[str], user_id: str, org_id: str) -> int:
        """Bring somebody in on these projects. Idempotent, and silent about duplicates.

        Re-inviting a person to a project they already hold is not an error and is not a
        second row: the invite is a statement about access, and access is a set.
        """
        if not line_ids:
            return 0
        async with self.pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(
                    """
                    INSERT INTO line_access (line_id, user_id, org_id)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    [(line_id, user_id, org_id) for line_id in line_ids],
                )
                return cursor.rowcount

    async def members_for_org(self, org_id: str) -> list[dict[str, Any]]:
        """Who is in this company, what they hold, and how much they can reach.

        The count is of lines they were *brought in on*, which is the same number their own
        product lines list shows. A roster that counted the company's lines instead would
        print five beside somebody who can open two.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT u.id, u.email, u.roles, u.created_at,
                       coalesce(
                           array_agg(a.line_id ORDER BY a.created_at) FILTER (WHERE a.line_id IS NOT NULL),
                           '{}'
                       ) AS line_ids
                  FROM users u
                  LEFT JOIN line_access a ON a.user_id = u.id AND a.org_id = u.org_id
                 WHERE u.org_id = %s
                 GROUP BY u.id, u.email, u.roles, u.created_at
                 ORDER BY u.created_at
                """,
                (org_id,),
            )
            return await cursor.fetchall()

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

    async def lines_exposed_to(
        self, org_id: str, mpn: str, user_id: str
    ) -> list[dict[str, Any]]:
        """Which of *this person's* lines carry the part.

        **The same grant as the product lines list narrows this**, because a notice that
        reported three affected products to somebody who can open two would be announcing
        work they cannot see. The count on the banner and the boards the review checks come
        from here, so they narrow together.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """SELECT p.id AS line_id, p.name, p.revision,
                          array_agg(lp.refdes ORDER BY lp.refdes) AS refdes
                     FROM line_parts lp
                     JOIN product_lines p ON p.id = lp.line_id AND p.org_id = lp.org_id
                    WHERE lp.org_id = %s AND lp.mpn = %s AND lp.populated
                      AND EXISTS (SELECT 1 FROM line_access a
                                   WHERE a.line_id = p.id AND a.user_id = %s)
                 GROUP BY p.id, p.name, p.revision ORDER BY p.name""",
                (org_id, mpn, user_id),
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
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO product_lines (id, user_id, org_id, name)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                    """,
                    (line_id, user_id, org_id, SCRATCH_LINE_NAME),
                )
                # Granted to its owner for the same reason `create_line` does it: a scratch
                # line nobody can open is the pad a run started without a line writes into.
                await conn.execute(
                    "INSERT INTO line_access (line_id, user_id, org_id) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (line_id, user_id, org_id),
                )

        return line_id

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
        """Everything this company knows about the parts it ships.

        Rebuilt 8 Sep on the record rather than on design runs. It used to read
        `threads.bom` and join every finding through `threads`, so a company that had
        never opened the design side had an empty memory while carrying five product
        lines, three change notices and a settled substitution.

        The reads are ordered by how much each source knows about a part, because
        `recall.compose` lets the first non-empty answer stand: a bill of materials states
        the manufacturer the company actually buys, and a design run's parts list is a
        weaker source for the same field.
        """
        async with self.pool.connection() as conn:
            read = partial(self._rows, conn, org_id)
            lines = await read(
                """
                SELECT p.id, p.name, p.revision,
                       COUNT(lp.refdes)::integer AS parts
                  FROM product_lines p
             LEFT JOIN line_parts lp ON lp.line_id = p.id AND lp.org_id = p.org_id
                 WHERE p.org_id = %s
              GROUP BY p.id, p.name, p.revision, p.updated_at
              ORDER BY p.updated_at DESC
                """
            )
            bom = await read(
                """
                SELECT lp.line_id, p.name AS line_name, lp.mpn, lp.manufacturer,
                       array_agg(lp.refdes ORDER BY lp.refdes) AS refdes
                  FROM line_parts lp
                  JOIN product_lines p ON p.id = lp.line_id AND p.org_id = lp.org_id
                 WHERE lp.org_id = %s AND lp.populated
              GROUP BY lp.line_id, p.name, lp.mpn, lp.manufacturer
                """
            )
            notices = await read(
                """
                SELECT mpn, mpn_line, manufacturer, effective_date, effective_date_line,
                       replacement_mpn, replacement_line, reason, source, created_at
                  FROM notices WHERE org_id = %s ORDER BY created_at DESC
                """
            )
            precedents = await read(
                """
                SELECT pr.mpn, pr.line_id, l.name AS line_name, pr.outcome, pr.detail,
                       pr.signature, pr.recorded_at
                  FROM precedents pr
                  JOIN product_lines l ON l.id = pr.line_id AND l.org_id = pr.org_id
                 WHERE pr.org_id = %s ORDER BY pr.recorded_at DESC
                """
            )
            approvals = await read(
                """
                SELECT a.mpn, a.line_id, l.name AS line_name, a.user_email, a.roles,
                       a.rule, a.subject, a.revision, a.rationale, a.created_at
                  FROM approvals a
             LEFT JOIN product_lines l ON l.id = a.line_id AND l.org_id = a.org_id
                 WHERE a.org_id = %s AND NULLIF(a.mpn, '') IS NOT NULL
              ORDER BY a.created_at DESC
                """
            )
            decisions = await read(
                """
                SELECT d.proposal, d.retiring, d.line_id, l.name AS line_name, d.state,
                       d.roles, d.gate_rule, d.slot_id, d.detail, d.created_at
                  FROM decisions d
                  JOIN product_lines l ON l.id = d.line_id AND l.org_id = d.org_id
                 WHERE d.org_id = %s ORDER BY d.created_at DESC
                """
            )
            thread_parts = await read(
                """
                SELECT t.line_id, p.name AS line_name,
                       item->>'mpn' AS mpn, item->>'manufacturer' AS manufacturer,
                       item->>'lifecycle' AS lifecycle
                  FROM threads t
                  JOIN product_lines p ON p.id = t.line_id AND p.org_id = t.org_id
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.bom, '[]'::jsonb)) AS item
                 WHERE t.org_id = %s AND NULLIF(item->>'mpn', '') IS NOT NULL
                """
            )
            findings = await read(
                """
                SELECT f.thread_id, f.line_id, p.name AS line_name, f.rule, f.slot,
                       f.mpn, f.manufacturer, f.lifecycle, f.verdict, f.outcome, f.action,
                       f.replacement_mpn
                  FROM findings f
                  JOIN threads t ON t.id = f.thread_id AND t.org_id = f.org_id
                  JOIN product_lines p ON p.id = f.line_id AND p.org_id = f.org_id
                 WHERE f.org_id = %s
                """
            )
            mpns = recall.mpns_in(
                bom, thread_parts, findings, notices, precedents, approvals,
                decisions, fields=("mpn", "replacement_mpn", "proposal", "retiring"),
            )
            facts = await self._facts_for(conn, mpns)

        return recall.compose(
            lines=lines,
            bom=bom,
            notices=notices,
            precedents=precedents,
            approvals=approvals,
            decisions=decisions,
            thread_parts=thread_parts,
            findings=findings,
            facts=facts,
            part_limit=part_limit,
        )

    async def _rows(self, conn: Any, org_id: str, sql: str) -> list[dict[str, Any]]:
        cursor = await conn.cursor(row_factory=dict_row).execute(sql, (org_id,))
        return await cursor.fetchall()

    async def _facts_for(self, conn: Any, mpns: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
        """Verified datasheet readings for every part memory is about to mention.

        One read for all of them rather than one per part: memory shows up to
        `PART_LIMIT` parts and a query each would be that many round trips for a screen
        nobody is waiting on.
        """
        if not mpns:
            return {}
        cursor = await conn.cursor(row_factory=dict_row).execute(
            """
            SELECT mpn, field, value, source FROM part_facts
             WHERE mpn = ANY(%s) ORDER BY mpn, field
            """,
            (list(mpns),),
        )
        by_mpn: dict[str, list[dict[str, Any]]] = {}
        for row in await cursor.fetchall():
            by_mpn.setdefault(row["mpn"], []).append(
                {"field": row["field"], "value": row["value"], "source": row["source"]}
            )
        return by_mpn

    # ── where the mailbox poller got to ──────────────────────────────────────

    async def mail_cursor(self, org_id: str) -> tuple[str, int] | None:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT validity, uid FROM mail_cursor WHERE org_id = %s", (org_id,)
            )
            row = await cursor.fetchone()
            return (row[0], int(row[1])) if row else None

    async def save_mail_cursor(self, org_id: str, *, validity: str, uid: int) -> None:
        """Move the read position forward, never back.

        `GREATEST` rather than a plain assignment: two pollers, or a poll that overlaps a
        slow one, must not rewind the mailbox and re-read what has already been turned
        into notices.
        """
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO mail_cursor (org_id, validity, uid) VALUES (%s, %s, %s)
                ON CONFLICT (org_id) DO UPDATE
                   SET uid = CASE WHEN mail_cursor.validity = EXCLUDED.validity
                                  THEN GREATEST(mail_cursor.uid, EXCLUDED.uid)
                                  ELSE EXCLUDED.uid END,
                       validity = EXCLUDED.validity,
                       updated_at = now()
                """,
                (org_id, validity, uid),
            )

    async def every_organisation(self) -> list[str]:
        """Every company in this database. Only the startup warm asks: nothing a request
        serves is ever allowed to reach past the organisation it was authorised for."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute("SELECT id FROM organisations")
            return [row[0] for row in await cursor.fetchall()]

    async def only_organisation(self) -> str | None:
        """The one organisation, when there is exactly one.

        A mailbox belongs to a company and nothing in a message says which. Rather than
        attribute a notice to whichever account happens to be first, this answers only
        when the question has one answer, and `CONTINUITY_MAIL_ORG` settles it otherwise.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.execute("SELECT id FROM organisations LIMIT 2")
            rows = await cursor.fetchall()
            return rows[0][0] if len(rows) == 1 else None

    async def organisation_of(self, email: str) -> str | None:
        """The company a person belongs to, by their address."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute("SELECT org_id FROM users WHERE email = %s", (email,))
            row = await cursor.fetchone()
            return row[0] if row else None

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

    async def list_entries(self, org_id: str) -> dict[str, list[dict[str, Any]]]:
        """The AML and AVL as rows, with what each entry carries besides its name.

        `approved_lists` answers the rules, which match on names and need nothing else. A
        screen has to say who qualified a part and when, and a set of names cannot.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """SELECT mpn, manufacturer, qualified_by, note, created_at
                     FROM approved_parts WHERE org_id = %s ORDER BY mpn""",
                (org_id,),
            )
            parts = await cursor.fetchall()
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """SELECT distributor, approved_by, note, created_at
                     FROM approved_vendors WHERE org_id = %s ORDER BY distributor""",
                (org_id,),
            )
            vendors = await cursor.fetchall()
        return {"parts": parts, "vendors": vendors}

    async def shipped_parts(self, org_id: str) -> list[dict[str, Any]]:
        """Every part this company's bills carry, which is what an AML has to cover.

        The question an empty AML cannot answer is *what am I failing?*, and the answer is
        every fitted part on every line. This is also the list the one-action qualification
        works from, so that a company that has just declared a policy does not have to type
        its own bill of materials back in to satisfy it.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """SELECT DISTINCT mpn, manufacturer FROM line_parts
                    WHERE org_id = %s AND populated AND mpn IS NOT NULL AND mpn <> ''
                    ORDER BY mpn""",
                (org_id,),
            )
            return await cursor.fetchall()

    async def release_part(self, org_id: str, mpn: str) -> bool:
        """Take a part off the AML. True when there was something there to take off."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM approved_parts WHERE org_id = %s AND upper(mpn) = upper(%s)",
                (org_id, mpn),
            )
            return cursor.rowcount > 0

    async def release_vendor(self, org_id: str, distributor: str) -> bool:
        """Take a source off the AVL. True when there was something there to take off."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM approved_vendors "
                "WHERE org_id = %s AND upper(distributor) = upper(%s)",
                (org_id, distributor),
            )
            return cursor.rowcount > 0

    async def record_approval(
        self,
        *,
        org_id: str,
        thread_id: str | None = None,
        decision_id: str | None = None,
        line_id: str | None = None,
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
                    id, org_id, thread_id, decision_id, line_id, user_id, user_email, roles,
                    rule, subject, mpn, revision, rationale
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    approval_id, org_id, thread_id, decision_id, line_id, user_id,
                    user_email, list(roles), rule, subject, mpn, revision, rationale,
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

        **Returns the existing id when this company already holds this notice**, so the
        same PCN arriving twice is one change rather than two. See the comment below for
        what counts as the same one and why it is read rather than constrained.
        """
        notice_id = new_id()
        async with self.pool.connection() as conn:
            # The same change, however many copies of the document arrive. A PCN forwarded
            # to the mailbox and uploaded through the page is one thing to act on, and the
            # product line drew a banner per stored notice — so it showed two identical
            # banners with two REVIEW THIS LINE buttons.
            #
            # The three fields are what make it a *different* notice: the part, the date it
            # takes effect, and what it recommends instead. Those are exactly what
            # distinguishes the preliminary `PCN-2026-118` from the full `PCN-2026-114`,
            # which name the same part and must stay two notices. `IS NOT DISTINCT FROM`
            # rather than `=`, because a notice that names no date has NULL there and NULL
            # never equals NULL — which would make the preliminary one a new notice on
            # every arrival.
            #
            # Read then write rather than a unique index: two of these fields are nullable,
            # and a unique index over nullable columns needs `NULLS NOT DISTINCT`, which is
            # Postgres 15 and above. Nothing here races — a notice arrives from a person or
            # a poll, never from both at once.
            cursor = await conn.execute(
                """
                SELECT id FROM notices
                 WHERE org_id = %s
                   AND mpn = %s
                   AND effective_date IS NOT DISTINCT FROM %s
                   AND replacement_mpn IS NOT DISTINCT FROM %s
                 ORDER BY created_at
                 LIMIT 1
                """,
                (org_id, notice.mpn, notice.effective_date, notice.replacement_mpn),
            )
            already = await cursor.fetchone()
            if already is not None:
                # The first arrival stays the record, `source` included: how this change
                # first reached us is a fact about the change, and the second copy did not
                # change it.
                return already[0]

            await conn.execute(
                """
                INSERT INTO notices (
                    id, org_id, user_id, reference, reference_line, mpn, mpn_line, manufacturer, effective_date,
                    effective_date_line, replacement_mpn, replacement_line, reason, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    notice_id, org_id, user_id, notice.reference, notice.reference_line,
                    notice.mpn, notice.mpn_line,
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
                SELECT id, reference, reference_line, mpn, mpn_line, manufacturer, effective_date, replacement_mpn,
                       reason, source, review_skipped, review_trace, created_at
                  FROM notices WHERE id = %s AND org_id = %s
                """,
                (notice_id, org_id),
            )
            return await cursor.fetchone()

    async def record_review_trace(
        self, notice_id: str, org_id: str, frames: Sequence[Mapping[str, Any]]
    ) -> None:
        """Write down what the run streamed, in the order it streamed it.

        **Replaced, not appended to.** `RUN IT AGAIN` is the same question asked a second
        time, and the trace the page should show afterwards is the one that most recently
        happened rather than a concatenation of every run this notice has ever had.

        Written once at the end of the run rather than frame by frame: the point of recording
        the order is the order of the whole thing, and a partially written trace is a trace
        with a fabricated ending. A run abandoned mid-stream records what it managed to say.
        """
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                UPDATE notices SET review_trace = %s::jsonb
                 WHERE id = %s AND org_id = %s
                """,
                (json.dumps(list(frames)), notice_id, org_id),
            )

    async def notices_for_org(self, org_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, reference, reference_line, mpn, mpn_line, manufacturer, effective_date, replacement_mpn,
                       reason, source, review_skipped, created_at
                  FROM notices WHERE org_id = %s ORDER BY created_at DESC LIMIT %s
                """,
                (org_id, limit),
            )
            return await cursor.fetchall()

    async def save_review_skipped(
        self, org_id: str, notice_id: str, skipped: Sequence[Mapping[str, str]]
    ) -> None:
        """The current discovery omissions, alongside the current requests for this notice."""
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                UPDATE notices SET review_skipped = %s
                 WHERE id = %s AND org_id = %s
                """,
                (Json(list(skipped)), notice_id, org_id),
            )

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
            # The latest request per line, not every one ever written. Reviewing a notice
            # twice — a candidate added, a volume corrected — writes a second document for
            # each line, and every one of them is kept, because a change request is a
            # record of what was decided and on what basis. What a reader needs back is the
            # current answer for each product line; two of them for one line is a document
            # that contradicts itself. Found on screen, with a notice reviewed twice.
            cursor = await conn.cursor(row_factory=dict_row).execute(
                f"""
                SELECT * FROM (
                    SELECT DISTINCT ON (notice_id, line_id)
                           id, notice_id, line_id, proposal, document, created_at
                      FROM change_requests WHERE {where}
                  ORDER BY notice_id, line_id, created_at DESC
                ) latest
                ORDER BY created_at DESC LIMIT %s
                """,
                (*params, limit),
            )
            return await cursor.fetchall()

    # ── precedents ───────────────────────────────────────────────────────────

    async def record_precedents(
        self, org_id: str, line_id: str, entries: Sequence[Mapping[str, Any]]
    ) -> None:
        """What worked and what did not, against the conflict shape it applied to.

        Upserted rather than appended: the current answer for a part on a board is one
        fact, and a history of it changing its mind is not what the next notice needs.
        """
        if not entries:
            return
        async with self.pool.connection() as conn:
            cursor = conn.cursor()
            await cursor.executemany(
                """
                INSERT INTO precedents (org_id, line_id, signature, mpn, outcome, detail)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (org_id, line_id, signature, mpn) DO UPDATE
                   SET outcome = EXCLUDED.outcome,
                       detail = EXCLUDED.detail,
                       recorded_at = now()
                """,
                [
                    (
                        org_id, line_id, entry["signature"], entry["mpn"],
                        entry["outcome"], entry.get("detail"),
                    )
                    for entry in entries
                ],
            )

    async def rejected_on(self, org_id: str, line_id: str) -> dict[str, str]:
        """MPNs already ruled out **on this board**, and the sentence that ruled each out.

        Scoped to the line on purpose. A part that cooks one product says nothing about a
        cooler one, and a rejection that spread across every board would remove candidates
        nobody had ever checked there.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT mpn, detail FROM precedents
                 WHERE org_id = %s AND line_id = %s AND outcome = 'rejected'
                """,
                (org_id, line_id),
            )
            return {row["mpn"]: row["detail"] or "" for row in await cursor.fetchall()}

    async def worked_anywhere(self, org_id: str, signature: str) -> list[dict[str, Any]]:
        """Parts that resolved this conflict shape anywhere in the company.

        Not scoped to a line, and that asymmetry is the point: a part already qualified on
        one product is the cheap answer on the next, which is the whole distance between
        resolving an end-of-life with an approved part and qualifying one from scratch.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT p.mpn, p.line_id, l.name AS line_name, p.detail, p.recorded_at
                  FROM precedents p
                  JOIN product_lines l ON l.id = p.line_id
                 WHERE p.org_id = %s AND p.signature = %s AND p.outcome = 'worked'
              ORDER BY p.recorded_at DESC
                """,
                (org_id, signature),
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

    # ── the board a line is built from ────────────────────────────────────────

    async def save_board(
        self,
        *,
        line_id: str,
        org_id: str,
        user_id: str | None,
        filename: str,
        project: str,
        bundle: bytes,
    ) -> None:
        """Store the uploaded project, replacing whatever the line had before.

        Scoped in the statement rather than checked first: a line belonging to another
        organisation matches nothing and writes nothing, which is the same shape every
        other write here has.
        """
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO line_boards (line_id, org_id, user_id, filename, project, bundle)
                SELECT %(line)s, %(org)s, %(user)s, %(filename)s, %(project)s, %(bundle)s
                  FROM product_lines
                 WHERE id = %(line)s AND org_id = %(org)s
                ON CONFLICT (line_id) DO UPDATE
                   SET org_id = EXCLUDED.org_id,
                       user_id = EXCLUDED.user_id,
                       filename = EXCLUDED.filename,
                       project = EXCLUDED.project,
                       bundle = EXCLUDED.bundle,
                       uploaded_at = now()
                """,
                {
                    "line": line_id,
                    "org": org_id,
                    "user": user_id,
                    "filename": filename,
                    "project": project,
                    "bundle": bundle,
                },
            )

    async def board_for(self, line_id: str, org_id: str) -> dict[str, Any] | None:
        """What is known about a line's board, without carrying the file itself.

        The bundle is a megabyte or so and a dashboard only ever wants the name and the
        date, so it is fetched separately by whoever actually needs to run KiCad on it.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT line_id, filename, project, uploaded_at, octet_length(bundle) AS bytes
                  FROM line_boards
                 WHERE line_id = %s AND org_id = %s
                """,
                (line_id, org_id),
            )
            return await cursor.fetchone()

    async def board_bundle(self, line_id: str, org_id: str) -> tuple[str, bytes] | None:
        """The uploaded file, exactly as it arrived."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT filename, bundle FROM line_boards WHERE line_id = %s AND org_id = %s",
                (line_id, org_id),
            )
            row = await cursor.fetchone()
        return (row[0], bytes(row[1])) if row else None

    async def delete_board(self, line_id: str, org_id: str) -> bool:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM line_boards WHERE line_id = %s AND org_id = %s",
                (line_id, org_id),
            )
            return cursor.rowcount > 0

    async def notices_reaching_line(self, line_id: str, org_id: str) -> list[dict[str, Any]]:
        """Every notice this product line carries a part for, newest first.

        The inverse of `lines_exposed_to`, and the question a product line's own page asks:
        not *what does this notice reach* but *what is coming for this product*. Joined on
        the fitted bill rather than on the whole document, because a part that is not
        populated is not on the board.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT n.id, n.mpn, n.manufacturer, n.effective_date, n.replacement_mpn,
                       n.reason, n.source, n.created_at,
                       array_agg(lp.refdes ORDER BY lp.refdes) AS refdes
                  FROM notices n
                  JOIN line_parts lp
                    ON lp.mpn = n.mpn AND lp.org_id = n.org_id AND lp.populated
                 WHERE n.org_id = %s AND lp.line_id = %s
              GROUP BY n.id, n.mpn, n.manufacturer, n.effective_date, n.replacement_mpn,
                       n.reason, n.source, n.created_at
              ORDER BY n.created_at DESC
                """,
                (org_id, line_id),
            )
            return await cursor.fetchall()

    async def change_requests_for_line(self, line_id: str, org_id: str) -> list[dict[str, Any]]:
        """The current change request per notice for this line. See `change_requests_for_org`
        for why the latest rather than every one ever written."""
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT DISTINCT ON (notice_id)
                       id, notice_id, line_id, proposal, document, created_at
                  FROM change_requests
                 WHERE line_id = %s AND org_id = %s
              ORDER BY notice_id, created_at DESC
                """,
                (line_id, org_id),
            )
            return await cursor.fetchall()

    # ── decisions waiting for a desk ──────────────────────────────────────────

    async def save_decision(
        self,
        *,
        org_id: str,
        line_id: str,
        notice_id: str | None,
        user_id: str | None,
        slot_id: str,
        retiring: str,
        proposal: str,
        gate_rule: str | None,
        roles: Sequence[str],
        detail: str,
        document: Mapping[str, Any],
    ) -> str:
        """Record a substitution that is waiting for somebody to say yes.

        One pending decision per line at a time: re-running a review replaces the pending
        one rather than stacking a second, because two open decisions about the same
        position on the same board is a question nobody can answer.
        """
        decision_id = new_id()
        async with self.pool.connection() as conn:
            await conn.execute(
                "DELETE FROM decisions WHERE line_id = %s AND org_id = %s AND state = 'pending'",
                (line_id, org_id),
            )
            await conn.execute(
                """
                INSERT INTO decisions (
                    id, org_id, line_id, notice_id, user_id, slot_id, retiring, proposal,
                    gate_rule, roles, detail, document
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision_id, org_id, line_id, notice_id, user_id, slot_id, retiring,
                    proposal, gate_rule, list(roles), detail, Json(dict(document)),
                ),
            )
        return decision_id

    async def decision_for(self, decision_id: str, org_id: str) -> dict[str, Any] | None:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT d.*, p.name AS line_name, p.revision
                  FROM decisions d
                  JOIN product_lines p ON p.id = d.line_id AND p.org_id = d.org_id
                 WHERE d.id = %s AND d.org_id = %s
                """,
                (decision_id, org_id),
            )
            return await cursor.fetchone()

    async def decisions_for_line(self, line_id: str, org_id: str) -> list[dict[str, Any]]:
        """Every decision recorded against this product line, newest first.

        The product line page's own record of what has been reviewed here. `decisions` is
        already the fullest account a review leaves — every candidate it tried and the
        sentence that settled each — and nothing was reading it per line.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT d.*, p.name AS line_name
                  FROM decisions d
                  JOIN product_lines p ON p.id = d.line_id AND p.org_id = d.org_id
                 WHERE d.line_id = %s AND d.org_id = %s
              ORDER BY d.created_at DESC
                """,
                (line_id, org_id),
            )
            return await cursor.fetchall()

    async def decisions_for_notice(self, notice_id: str, org_id: str) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT d.*, p.name AS line_name
                  FROM decisions d
                  JOIN product_lines p ON p.id = d.line_id AND p.org_id = d.org_id
                 WHERE d.notice_id = %s AND d.org_id = %s
              ORDER BY p.name
                """,
                (notice_id, org_id),
            )
            return await cursor.fetchall()

    async def decisions_waiting_on(
        self, org_id: str, roles: Sequence[str]
    ) -> list[dict[str, Any]]:
        """Every pending decision one of these desks may answer, newest first.

        **The desk's own queue, across every product line.** A substitution needs a
        signature from each department that examined it, and until this existed the other
        desks had no way to find the thing they had to sign: they would have had to know
        which product line it was on and navigate there. Ownership is by role rather than
        by organisation, so a colleague holding none of the required desks sees an empty
        list, which is not an error.

        The line and the notice are joined here rather than fetched per row, because a
        queue that costs one round trip per entry is a queue nobody opens.
        """
        if not roles:
            return []
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT d.id, d.line_id, d.notice_id, d.slot_id, d.retiring, d.proposal,
                       d.gate_rule, d.roles, d.detail, d.created_at,
                       p.name AS line_name, p.revision AS revision,
                       n.mpn AS notice_mpn,
                       COALESCE(
                           (SELECT array_agg(DISTINCT role)
                              FROM approvals a, unnest(a.roles) AS role
                             WHERE a.decision_id = d.id),
                           ARRAY[]::text[]
                       ) AS signed
                  FROM decisions d
                  JOIN product_lines p ON p.id = d.line_id AND p.org_id = d.org_id
             LEFT JOIN notices n ON n.id = d.notice_id
                 WHERE d.org_id = %s AND d.state = 'pending' AND d.roles && %s::text[]
              ORDER BY d.created_at DESC
                """,
                (org_id, list(roles)),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def settle_decision(
        self, decision_id: str, org_id: str, *, state: str, by: str | None, rationale: str | None
    ) -> bool:
        """Answer a decision, once. A second answer is refused rather than overwriting.

        `state = 'pending'` in the WHERE clause is what makes that true under two people
        pressing approve at the same moment: the second update matches no row.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE decisions
                   SET state = %s, decided_by = %s, rationale = %s, decided_at = now()
                 WHERE id = %s AND org_id = %s AND state = 'pending'
                """,
                (state, by, rationale, decision_id, org_id),
            )
            return cursor.rowcount == 1

    async def manufacturer_of(self, org_id: str, mpn: str) -> str | None:
        """Who makes the part this company actually fitted, as its bills record it.

        A part on a board is not ambiguous however many manufacturers a distributor lists
        it under: the bill of materials says whose it is. Without this, resolving the
        incumbent by part number alone is refused as ambiguous and a whole review returns
        nothing — which it did, twice, in two different features.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT manufacturer FROM line_parts
                 WHERE org_id = %s AND mpn = %s AND manufacturer IS NOT NULL
                 LIMIT 1
                """,
                (org_id, mpn),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def recorded_manufacturers(self, org_id: str) -> dict[str, str]:
        """Who this company says makes each part it knows about, keyed by uppercased MPN.

        Two records, and the bill wins where they disagree. The approved list is a
        statement of what quality qualified; a bill is a statement of what is on a board
        somebody ships, which is the stronger evidence and the one `manufacturer_of`
        already relies on for a single part.

        Read once per review rather than per candidate: it is two small reads of the
        organisation's own tables, and a lookup per candidate would put a round trip in
        front of every part in the catalogue leg.
        """
        recorded: dict[str, str] = {}
        async with self.pool.connection() as conn:
            # Written out rather than looped over a table name, so no identifier is
            # interpolated into SQL even from a literal this module controls.
            qualified = await (
                await conn.execute(
                    """
                    SELECT mpn, manufacturer FROM approved_parts
                     WHERE org_id = %s AND manufacturer IS NOT NULL AND manufacturer <> ''
                    """,
                    (org_id,),
                )
            ).fetchall()
            fitted = await (
                await conn.execute(
                    """
                    SELECT mpn, manufacturer FROM line_parts
                     WHERE org_id = %s AND manufacturer IS NOT NULL AND manufacturer <> ''
                    """,
                    (org_id,),
                )
            ).fetchall()
            # The bill last, so it wins.
            for mpn, manufacturer in [*qualified, *fitted]:
                recorded[mpn.upper()] = manufacturer
        return recorded

    async def attach_board_consequence(
        self, org_id: str, notice_id: str, line_id: str, payload: dict[str, Any]
    ) -> bool:
        """Put a board's consequence on the change request it belongs to. `False` if absent.

        **The request row is written first and the board arrives seconds later**, so this is
        an update rather than part of the insert: a KiCad run is several seconds and the
        document is written milliseconds after the proposal is chosen. It is a no-op when
        there is no row yet, which is why it returns whether it found one — a caller that
        cared could retry, and the review does not, because a board that never lands leaves
        the card showing the button it shows today.

        `||` rather than a rewrite: the document is the run's record and this adds one key
        to it. Nothing here can lose a field the run wrote.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE change_requests
                   SET document = document || %s::jsonb
                 WHERE org_id = %s AND notice_id = %s AND line_id = %s
                   AND id = (
                       SELECT id FROM change_requests
                        WHERE org_id = %s AND notice_id = %s AND line_id = %s
                     ORDER BY created_at DESC
                        LIMIT 1
                   )
                """,
                (
                    json.dumps({"board": payload}),
                    org_id, notice_id, line_id,
                    org_id, notice_id, line_id,
                ),
            )
            return cursor.rowcount > 0

    async def apply_substitution(
        self,
        *,
        line_id: str,
        org_id: str,
        user_id: str,
        refdes: str,
        mpn: str,
        manufacturer: str | None,
        footprint: str | None,
        revision: str | None,
    ) -> bool:
        """Put the substitute on the product line, at the position the old part sat in.

        One statement, scoped by organisation, so a line belonging to somebody else matches
        nothing and writes nothing. The revision moves with it because the bill of materials
        of a released design cannot change without the design changing — a board carrying a
        different regulator under the same revision is a board nobody can trace.
        """
        async with self.pool.connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    UPDATE line_parts SET mpn = %s, manufacturer = %s, footprint = %s
                     WHERE line_id = %s AND org_id = %s AND refdes = %s
                    """,
                    (mpn, manufacturer, footprint, line_id, org_id, refdes),
                )
                if cursor.rowcount != 1:
                    return False
                await conn.execute(
                    """
                    UPDATE product_lines
                       SET revision = COALESCE(%s, revision), updated_at = now()
                     WHERE id = %s AND org_id = %s
                    """,
                    (revision, line_id, org_id),
                )
        return True

    async def approvals_for_decision(
        self, decision_id: str, org_id: str
    ) -> list[dict[str, Any]]:
        """Every signature already given against one decision.

        A decision needs one from each department that examined the change, so answering it
        is a read of what is already there rather than a single write. `decisions.state`
        stays the record of the outcome; these are the record of who got there.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_id, user_email, roles, rationale, created_at
                  FROM approvals WHERE decision_id = %s AND org_id = %s
              ORDER BY created_at
                """,
                (decision_id, org_id),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def approvals_for_line(self, line_id: str, org_id: str) -> list[dict[str, Any]]:
        """Who signed what on this product line. The audit trail an ECO process asks for."""
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT id, user_email, roles, rule, subject, mpn, revision, rationale,
                       created_at
                  FROM approvals WHERE line_id = %s AND org_id = %s
              ORDER BY created_at DESC
                """,
                (line_id, org_id),
            )
            return await cursor.fetchall()

    async def accepted_waivers_for_line(
        self, line_id: str, org_id: str
    ) -> list[dict[str, Any]]:
        """Accepted EOL gates that apply to the line as it stands now.

        A signature on a pending or declined decision is not a waiver. Only the desk that
        owns the failed rule can create one, even though every desk signs the released
        change itself. The rule/candidate/revision tuple stays intact for revalidation.
        """
        async with self.pool.connection() as conn:
            cursor = await conn.cursor(row_factory=dict_row).execute(
                """
                SELECT d.gate_rule AS rule, a.subject, a.mpn, a.revision, a.roles
                  FROM decisions d
                  JOIN approvals a ON a.decision_id = d.id AND a.org_id = d.org_id
                 WHERE d.line_id = %s AND d.org_id = %s
                   AND d.state = 'approved' AND d.gate_rule IS NOT NULL
                   AND a.rule = d.gate_rule
              ORDER BY a.created_at
                """,
                (line_id, org_id),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        waivers = []
        for row in rows:
            owning_roles = sorted(
                set(row["roles"] or ()).intersection(roles_for_rule(row["rule"]))
            )
            if owning_roles:
                waivers.append({**row, "roles": owning_roles})
        return waivers
