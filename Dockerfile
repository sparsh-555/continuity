# The deployed app, on a host that can run KiCad.
#
# ## Why this exists rather than a build command
#
# The board surfaces need KiCad: `kicad-cli` for the bill, the render and the design rule
# check, and Python's `pcbnew` for placing a substitute and carrying its nets. Render's native
# runtimes give you a container with no Docker daemon, so the runner's `docker` mode cannot
# work there, and no amount of `apt-get` in a build command installs KiCad into a runtime that
# does not let you become root. A Docker service is the only shape where the answer to "is
# there a KiCad" is yes.
#
# **The base image is the one the runner already pins.** `kicad/kicad:9.0` is what
# `CONTINUITY_KICAD=docker` runs on a laptop, and starting from it means the deployed instance
# answers with the same 9.0.9 that every file format and command argument here was verified
# against. `runner.check()` refuses any other version, so a base image chosen for convenience
# would fail at the first request rather than at the build.
#
# `--platform=linux/amd64` is required and is not a workaround: the image is amd64 only, and
# Render builds and runs linux/amd64. See `backend/continuity/kicad/runner.py`.

# ── The UI, built once and thrown away ────────────────────────────────────────
# The KiCad image has no node, and it should not grow one. `npm ci` rather than `npm install`
# so the lockfile decides the tree, which is the same reason Render's own build command uses
# it and the reason a lockfile that drifts from `package.json` fails loudly here too.
FROM --platform=linux/amd64 node:22-bookworm-slim AS ui

WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# **The UI build reads one file out of `backend/`, and the build fails without it.**
# `vite.config.ts` aliases `../backend/continuity/api/walkthrough.jsonl` to a module, which is
# the recorded landing animation. It resolves relative to the config file, so inside this stage
# that is `/backend/`, which is why the path below sits outside the working directory. The
# failure is a build error naming the path, so there is nothing quiet about getting it wrong.
COPY backend/continuity/api/walkthrough.jsonl /backend/continuity/api/walkthrough.jsonl
# **Vite inlines this at build time, and the default is wrong here.** `lib/api.ts` falls back
# to `http://localhost:8000` when the variable is unset, which is right for a laptop and is a
# page that calls the visitor's own machine once this is deployed. The Python-runtime service
# gets it from the dashboard's environment; a Docker image has no such environment at build
# time, so it is stated here. `/api`, because `spa.py` mounts the API there on one origin.
ENV VITE_API_URL=/api
RUN npm run build

# ── The app, on the pinned KiCad ──────────────────────────────────────────────
FROM --platform=linux/amd64 kicad/kicad:9.0

USER root
# `python3-venv` and nothing else: the image already carries python3, `pcbnew` and the stock
# symbol and footprint libraries, which is the whole reason it is the base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/*

# **`--system-site-packages` is load-bearing.** `pcbnew` is a distro package in
# `/usr/lib/python3/dist-packages`, built for this image's Python 3.11, and it cannot be
# installed from PyPI. A venv without this flag would isolate the app from the one module the
# board placement needs, and the failure would arrive as an import error inside a KiCad run
# rather than as anything the build could see.
RUN python3 -m venv --system-site-packages /opt/continuity
ENV PATH=/opt/continuity/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CONTINUITY_KICAD=local

WORKDIR /app

# **`-e`, and the layout is the reason.** `api/spa.py` anchors the built UI at
# `parents[3] / frontend / dist`, which from `backend/continuity/api/spa.py` is the repository
# root. A non-editable install would copy the package into site-packages, where `parents[3]` is
# a site-packages directory with no `frontend/` in it, and the app would serve an API with no
# UI at all. `cache/` and `fixtures/` are anchored the same way.
COPY backend/ ./backend/
RUN pip install --no-cache-dir -e ./backend

COPY --from=ui /ui/dist ./frontend/dist

# **Runs as `kicad`, which is the image's own user, and that matters.** The image copies the
# KiCad library tables into that user's config directory at build time. Running as root would
# give KiCad a different config directory, the footprint tables would not be there, and the
# substitution would fail to find the land pattern it needs to place.
RUN mkdir -p backend/cache && chown -R kicad:kicad /app
USER kicad

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn continuity.api.app:ui --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
