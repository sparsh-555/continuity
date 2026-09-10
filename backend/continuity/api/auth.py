"""Accounts and the session cookie.

## Why an opaque session and not a JWT

A JWT would have to be revoked by keeping a list of the ones that are no longer valid,
which is a session table with extra steps and a signature to get wrong. An opaque random
token *is* the reference to a row, so logging out is a `DELETE` and there is no window
where a stolen token outlives the logout that was supposed to end it.

Only the SHA-256 of the token is stored. The cookie value itself is never written down.

## The two settings that will break on deploy day

`SameSite=Lax` is right when the UI and the API share a registrable domain — ports are
not part of that comparison, so `localhost:5173 → localhost:8000` is same-site and works
unchanged in development. Split them across domains (`*.vercel.app` calling `*.fly.dev`)
and Lax stops sending the cookie at all: that deployment needs
`CONTINUITY_COOKIE_SAMESITE=none` together with `CONTINUITY_COOKIE_SECURE=1`, because
browsers refuse `SameSite=None` without `Secure`.

Both default to the development setting, so nothing has to be configured to run locally
and the production values are a deliberate act.
"""

from __future__ import annotations

import os
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from .store import SESSION_TTL_SECONDS, EmailTaken, Store, User

COOKIE = "continuity_session"
HELD = "continuity_sessions"
"""Every session this browser has authenticated, newest first.

## Why a second cookie

A substitution on a released design is signed by four departments, and walking that on stage
meant signing out and back in three times. The pattern every multi-party demo uses is a
principal switcher holding several genuine sessions, and the distinction that matters is the
one the *view as role* literature draws: a simulation is visual only and cannot act, while
switching accounts actually can. **A desk has to sign**, so this holds real sessions.

`httponly` like the active one, so no script can read a token, and `/auth/switch` will only
move to a session this browser already authenticated. There is no path here to a session the
caller did not sign into.
"""

HELD_LIMIT = 6
"""How many sessions one browser keeps. Four desks and room to be wrong twice."""

MIN_PASSWORD_LENGTH = 8
"""A floor, not a policy. Composition rules push people towards worse passwords."""

hasher = PasswordHasher()

_DUMMY_HASH = hasher.hash("a password that belongs to nobody")
"""Verified against when the email is unknown, so that "no such account" and "wrong
password" take the same time as well as returning the same body. Without it the login
endpoint answers a question it was never asked."""

INVALID_CREDENTIALS = "email or password is incorrect"
"""One message for both failures. Naming which half was wrong is an enumeration oracle."""

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class PublicUser(BaseModel):
    id: str
    email: str
    onboarded: bool
    org_id: str
    roles: list[str]
    """The hats this person wears, from `store.ROLES`.

    Reported now rather than when a screen first needs it: item 13's gates have to know
    whether to offer the person an approval or tell them who to fetch, and a field that
    appears later is a second migration through the client's types."""


def _public(user: User) -> PublicUser:
    return PublicUser(
        id=user.id,
        email=user.email,
        onboarded=user.onboarded_at is not None,
        org_id=user.org_id,
        roles=list(user.roles),
    )


def store_of(request: Request) -> Store:
    """The store, or a straight answer that this deployment has no accounts.

    Running without `DATABASE_URL` is a supported mode — it is what the offline suite
    uses — but it cannot serve these routes, and pretending otherwise would surface as
    an AttributeError inside a handler.
    """
    store = request.app.state.store
    if store is None:
        raise HTTPException(503, "this instance is running without a database")
    return store


async def current_user(request: Request) -> User:
    """Every authenticated route depends on this. A miss is 401, never an empty user.

    An instance with no store answers 401 here rather than the 503 `store_of` gives the
    other routes. The distinction is deliberate: `register` and `login` genuinely cannot
    function without a database, but "this instance has no accounts" is a complete and
    accurate answer to *who is signed in* — nobody is. Returning 503 reports a server
    fault where there is none, and a browser holding a cookie from some other instance
    then sees a scary error on every page load instead of simply being signed out.
    """
    store = request.app.state.store
    token = request.cookies.get(COOKIE)
    if store is None or not token:
        raise HTTPException(401, "not signed in")

    user = await store.user_for_token(token)
    if user is None:
        raise HTTPException(401, "not signed in")
    return user


def _held(request: Request) -> list[str]:
    """The tokens this browser holds, in order, newest first."""
    raw = request.cookies.get(HELD) or ""
    return [token for token in raw.split(".") if token][:HELD_LIMIT]


