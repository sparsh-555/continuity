# RUNNER.md

Everything needed to start Continuity from cold and walk through every capability that is in
the app today, in the order that tells the story. Written to be followed literally.

`RUN.md` at the repository root is the older, developer-facing version of this and is still
accurate about the design flow. This file is the finals build, end to end.

---

## 0 · Once, before anything

```bash
pg_isready                              # expect: accepting connections
createdb continuity_demo                # the world the demo happens inside
createdb continuity_test                # only needed to run the suite

ls .venv/bin/python                     # expect a path, not "No such file"
cd frontend && bun install && cd ..

# The model key. Reading a change notice is the one step that needs it.
cd backend && ../.venv/bin/python -c "from continuity import llm; print(llm.available())"
```

`True` means real parsing. **`False` is not a crash**, which is exactly why it is worth
checking: the app keeps running and every field that needs a model comes back unchecked.

**For the board view**, Docker Desktop must be running and the pinned image pulled:

```bash
docker pull --platform linux/amd64 kicad/kicad:9.0        # about 2 GB, once
docker run --rm --platform linux/amd64 kicad/kicad:9.0 kicad-cli version   # expect 9.0.9
```

The `--platform` flag is not optional on Apple silicon. That tag is amd64 only, whatever the
Docker Hub page says, and emulation is what runs it.

---

## 1 · Three terminals

### Seed the world

```bash
cd backend
PYTHONPATH=. ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo
```

Add `--reset` to replace a world that is already there. It prints what it built, ending with
the five product lines and their ids. **If it prints nothing about an AML, stop** — the
qualification gate is half the story.

### The API

```bash
cd backend
DATABASE_URL=postgresql:///continuity_demo CONTINUITY_KICAD=docker \
  ../.venv/bin/python -m uvicorn continuity.api.app:app --port 8000
```

Expect `persistence: postgres` in the startup lines. If it says single-user and in-memory,
`DATABASE_URL` did not reach it and there are no accounts at all.

`backend/.env` points `DATABASE_URL` at **production Neon**. Naming the database on the
command line as above is what keeps a local run local. Never start the API without it.

### The UI

```bash
cd frontend
VITE_API_URL=http://localhost:8000 bun run dev --strictPort --port 5173
```

`--strictPort` matters. If Vite quietly takes 5174 or 5175, the browser blocks every API call
on CORS and the app looks broken without naming the cause. To use another port, add it to
`CONTINUITY_ORIGINS` on the API.

Open `http://localhost:5173`.

---

## 2 · The world you just seeded

**Northwind Instruments**, two people, five products, both standing lists.

| Account | Password | Roles |
|---|---|---|
| `engineer@northwind.example` | `continuity-demo-2026` | engineering |
| `quality@northwind.example` | `continuity-demo-2026` | quality, procurement |

| Product line | Regulator | Rail | Ambient | Load |
|---|---|---|---|---|
| Sensor node | **AMS1117-3.3** | 5 V | 25 °C | 150 mA |
| Gateway | **AMS1117-3.3** | 5 V | 45 °C | 420 mA |
| Cabinet controller | **AMS1117-3.3** | 12 V | 55 °C | 60 mA |
| Bench supply | TLV1117LV33DCYR | — | — | — |
| Handheld meter | NCP1117ST33T3G | — | — | — |

The **AML is derived from what ships**, which is what an AML is: seven parts, every one of
them already in production. `LD1117S33TR` is absent for an honest reason — nothing ships with
it yet. The **AVL** holds one vendor, JLCPCB.

Three of five lines carry the retired part, so exposure has something to be wrong about. The
three that carry it run at different ambients on different rails, which is what makes one
recommendation right for one product and wrong for another.

---

## 3 · The run-through

### Step 1 · Sign in

`http://localhost:5173` → **GET_STARTED** → sign in as the engineer.

The **first** sign-in on a freshly seeded database lands on `/walkthrough`, a replayed board
that plays once per account. Step through it or skip it; afterwards every sign-in goes
straight to `/lines`.

**Look for:** 33 satisfied, 3 failed, 3 no-evidence, 4 not-applicable, 3 not-assessed, and
one margin. **Would be a bug:** a `pass`, `warn` or `fail` label anywhere — those three words
were retired, and any of them means something is replaying an old vocabulary.

### Step 2 · Attach a board to the Sensor node

Do this before the notice, so the board view has something to answer with.

```bash
cd backend/fixtures/kicad && zip -r ~/ProPico.zip propico && cd -
```

`/lines` → the **⋮** menu on **Sensor node** → **Attach board** → pick `~/ProPico.zip`.

