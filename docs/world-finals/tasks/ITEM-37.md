# Task · BUILD item 37 — the presenter can be any desk without logging out

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** item 36.

[SCENARIO-B.md](../SCENARIO-B.md)'s open question — *"how this is demoed on stage in the time
available"* — has never been answered. With four desks and all-must-approve, the run-through
needs four signatures and today that is four sign-outs.

## Why a real session and not a "view as"

The WordPress *View as Role* documentation draws the line precisely: a view-as simulation is
*"visual only — it doesn't grant or remove actual permissions"* and *"any actions you take are
still done as you"*, whereas login-as *"actually switches accounts"* and can act. Its own
guidance: *"use View as Role when you want to check what a role can see. Use Login As User when
you need to act as a specific user."*

**A desk has to actually sign.** A simulation would be an affordance that cannot be used, which
is the rule we already hold. So this holds several genuine sessions and switches the active
one. Every reference implementation does the same: `treasury-rfq-demo` switches principal from
the header with each view fetching *"independently with its own credentials, no god-view
shortcuts"*, and a wrong-principal call still returns 403.

## 1 · Several sessions, one active — `continuity/api/auth.py`

Sessions are already opaque random tokens stored server-side as SHA-256, in an httpOnly cookie
`continuity_session` (`auth.py:36,106,116`). Read that file before writing anything.

Add a second **httpOnly** cookie, `continuity_sessions`, holding the tokens this browser has
authenticated, newest first, capped at six:

- `_set_session_cookie` appends the new token to it on register and on login.
- `logout` removes that one token from it and clears the active cookie.

Tokens stay httpOnly and are never readable by JavaScript, so nothing about this weakens the
session model. **You can only switch to a desk you have already signed into in this browser**,
which is a real property rather than a demo shortcut.

```
GET  /auth/sessions      → [{email, roles, active}]   invalid or expired tokens are dropped
POST /auth/switch {email} → PublicUser, and the active cookie becomes that account's token
```

`switch` refuses an email whose token this browser does not hold: 403, not 404. There is no
path here to a session the caller did not authenticate.

## 2 · The control — `frontend/src/app/shell/`

In the header, and always showing the current desk. Not in a menu: the reader of a screen must
be able to see whose eyes they are looking through without clicking anything, which is the one
thing every reference implementation agrees on.

Switching refetches. Everything in the app is per-user already, so the simplest correct
behaviour is to invalidate and reload the current route rather than reconcile state by hand.

## 3 · The four-desk frame, if there is time

The strongest single frame for this scenario, and it is optional: one change request, four
panes, each fetching as its own desk, each showing that desk's own verdicts and its own button.
`treasury-rfq-demo`'s note on why it works is the reason to build it:

> *"The empty pane is the most concrete evidence that scoping is real, not cosmetic."*

A desk with nothing to answer showing nothing to answer cannot be faked, and it makes the point
without anybody switching anything. It is also what the right-hand side of a master-detail
`/changes` should hold — see the third-pass finding on that page.

**Build the switcher first.** The four-pane view is worth nothing if a desk cannot sign.

## 4 · Tests

- Signing in twice in one client leaves both sessions live, and `/auth/sessions` lists both.
- `POST /auth/switch` changes what `/auth/me` returns.
- Switching to an email this browser has not authenticated is a 403.
- An answer submitted after switching is attributed to the switched-to user in `approvals`.
- Logging out of one desk leaves the others usable.

## Done when

The run-through can take four signatures without typing a password twice, and every 403 in the
product still fires exactly as it did.