def _set_held_cookie(response: Response, tokens: list[str]) -> None:
    if not tokens:
        response.delete_cookie(HELD, path="/")
        return
    _write_cookie(response, HELD, ".".join(tokens[:HELD_LIMIT]))


def _set_session_cookie(response: Response, token: str) -> None:
    _write_cookie(response, COOKIE, token)


def _write_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        samesite=os.environ.get("CONTINUITY_COOKIE_SAMESITE", "lax"),
        secure=os.environ.get("CONTINUITY_COOKIE_SECURE", "") == "1",
        path="/",
        # The *ceiling*, not the idle window. The browser keeps sending the cookie and the
        # server decides whether it is still alive — a cookie that expired client-side would
        # be indistinguishable from never having signed in, and the session table is the one
        # place that knows the difference.
        max_age=SESSION_TTL_SECONDS,
    )


@router.post("/register", status_code=201)
async def register(
    credentials: Credentials, request: Request, response: Response
) -> PublicUser:
    store = store_of(request)
    try:
        user = await store.create_user(credentials.email, hasher.hash(credentials.password))
    except EmailTaken:
        raise HTTPException(409, "an account with that email already exists")

    token = await store.create_session(user.id)
    _set_session_cookie(response, token)
    _set_held_cookie(response, [token, *_held(request)])
    return _public(user)


@router.post("/login")
async def login(credentials: Credentials, request: Request, response: Response) -> PublicUser:
    store = store_of(request)
    user = await store.user_by_email(credentials.email)

    try:
        hasher.verify(user.password_hash if user else _DUMMY_HASH, credentials.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, INVALID_CREDENTIALS)

    if user is None:  # the dummy hash matched, which it cannot — belt and braces
        raise HTTPException(401, INVALID_CREDENTIALS)

    # Parameters change as hardware does; a login is the only moment the plaintext is
    # available to re-hash with the current ones.
    if hasher.check_needs_rehash(user.password_hash):
        await store.update_password_hash(user.id, hasher.hash(credentials.password))

    token = await store.create_session(user.id)
    _set_session_cookie(response, token)
    # Kept alongside whatever this browser already holds, so signing in as a second desk
    # adds one rather than replacing one.
    _set_held_cookie(response, [token, *(t for t in _held(request) if t != token)])
    return _public(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    """Ends the session server-side, so a copied token stops working too.

    Only this desk's. The others this browser holds stay live, because signing out of
    procurement is not a statement about engineering.
    """
    token = request.cookies.get(COOKIE)
    if token and request.app.state.store is not None:
        await request.app.state.store.delete_session(token)
    response.delete_cookie(COOKIE, path="/")
    _set_held_cookie(response, [held for held in _held(request) if held != token])


@router.get("/sessions")
async def sessions(request: Request) -> list[dict[str, Any]]:
    """Every desk this browser is signed into, and which one is active.

    Tokens are never returned. The switcher names accounts by email and asks the server to
    move; a token readable by a script would undo the whole point of an httpOnly cookie.
    Expired or revoked tokens are dropped rather than reported, because a session that no
    longer works is not a desk somebody can switch to.
    """
    store = request.app.state.store
    if store is None:
        return []
    active = request.cookies.get(COOKIE)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for token in _held(request):
        user = await store.user_for_token(token)
        if user is None or user.email in seen:
            continue
        seen.add(user.email)
        out.append(
            {"email": user.email, "roles": list(user.roles), "active": token == active}
        )
    return out


class Desk(BaseModel):
    email: EmailStr


@router.post("/switch")
async def switch(body: Desk, request: Request, response: Response) -> PublicUser:
    """Make another session this browser already holds the active one.

    **Not an impersonation.** There is no path here to a session the caller did not
    authenticate: the token must already be in this browser's own httpOnly cookie, so
    switching is a change of which real session is in use rather than a grant of one. A
    desk that has to sign has to be signed in.
    """
    store = store_of(request)
    for token in _held(request):
        user = await store.user_for_token(token)
        if user is not None and user.email.lower() == body.email.lower():
            _set_session_cookie(response, token)
            return _public(user)
    raise HTTPException(
        403,
        f"this browser is not signed in as {body.email}. Sign in as that desk first.",
    )


@router.get("/me")
async def me(user: User = Depends(current_user)) -> PublicUser:
    return _public(user)
