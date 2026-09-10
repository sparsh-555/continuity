# OPERATING.md

Everything around the run-through: what the start script checks, how to run the pieces by
hand, every route and every variable, what would be a bug at each step, what breaks and why,
and what is known and not worth reporting.

[RUNNER.md](RUNNER.md) is the flow. [DEMO-DAY.md](DEMO-DAY.md) is what you say. Read this one
when something needs fixing or when you want to run the parts separately.

---

## 1 · What the script checks

`./demo.sh --check` prints one line per item and changes nothing. The commands are in the
script; the reasons are here, because a check that fails is a check somebody has to
understand.

| Check | Fatal? | If it fails |
|---|---|---|
| python | yes | There is no `.venv`. Anaconda's Python cannot import langgraph and gives twelve collection errors |
| postgres | yes | `pg_isready` says no. Start Postgres |
| `continuity_demo` | no | The script creates it |
| `continuity_test` | no | `createdb continuity_test`. Only the suite needs it |
| frontend dependencies | no | The script runs `bun install` |
| model key | no | Reading a change notice is the one step that needs it. Everything else still runs |
| mailbox | no | The notice arrives by **UPLOAD ONE INSTEAD** rather than by email |
| kicad image | no | The BOARD view reports itself unavailable |
| recordings | no | With none in `backend/fixtures/`, every distributor call fails. `--live` records them as it goes |

The port check runs before the world is rebuilt rather than after, because the rebuild is the
first thing that cannot be undone and finding out afterwards that a run is already up would
cost a world for the sake of a message about a port.

**There is nothing to paste.** The key lives in `backend/.env`, which is gitignored, and
`continuity/env.py` walks upward from wherever the process starts, so it is found whether you
launch from the repository root or from `backend/`. Local Postgres authenticates by user
rather than by password, which is why every database URL here is `postgresql:///name` with no
credentials in it. The KiCad image is public and needs no Docker login. The only credentials
you type anywhere are the four demo accounts.

If the key ever has to be replaced, put the new one in `backend/.env` as
`CONTINUITY_LLM_API_KEY=…` and set `CONTINUITY_LLM_BASE_URL=https://api.deepseek.com` beside
it. Do not echo it into a terminal on the way there: scrollback outlives the command.

**The mailbox, in more detail than the script gives:**

```bash
cd backend && ../.venv/bin/python tools/check_mail.py
```

It should say `signed in` and a message count. If it warns that messages are sitting in a spam
folder, one of them is probably the notice: the poller reads `INBOX` only, on purpose, because
acting on a document the provider has judged hostile is not a thing to do in a system whose
output is an engineering change request. Fix it with a Gmail filter rather than by reading the
folder. `not configured` means the three `CONTINUITY_MAIL_*` variables are not in
`backend/.env`, and the whole demo still runs by upload.

**The KiCad image, once:**

```bash
docker pull --platform linux/amd64 kicad/kicad:9.0        # about 2 GB
docker run --rm --platform linux/amd64 kicad/kicad:9.0 kicad-cli version   # expect 9.0.9
```

The `--platform` flag is not optional on Apple silicon. That tag is amd64 only, whatever the
Docker Hub page says, and emulation is what runs it.

---

## 2 · Running the pieces by hand

`./demo.sh` starts both servers. Run them separately when one of them is what you are
debugging, so its log is in front of you rather than in `.demo/`.

```bash
# Seed. --reset replaces a world that is already there.
cd backend
PYTHONPATH=. ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo

# The API.
DATABASE_URL=postgresql:///continuity_demo CONTINUITY_KICAD=docker \
  CONTINUITY_FIXTURES=1 CONTINUITY_MAIL_ORG=engineer@northwind.example \
  ../.venv/bin/python -m uvicorn continuity.api.app:app --port 8000

# The UI.
cd ../frontend
VITE_API_URL=http://localhost:8000 bun run dev --strictPort --port 5173
```

Four things about those commands are load-bearing.

**`backend/.env` points `DATABASE_URL` at production Neon.** Naming the database on the command
line is what keeps a local run local. Never start the API without it.

**`--strictPort` matters.** If Vite quietly takes 5174 or 5175, the browser blocks every API
call on CORS and the app looks broken without naming the cause. To use another port, add it to
`CONTINUITY_ORIGINS` on the API.

**`CONTINUITY_MAIL_ORG` is an address, not an organisation id.** A reseed mints a new id every
time, and a stale one fails by quietly finding no product lines. With exactly one company in
the database it can be left out entirely; the demo world has two if anybody has ever signed up,
which is why it is there.

