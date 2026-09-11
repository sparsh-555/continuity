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
| recordings | no | With none in `backend/fixtures/`, every distributor call and every notice reading fails. `--live` records them as it goes |

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

**`backend/.env` names `postgresql:///continuity_demo`, and that is deliberate.** It used to
point at production Neon, so a local run started without an override wrote real rows — the
hazard was closed on 11 Sep by making the local database the default. Production is the one
URL you name explicitly, never the one you fall into; `env.load` lets an injected platform
variable win over the file, so the deployed instance is unaffected either way.

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
| 6 | The bill changing on the first signature. Every department that examined the change signs it, and it applies on the last one |
| 6 | A department block naming a part other than the one being substituted. Every rule runs on every slot, and a desk's line is about the change |
| 6 | The same desk signing twice, or one desk's signature recorded against another desk |
| 9a | A decision this desk has already signed still showing live buttons, or a desk with nothing waiting showing an error rather than saying so |
| 9a | The count on the rail disagreeing with the number of rows that can be acted on |
| 9b | The Gateway's bill reading **JSMSEMI** rather than Texas Instruments; U1 green, or U1 red, where a desk accepted the shortfall; a review pane saying *nothing failed* on a board that has an accepted failure |
| 10 | A retired part drawn in the same orange as every other, its edges drawn like healthy ones, or a graph with no legend |
| any | A power-tree legend offering a state nothing on that board is in. It is derived from the slots it was handed, so a board at rest offers *Fitted · unchecked* and a running one offers what it has |
| any | A change request saying a rule could not be checked. `emc`, `output_capacitor_stability` and `signal_integrity` became real checks on 11 Sep and **no request admits a gap any more** — the figures `signal_integrity` stacks are hand-read datasheet values on the dossier, so losing them is silent: the rule declines and the document says so rather than failing |
| 10 | Another company's parts on `/memory`, or one approval listed twice |
| any | The desk switcher offering a session this browser has not signed into, or a switch that does not change what the app says you hold |
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
| `/changes` | notices received, the company-wide review in lanes, the change requests, and what this desk owes |
| `/memory` | the company's record: parts, boards, notices, and what was decided |
| `/policy` | the approved manufacturer list and the approved vendor list, where a company states them. Parts are engineering's and quality's to qualify, sources are procurement's alone, and every part a board carries that is not qualified is named with the action that clears it |

Endpoints with no screen, worth knowing about:

```bash
curl -s -b cookies.txt 'http://localhost:8000/exposure?mpn=AMS1117-3.3'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/bom'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/reviews'      # a finished review, replayed
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/render' # the board, cached after the first
curl -s -b cookies.txt 'http://localhost:8000/decisions'               # what this desk owes
curl -s -b cookies.txt 'http://localhost:8000/auth/sessions'           # desks this browser holds
```

**Signing a substitution** takes one call per department, in any order, and the change
applies on the last one:

```bash
curl -s -b cookies.txt -X POST 'http://localhost:8000/decisions/<id>' \
  -H 'Content-Type: application/json' -d '{"approve": true}'
# {"state": "pending", "signed": ["engineering"], "outstanding": ["procurement", ...]}
```

---

## 5 · Replay, which is the default

`./demo.sh` sets `CONTINUITY_FIXTURES=1`. Every distributor call and every reading of a
change notice replays from `backend/fixtures/`, 622 recordings committed so a fresh clone has
them, and none of them touches the network.

**Measured on 10 Sep.**

| | Live | Replayed |
|---|---|---|
| One product line | 52 s one day, **unfinished after 140 s** the next | — |
| All three | — | **0.25 s** computed; **~20 s** as it plays back |
| Reading `PCN-2026-114.pdf` | 1903 ms | **7 ms** |

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

**Reading a change notice replays too, as of 10 Sep.** Both committed notices are recorded,
keyed on a digest of the extracted text and a fingerprint of the reader's instructions — so a
reworded prompt re-reads rather than believing an answer to a different question. The
verification runs on the replayed reply exactly as on a live one: a recording is the model's
answer, not a licence to believe it, and a quoted line the document does not contain is still
refused.

**A notice nobody has recorded is refused, not fetched.** Forwarding some other PDF under
replay returns *no fixture for notice_read*, which is the same contract every distributor call
keeps. To demonstrate a new notice, record it first:

**Changing the reader's prompt invalidates every notice recording**, by design — a recording
made under one prompt is not an answer to a different one. That is not hypothetical: P9 added
`reference` and `reference_line` to what the reader is asked for on 11 Sep, both committed
recordings went stale in the same edit, and the demo's first step would have refused. The
remedy is the command below, run once, and it is worth running whenever `notices.SYSTEM`
changes. A quick way to tell before starting a demo:

