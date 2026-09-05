"""Serve the built UI from the API, so the whole app has exactly one origin.

## Why this exists

`onrender.com` is on the Public Suffix List, so `continuity-ui.onrender.com` and
`continuity-api.onrender.com` are not two subdomains of one site — they are two different
*sites*. The session cookie was therefore a third-party cookie. `SameSite=none` only makes
such a cookie eligible to be **sent**; WebKit refuses to **store** third-party cookies at
all, so Safari and every browser on iOS got a 401 on every authenticated request and a
dashboard reading "Could not load your projects". Chrome still permits them, which is why
it looked fine for months.

No cookie attribute fixes that, and the alternatives each cost something: a custom domain
needs a registrar, and proxying the API through the static site's CDN puts an edge cache in
front of a long-lived SSE stream. Serving both from one process removes the question
instead of answering it — one origin means a first-party cookie, no CORS, and nothing
between uvicorn and the browser while a run streams.

The trade is the static CDN. At 620 KB that is a fraction of a second, and the same
process was already on the critical path for every authenticated request anyway.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
"""The Vite build. Anchored off this file, so it survives whatever the working directory is.

`pip install -e ./backend` is what keeps that true on Render — a non-editable install would
copy the package into site-packages, and this path would then point at a directory with no
`frontend/` beside it. The same reason `cache/` and `fixtures/` need the editable install.
"""


class _Spa(StaticFiles):
    """Static files, with a client-router fallback and an uncached entry point.

    Two behaviours the default does not have:

    * **Unknown paths serve `index.html`.** `/projects` and `/design/:id` are routes the
      React router owns; there was never a file at either. Without this a reload on any
      of them is a 404.
    * **`index.html` is never cached.** Vite content-hashes the asset filenames, so those
      are safe to cache forever, but `index.html` is what *names* them. A stale copy after
      a deploy points at bundles that no longer exist, and the app comes up blank with no
      error anyone can act on.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            response = await super().get_response("index.html", scope)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-store"
        return response


def serve(api: FastAPI, dist: Path = DIST) -> FastAPI:
    """The app to run in production: the API under `/api`, the UI everywhere else.

    ## Why the API needs a prefix

    The router and the API both own `/projects`, `/memory` and `/design`. On two hosts that
    was never a conflict — one served pages, the other served JSON, and nothing had to
    choose. On one origin something has to, and a path cannot mean two things.

    Prefixing the API keeps the URLs a person sees unchanged: `/projects` is still the
    page, and `/api/projects` is the JSON behind it. Prefixing the *UI* instead would have
    meant no backend change at all, but every visible URL would carry an `/app` that exists
    only to serve an implementation detail.

    The API keeps its unprefixed shape as a standalone app, which is what the tests drive
    and what local development runs. Only the composed application is prefixed, so nothing
    below this function has to know it is mounted.

    Returns the API untouched when there is no build to serve — the normal state in local
    development, where Vite serves the UI on its own port.
    """
    if not (dist / "index.html").is_file():
        return api

    @asynccontextmanager
    async def lifespan(_composed: FastAPI) -> AsyncIterator[None]:
        """Run the API's own startup, against the API.

        **Starlette does not run a mounted application's lifespan.** Without this the
        database pool is never opened, `app.state.store` stays `None`, and every route
        behind it answers 503 "this instance is running without a database" — while
        `/health` and the whole UI keep working, so it looks fine until someone signs in.

        The inner app is passed deliberately. A mounted `FastAPI` sets `scope["app"]` to
        itself, so routes read `request.app.state` off the API, not off this wrapper.
        """
        async with api.router.lifespan_context(api):
            yield

    composed = FastAPI(title="Continuity", version=api.version, lifespan=lifespan)
    composed.mount("/api", api)
    # Last: a mount at `/` matches every path `/api` did not claim.
    composed.mount("/", _Spa(directory=dist, html=True), name="ui")
    return composed