**There is no startup line to look for.** Nothing configures logging, so the API's own
`persistence: postgres` never reaches the console under uvicorn's default config. Ask instead:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"engineer@northwind.example","password":"continuity-demo-2026"}'
```

`200` means it is on the seeded database. Anything else means `DATABASE_URL` did not reach it,
and in single-user in-memory mode there are no accounts at all. `./demo.sh` does this check for
you.

**The API checks every product line once at startup**, so the first person to open one is not
the person who waits four seconds for it. Nothing depends on that finishing; it moves work that
was going to happen anyway to a moment when nobody is looking.

### Resetting by hand

`./demo.sh` rebuilds the world on every start, so the usual answer is to stop it and start it
again. When the servers are staying up:

```bash
cd backend
PYTHONPATH=. ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo --reset
```

It reseeds five product lines, three boards, both standing lists, and **a described design run
against every line**, which is what step 2 opens.

**The mailbox no longer needs dealing with.** It used to: `mail_cursor` cascades off the
organisation, so a reset wiped the read position, the poller saw a mailbox it had never read,
and within fifteen seconds the last run-through's notice was back. The seed now moves the read
position to the end of the folder, because a company that has just been created has not read
its mail, and it says so when it does:

```
mailbox: read position moved past UID 4, so only new mail arrives
```

Pass `--read-mail` to seed the old way if you ever want the inbox re-read. The demo database
can still end up with two `AMS1117-3.3` notices if you both forward one and upload one, so pick
one per pass.

---

## 3 · What would be a bug

The run-through says what a correct screen looks like. These are the specific failures worth
naming, because each one has been seen at least once.

| Step | Would be a bug |
|---|---|
| 1 | The words *"What are you building?"*; a grey part; content in a narrow strip with an empty field around it; a four-second wait for anything; **any sentence about what could not be checked** |
| 1 | Anything on the product line page navigating to `/changes`. A whole run-through was once spent looking for a review that was on another page |
| 2 | *"NO DESIGN RUNS ON THIS PRODUCT LINE"* on a seeded line, or a brief screen asking what you are building about a product that has a revision and a KiCad project |
| 3 | A product line reporting no board, two of them reporting the same one, or the **BOARD** toggle missing before a review has run |
| 4 | **2027-09-30 as the last order date.** That is the last time *ship* date, and it is the mistake this document was built to catch |
| 4 | Nothing appearing at all, which almost always means the message went to spam |
| 5 | Three identical answers; three columns of streaming monospace side by side; a rejection with no sentence; expanding one lane collapsing another; the lanes sitting on CHECKING with nothing above them |
| 7 | The applied part with no manufacturer or no footprint. Resolving a part by MPN alone is ambiguous, three manufacturers list AMS1117-3.3, and this is the screen where that failure shows |
| 7 | The verdict chip reading **NO VIABLE PART** on a board that shipped |
| 8 | The regulator staying red for the whole run; a green tick beside a sentence about a part that failed; the review opening a different page; a board picture that is a stamp in the middle of a black rectangle |
| 8 | A board consequence for a part with no pinout on file. Ask for `LD1117S33TR` and it must refuse by name, because ST publishes its pin connections as a figure and a figure is not extractable text |
| 9 | Clicking a notice opening the change request instead of the notice |
| 10 | Another company's parts on `/memory`, or one approval listed twice |
| extras | The PCN-2026-118 issue date of 2026-09-01 appearing as a last order date, or a part called `none` being proposed. Both passed every check this system had before item 17 |

**The first row is not a style note.** A product whose pitch is that it checks parts must never
open by naming the ones it did not. Coverage honesty belongs in the change request, where
somebody is deciding whether to sign. See BUILD.md's second governing rule.

---

## 4 · Every route

| Route | What it is |
|---|---|
| `/` | landing |
| `/signup`, `/login` | email and password, no verification, no reset |
| `/lines` | every product line this company ships |
| `/lines/:id` | one product, as a workspace: power tree or board, bill, its own review, and the notice against it |
| `/design/:lineId` | the run in which this line was described; a brief screen only if it has none |
| `/design` | single-user local mode, no account |
| `/changes` | notices received, the company-wide review in lanes, the change requests |
| `/matrix` | every candidate against every product line |
| `/memory` | the company's record: parts, boards, notices, and what was decided |

Endpoints with no screen, worth knowing about:

```bash
curl -s -b cookies.txt 'http://localhost:8000/exposure?mpn=AMS1117-3.3'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/bom'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/reviews'      # a finished review, replayed
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/render' # the board, cached after the first
```

---

## 5 · Replay, which is the default

`./demo.sh` sets `CONTINUITY_FIXTURES=1`. Every distributor call replays from
`backend/fixtures/`, 617 recordings committed so a fresh clone has them, and none of them
touches the network.

**Measured on 10 Sep.**

| | Live | Replayed |
|---|---|---|
| One product line | 52 s one day, **unfinished after 140 s** the next | — |
| All three | — | **0.25 s** |

Same frames, same verdicts, same margins: TLV1117LV33DCYR at 35 °C on the Gateway,
NCP1117ST33T3G at 84 °C on the Sensor node and 11 °C on the Cabinet controller. Only the
distributor's answers come off disk. The engine, every rule, KiCad and the model all still run,
and a call with no recording is an **error** rather than a silent live fetch, because a replay
run that quietly reaches the internet looks offline right up until the wifi fails.

```bash
./demo.sh --live      # go to the distributor, and record what comes back
```

Run that when a part, a bill or a search query has changed and the recordings need refreshing.
It is slow for the reason above, and it is the only way new fixtures are made.

**One step never replays: reading a change notice.** That calls the model directly and has no
recorded path, so on a dead network the upload fails. Receive the notice while you have a
connection, and everything after it replays.

Two consequences of the live path are worth knowing when you run with `--live`. The lanes are
quiet for a stretch between the candidate list and the first line about a board, while that
line's own parts resolve. And `_catalogue_search` is unbounded, which is where the 140 seconds
went. Both are in [DEFERRED.md](DEFERRED.md); neither is visible under replay.

The demo consequence of the speed, which is a choice rather than a defect, is in
[DEMO-DAY.md](DEMO-DAY.md).

---

## 6 · Checks

```bash
cd backend