```bash
cd backend && ../.venv/bin/python -c "
import pathlib, sys; sys.path.insert(0, '.')
from continuity import notices
pdf = pathlib.Path('../docs/world-finals/notices/PCN-2026-114.pdf').read_bytes()
call = notices._recording_for(notices.text_of(pdf))
key = notices.fixtures.key_for(notices.READ_TOOL, call)
print('HIT' if pathlib.Path(f'fixtures/notice_read.{key}.json').exists() else 'MISS — record it')"
```

```bash
./demo.sh --live      # then forward the new document once
```

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
../.venv/bin/python -m pytest                                    # 959 passed, 238 skipped, ~9s

# with a database
CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1177 passed, 20 skipped, ~30s

# with a database and KiCad
CONTINUITY_KICAD=docker CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1189 passed, 8 skipped, ~145s

# the eight that still skip: five need the network, two need a real model, and one is
# the answer given when KiCad is absent
CONTINUITY_LIVE=1 ../.venv/bin/python -m pytest tests/test_parts.py tests/test_notice_document.py

cd ../frontend
bun run build     # tsc first, then the bundle
bun run test      # the pure decisions behind the screens
bun run lint      # oxlint; warnings only, no errors
bun run e2e       # a real browser, against a running ./demo.sh
```

**`bun run e2e` needs a world nobody has touched**, because it asserts `End of life (0)`
before delivering the notice. Start `./demo.sh` without `--keep` and run it once. It reads
its credentials from the environment and never from source:

```bash
CONTINUITY_E2E_EMAIL=engineer@northwind.example \
CONTINUITY_E2E_PASSWORD=continuity-demo-2026 bun run e2e
```

**`bun test` on its own sweeps `e2e/` too** and fails on it, which is why `bun run test` is
scoped to `src`. Playwright specs are not bun tests.

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
| `CONTINUITY_FIXTURES` | `0` | `1` replays recorded distributor calls and notice readings, and never goes live |
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
| A signature does not change the bill | Expected. Every department that examined the change signs it, and it applies on the last one. The reply says who it is waiting for |
| `already signed this` on a second press | Expected. A desk signs once; the message names who is outstanding |
| The desk switcher offers nothing to switch to | Only sessions this browser has signed into appear. Sign in as that desk once and both stay live |
| The mailbox poll fails on a foreign key after a reseed | The poller resolved the organisation at startup and the reseed replaced it. Restart the API |
| The mailbox refuses the sign-in: `[ALERT] Invalid credentials` | **Throttling, not a wrong password.** Gmail closes an account that authenticates too often; `./demo.sh --check` now signs in and says so rather than reporting the variables are present. It clears in minutes, and it is why the poller idles at Google's documented ten minutes when nobody is watching |
| `the poller would read the whole inbox` after a start | The seed could not reach the mailbox, so no read position was stored and every message in the inbox counts as new. Get the mailbox answering and run `./demo.sh` again before step 4 — the seed sets the position, and `poll_once` catches up on its own if it is still missing |
| No notice arrives after forwarding one, and the application is open | The mailbox is being polled at Google's ten minutes because nothing has asked for notices. Any authenticated screen asks every ten seconds, so this means no browser tab is open on the application |
| Every call fails, console shows CORS | Vite is not on 5173 or 5174. Restart with `--strictPort` |
| `port 8000 is in use` after a clean `--stop` | Fixed 10 Sep. An old `demo.sh` counted a browser's leftover socket as the port being taken; the check now looks for a listener |
| `401` on `/auth/me` before signing in | Normal. Two of these on the landing page are expected |
| The BOARD view says no KiCad is configured | `CONTINUITY_KICAD=docker` was not set on the API, or Docker is not running |
| BOARD takes three seconds the first time | Expected. The render is cached on the bundle after that, and the page warms it on arrival. A server restart empties the cache |
| BOARD takes three seconds again on the same page | Fixed 10 Sep. Placements are remembered for the session; a second **PLACING…** for a board already placed means an old build |
| The board crops are empty, caption and border still there | Fixed 10 Sep. The SVG's blob URL was revoked by an effect cleanup a remount did not repeat. `net::ERR_FILE_NOT_FOUND` in the console names it |
| A reviewed line shows a verdict but no trace | The API predates `/lines/:id/reviews`. Restart it |
| A change request shows *PLACE … ON THIS BOARD* a minute after a run | The placement had not landed when the card loaded. Reload once; if it persists the instance has no KiCad, which is the honest case that button is for |
| `/changes` shows no lanes on a notice that was reviewed | The API predates `/notices/:id/reviews`, or the run predates the `decisions` rows that back it. Restart it, then **RUN IT AGAIN** once |
| `POST /notices/{id}/review` refuses with *the retired part sits at different positions* | Fixed 11 Sep. Only an old build does this: each board is now substituted at its own position |
| Two identical notices in the drawer | Both forwarded and uploaded, or a reseed re-read the mailed message |
| `no matching manifest for linux/arm64` | The `--platform linux/amd64` flag is missing |
| A notice upload fails saying `no fixture for notice_read` | That document has never been read **under this prompt**. Changing `notices.SYSTEM` restages every recording. `./demo.sh --live`, forward it once, and it replays from then on |
| A notice upload fails with nothing readable | No model key under `--live`, or the document genuinely holds no part number backed by a line of its own text |
| The run finishes fast with no real MPNs | `CONTINUITY_LLM_API_KEY` did not load |
| A review dies on its second frame saying the part could not be sourced | A distributor call has no recording. `./demo.sh --live` records it |
| Accounts vanish on restart | The API was started without `DATABASE_URL` |
| Two notice rows show the same date when they arrived on different days | Fixed 11 Sep. The label rendered a UTC slice; it now renders the reader's own day |
| Twelve collection errors from pytest | Anaconda's Python. Use `.venv/bin/python` |
| A forwarded notice never appears | It is in spam. `tools/check_mail.py` says so and names the filter |
| The mailbox is configured and nothing polls | More than one company and no `CONTINUITY_MAIL_ORG` |
| A mailed notice appears against no product lines | `CONTINUITY_MAIL_ORG` holds an organisation id from before a reseed. Use the address form |
| `--reset` fails on `decisions_line_id_fkey` | Fixed 8 Sep. An old `tools/seed_world.py` |

---

## 9 · Known, and not a bug

[DEFERRED.md](DEFERRED.md) carries everything found and not fixed, with a severity against
each. These are the ones a run-through walks into, so they are not worth reporting twice.

**Three entries left this list on 10 September because Phase 8 built them:** every lane ending
at engineering, an engineer qualifying a part alone, and no desk being told a decision was
waiting for it. Do not re-report those.

- **The quality gate does not fire in the seeded world.** The Gateway now stops at
  *procurement* on a stock shortfall, so one notice does produce answers that halt in different
  places — but no line's best answer is off the approved manufacturer list, so the
  qualification gate itself is still unexercised. 🟡
- **The recurring half of the cost once said *"no annual volume stated"* on every request.**
  Every operating profile carries an annual volume with its own source now, so the Gateway
  reads **$2,344 a year** under *+$0.1172 a unit at 20,000/yr*. Closed in the third pass; the
  line stays here because a request reading *no annual volume stated* is a regression rather
  than an unknown.
- **Applying a decision writes the distributor's manufacturer**, so the Gateway's bill reads
  `TLV1117LV33DCYR · JSMSEMI` where the part is Texas Instruments'. 🟡
- **A deployed instance has no KiCad**, so the board section is unavailable anywhere but a
  machine with the container.
- **The board consequence is stored on the change request and nothing renders it there.**
  `attach_board_consequence` writes it seconds after the document is written, and the card
  carried it until 11 September, when the pictures moved to the product line's own BOARD pane.
  The background KiCad run still happens. 🟡
- **A review that ran before 11 September replays one lane at a time.** The run records the
  frames it streams, so a review from now on replays with three boards advancing together; a
  decision written before the column existed has no stored order and falls back to the
  per-decision rebuild. Re-run the notice to get the recorded order.
- **The AML and AVL are stated at `/policy`.** The lists were read by the gates and written only
  by the seed until 11 September; parts are engineering's and quality's to qualify, sources are
  procurement's alone, and every part a board carries that is not qualified is named with the
  action that clears it.
- **A mailed notice raises no notification.** `/changes` is the only screen that reacts to one
  on its own, and `/lines` needs a reload. This is the last 🔴 and it is BUILD item 28.
- **The outbound approval request does not exist.** A desk finds what it owes at the top of
  `/changes`, or on the rail badge beside it; nothing goes out to tell it. The in-app queue is
  the demo-safe half. 🟡

---

## 10 · Worth knowing about the boards

OpenJBOD carries 687 copper zones and found two defects the day it arrived, both fixed. The
details are in `backend/fixtures/kicad/README.md`.

KiCad's DRC is not deterministic for `unconnected_items`, so the tests key on the **net**. Zones
are refilled before DRC, and one board is opened per `pcbnew` interpreter.