That is [ProPico](https://github.com/diminDDL/ProPico), MIT licensed, drawn in KiCad 7 by
somebody who has never heard of us, carrying a real AMS1117-3.3 in SOT-223 at U3.

**Look for:** *"ProPico attached to Sensor node. The line already had a bill of materials, so
it was kept."* Attaching a project to a line that has no bill adopts the one KiCad reads out
of the schematic instead, and says which field it read the part numbers from.

**Would be a bug:** the seeded bill being replaced without being asked, or a silent success
with no sentence at all.

### Step 3 · The notice

`/notices` → **RECEIVE A NOTICE** → `docs/world-finals/notices/PCN-2026-114.pdf`.

Both notices in that folder are **constructed examples** and say so on their first line and
their last. The provenance is in `docs/world-finals/notices/README.md`.

**Look for:**

- `AMS1117-3.3`, `ADVANCED MONOLITHIC SYSTEMS`, **last order 2027-03-31**, recommends
  `NCP1117ST33T3G`.
- *read from: "Affected part: AMS1117-3.3 (SOT-223)"* — the line the part number was sourced
  from, in the document's own words.
- *Affects 3 product lines: Cabinet controller, Gateway, Sensor node.*

**Would be a bug:** 2027-09-30 as the last-order date. That is the last time **ship** date,
and it is the mistake this document was built to catch.

### Step 4 · The review, and three different answers

In the same panel, type the candidates and a volume, then **REVIEW EVERY AFFECTED LINE**.

```
NCP1117ST33T3G, LD1117S33TR, TLV1117LV33DCYR
20000
```

It takes under a minute against live sourcing. What comes back is one change request per
affected product line, and the three do not agree:

| Product line | Proposal | Why |
|---|---|---|
| Cabinet controller | **NCP1117ST33T3G** | clears everything with 11 °C to spare, already on the AML |
| Gateway | **NO VIABLE PART** | NCP1117 reaches **159 °C against a 150 °C limit**; LD1117 is not qualified |
| Sensor node | **NCP1117ST33T3G** | 84 °C to spare |

That is the whole argument in one screen: the manufacturer's own recommendation is right for
two of these products and would cook the third, and the part that survives the third is
blocked at a different desk for a different reason.

**Look for:** every rejection carrying the sentence that killed it, the evidence rows with
their arithmetic, *Not assessed* and *Could not be checked* kept apart, the cost split, and
the desks that have to sign. Also a **NOT CHECKED** section naming `TLV1117LV33DCYR`, which
JLCPCB lists under two manufacturers and which is therefore excluded rather than guessed at.

**Would be a bug:** three identical answers, a rejection with no sentence, or a cost quoted
for a line with no proposal.

### Step 5 · The board

Inside the **Sensor node** change request, find **THE BOARD** and press
**PLACE NCP1117ST33T3G ON THIS BOARD**. About forty seconds.

**Look for:** *No connections break at U3, SOT-223 → SOT-223*, two crops of the same twelve
millimetres of board, and the datasheet line the pin functions were read from. The two
pictures are all but identical, which is the correct answer for a true drop-in: the pads it
lands on are the pads that are already there.

The other half of the argument is in the tests rather than the demo, because no SOT-23-5 part
is a sourced candidate yet: placing an `ME6211C33M5G-N` at the same position takes unconnected
items from 1 to 4 and adds four shorting items and three clearance violations. See
`backend/tests/test_boards.py::test_a_smaller_package_breaks_connections_on_this_board`.

**Would be a bug:** a picture that is not centred on U3, an answer with no design rule
findings behind it, or a board consequence for a part with no pinout on file. Ask for
`LD1117S33TR` and it refuses by name, because ST publishes its pin connections as a figure
and a figure is not extractable text.

### Step 6 · The matrix, which is the working

`/matrix` → select the three affected lines → position `u1` → candidates:

```
AMS1117-3.3, NCP1117ST33T3G, LD1117S33TR, TLV1117LV33DCYR
```

**CHECK EVERY LINE.** The change request is the deliverable; this is the grid it came from.
Every cell carries the five coverage labels — satisfied, failed, no evidence, not assessed,
n/a — and clicking one opens the evidence for that part on that board.

**Look for:** the same part green on one line and red on another, and a margin printed on a
cell that only just holds. **Would be a bug:** a cell with no counts at all, or a candidate
silently missing from the grid.

### Step 7 · What the reader refuses to invent

`/notices` → **RECEIVE A NOTICE** → `docs/world-finals/notices/PCN-2026-118.pdf`.

This is the preliminary notice. It withholds the two fields a reader is most tempted to fill:
there is no last-order date, and the recommendation is the word *none*.

**Look for:** the subtitle showing the manufacturer alone, with no date clause and no
recommendation clause. **Would be a bug:** the notice's own issue date of 2026-09-01
appearing as the last-order date, or a part called `none` being proposed. Both would have
passed every check this system had before item 17.

### Step 8 · A design run, and a decision that is not the engineer's

The EOL flow above is the finals scenario. The design flow is the Singapore one, and it still
runs.

`/lines` → **NEW PRODUCT LINE** → type a brief and press Enter:

```
temp and humidity sensor, wifi and ble, usb-c powered with li-ion backup, small oled
```

Fifty to a hundred and thirty seconds against live sourcing. Inside Northwind the AML is
live, so the run stops on the first part that is not on it:

> The TP4056 is unqualified for production, but neither available replacement shares its
> ESOP-8 footprint, so a direct substitution would require a board revision.

That question carries `roles: ["engineering", "quality"]` on the wire. Answer it with
**Qualify this part for use** and a rationale, and an `approval` event goes into the trace
carrying who approved it, the rule, the part, the revision and the reason. `/resume` enforces
the role at the HTTP boundary, so a decision addressed to procurement is refused for an
engineer with a 403 rather than being quietly accepted.

**A brand-new signup gets its own company with no lists kept**, and there the design flow
plays exactly as it did in Singapore, with no qualification gate at all. `None` for a list
that is not kept and an empty list that approves nothing are different things, and this is
where the difference shows.

**Would be a bug:** a gate that fires with nobody named, an approval with no author, or a run
that continues past an unqualified part without asking.

### Step 9 · Memory

`/memory`. Parts and boards the company has seen, with the findings attached to each. Search
by MPN.

**Look for:** the parts from the runs above, and findings that name the board they happened
on. **Would be a bug:** another organisation's parts appearing here.

---

## 4 · Every route

| Route | What it is |
|---|---|
| `/` | landing |
| `/signup`, `/login` | email and password, no verification, no reset |
| `/walkthrough` | the replayed board, once per account |
| `/lines` | the dashboard, and where a KiCad project is attached |
| `/design/:lineId` | brief entry, then the workspace |
| `/design` | single-user local mode, no account |
| `/notices` | receive a notice, review it, read the change requests, check the board |
| `/matrix` | every candidate against every product line |
| `/memory` | what the company has seen |

Two endpoints have no screen and are worth knowing about:

```bash
curl -s -b cookies.txt 'http://localhost:8000/exposure?mpn=AMS1117-3.3'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/bom'
```

---

## 5 · Rehearsing without a network

```bash
CONTINUITY_FIXTURES=1 DATABASE_URL=postgresql:///continuity_demo CONTINUITY_KICAD=docker \
  ../.venv/bin/python -m uvicorn continuity.api.app:app --port 8000
```

Distributor calls replay from `backend/fixtures/` and never touch the network. A call with no
recording is an error rather than a silent live fetch, which is the point: a fixture run that
quietly reaches the internet looks offline right up until the wifi fails. Part normalisation
and datasheet readings come from `backend/cache/`.

**One step is not covered: reading a change notice.** That calls the model directly and has
no recorded path, so on a dead network the upload fails. Receive the notice while you have a
connection — it is stored — and everything after it replays offline.

---

## 6 · Checks

```bash
cd backend

# offline, no infrastructure
../.venv/bin/python -m pytest                                    # 834 passed, 165 skipped, ~9s

# with a database
CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 981 passed, 18 skipped, ~22s

# with a database and KiCad
CONTINUITY_KICAD=docker CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 991 passed, 8 skipped, ~88s

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
| `CONTINUITY_TEST_DB` | *(unset)* | database for the persistence and ownership suites |
| `CONTINUITY_LIVE` | `0` | `1` runs the network and model tests too |

---

## 8 · When something looks wrong

| Symptom | Cause |
|---|---|
| Every call fails, console shows CORS | Vite is not on 5173 or 5174. Restart with `--strictPort` |
| `401` on `/auth/me` before signing in | Normal. Two of these on the landing page are expected |
| The board section says no KiCad is configured | `CONTINUITY_KICAD=docker` was not set on the API, or Docker is not running |
| `no matching manifest for linux/arm64` | The `--platform linux/amd64` flag is missing |
| A notice upload fails with nothing readable | No model key, or no network. The parse is the one step with no offline path |
| The run finishes fast with no real MPNs | `CONTINUITY_LLM_API_KEY` did not load |
| Accounts vanish on restart | The API was started without `DATABASE_URL` |
| Twelve collection errors from pytest | Anaconda's Python. Use `.venv/bin/python` |

---

## 9 · What is deliberately not here

[DEFERRED.md](DEFERRED.md) carries everything found and not fixed, with a severity against
each. The ones that will be noticed during a run-through:

- **A deployed instance has no KiCad**, so the board section is unavailable anywhere but a
  machine with the container.
- **The board consequence is not stored**, so it is not part of the change request document
  and has to be asked for again on a later visit.
- **The AML and AVL have no screen.** The lists are read correctly by the gates and written
  only by the seed and the store.
- **Approvals are recorded and never shown.** They stream into the trace as they happen, and
  no view reads them back.
- **A successful precedent is never written.** Rejections are; a success needs the moment a
  substitution is accepted rather than proposed.