# offline, no infrastructure
../.venv/bin/python -m pytest                                    # 920 passed, 213 skipped, ~9s

# with a database
CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1115 passed, 20 skipped, ~30s

# with a database and KiCad
CONTINUITY_KICAD=docker CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1125 passed, 8 skipped, ~130s

# the eight that still skip: five need the network, two need a real model, and one is
# the answer given when KiCad is absent
CONTINUITY_LIVE=1 ../.venv/bin/python -m pytest tests/test_parts.py tests/test_notice_document.py

cd ../frontend && bun run build     # tsc first, then the bundle
```

`tools/eol_differential.py` prints the demo matrix from the command line, and
`tools/brief_sweep.py` sweeps briefs for thin evidence.

---

## 7 · Environment

| Variable | Default | For |
|---|---|---|
| `DATABASE_URL` | *(unset)* | Postgres. Unset means single-user, in-memory, no accounts |
| `CONTINUITY_ORIGINS` | `http://localhost:5173,http://localhost:5174` | origins allowed to send the session cookie |
| `CONTINUITY_LLM_API_KEY` | *(from `backend/.env`)* | parsing and repair. Absent is degraded, not fatal |
| `CONTINUITY_LLM_BASE_URL` | z.ai | set to `https://api.deepseek.com` for DeepSeek |
| `CONTINUITY_FIXTURES` | `0` | `1` replays recorded distributor calls and never goes live |
| `CONTINUITY_FIXTURE_DIR` | `backend/fixtures` | point elsewhere to record without touching the committed set |
| `CONTINUITY_KICAD` | *(unset)* | `docker` or `local`. Unset means the board view reports itself unavailable |
| `CONTINUITY_KICAD_IMAGE` | `kicad/kicad:9.0` | the pinned image |
| `CONTINUITY_KICAD_PLATFORM` | `linux/amd64` | required on Apple silicon |
| `CONTINUITY_MAIL_HOST` | *(unset)* | IMAP host, e.g. `imap.gmail.com`. All three, or the poller does not start |
| `CONTINUITY_MAIL_USER` | *(unset)* | the mailbox address |
| `CONTINUITY_MAIL_PASSWORD` | *(unset)* | an app password, not the account password |
| `CONTINUITY_MAIL_ORG` | *(unset)* | whose notices these are. An email address, or an org id. Unset means the only company, when there is one |
| `CONTINUITY_TEST_DB` | *(unset)* | database for the persistence and ownership suites |
| `CONTINUITY_LIVE` | `0` | `1` runs the network and model tests too |

---

## 8 · When something looks wrong

| Symptom | Cause |
|---|---|
| A notice is already there before step 4 | The world was carried over from an earlier run. Start `./demo.sh` without `--keep` |
| Every call fails, console shows CORS | Vite is not on 5173 or 5174. Restart with `--strictPort` |
| `401` on `/auth/me` before signing in | Normal. Two of these on the landing page are expected |
| The BOARD view says no KiCad is configured | `CONTINUITY_KICAD=docker` was not set on the API, or Docker is not running |
| BOARD takes three seconds the first time | Expected. The render is cached on the bundle after that, and the page warms it on arrival. A server restart empties the cache |
| A reviewed line shows a verdict but no trace | The API predates `/lines/:id/reviews`. Restart it |
| Two identical notices in the drawer | Both forwarded and uploaded, or a reseed re-read the mailed message |
| `no matching manifest for linux/arm64` | The `--platform linux/amd64` flag is missing |
| A notice upload fails with nothing readable | No model key, or no network. The parse is the one step with no offline path |
| The run finishes fast with no real MPNs | `CONTINUITY_LLM_API_KEY` did not load |
| A review dies on its second frame saying the part could not be sourced | A distributor call has no recording. `./demo.sh --live` records it |
| Accounts vanish on restart | The API was started without `DATABASE_URL` |
| Twelve collection errors from pytest | Anaconda's Python. Use `.venv/bin/python` |
| A forwarded notice never appears | It is in spam. `tools/check_mail.py` says so and names the filter |
| The mailbox is configured and nothing polls | More than one company and no `CONTINUITY_MAIL_ORG` |
| A mailed notice appears against no product lines | `CONTINUITY_MAIL_ORG` holds an organisation id from before a reseed. Use the address form |
| `--reset` fails on `decisions_line_id_fkey` | Fixed 8 Sep. An old `tools/seed_world.py` |

---

## 9 · Known, and not a bug

[DEFERRED.md](DEFERRED.md) carries everything found and not fixed, with a severity against
each. These are the ones a run-through walks into, so they are not worth reporting twice.

- ~~**Every lane ends at engineering.**~~ **Moved out of this list on 10 Sep. It is a 🔴 open
  defect, not a known limitation.** The cause is not the seeded world: `review.choose` hardcodes
  engineering for any candidate that clears, and there is no production role in the product,
  which is one of the three departments the assigned scenario names. Report anything about it
  against the two 🔴 rows in [DEFERRED.md](DEFERRED.md).
- **An engineer can qualify a part alone.** `roles.py` addresses `part_qualification` to
  engineering *and* quality with the words "it needs both", and the code reads that list as
  "any one of these may answer". Faithful would be two signatures, which the `decisions` row
  cannot express: it has one state and one `decided_by`. 🟡
- **The annual volume has no input any more**, so every change request is missing the recurring
  half of its cost and says *"no annual volume stated"*. It belongs on the product line beside
  the ambient rather than being typed per review. 🟡
- **Applying a decision writes the distributor's manufacturer**, so the Gateway's bill reads
  `TLV1117LV33DCYR · JSMSEMI` where the part is Texas Instruments'. 🟡
- **A deployed instance has no KiCad**, so the board section is unavailable anywhere but a
  machine with the container.
- **The board consequence is not stored**, so it is not part of the change request document and
  is computed again on a later visit. The picture itself is cached per board for as long as the
  API is up, so it costs about three seconds once and nothing afterwards.
- **A replayed review cannot say where each candidate came from.** The live trace narrates
  *"Trying LD1117-3.3 — found in the distributor's catalogue"*; only the manufacturer and
  package are stored per attempt, so the replay says *"Trying LD1117-3.3."* One field would
  close it.
- **A review left waiting on a desk replays without its buttons.** Reopening the line shows its
  trace and its proposal; whether that decision is still answerable is the decision row's
  business, and the trace does not re-raise the question.
- **The AML and AVL have no screen.** The lists are read correctly by the gates and written only
  by the seed and the store. Memory shows what was decided against them, which is the part a
  person asks about.

---

## 10 · Worth knowing about the boards

OpenJBOD carries 687 copper zones and found two defects the day it arrived, both fixed. The
details are in `backend/fixtures/kicad/README.md`.

KiCad's DRC is not deterministic for `unconnected_items`, so the tests key on the **net**. Zones
are refilled before DRC, and one board is opened per `pcbnew` interpreter.
