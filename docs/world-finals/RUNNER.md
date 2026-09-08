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

# The mailbox, if the notice is to arrive by email rather than by upload.
cd backend && ../.venv/bin/python tools/check_mail.py
```

`True` means real parsing. **`False` is not a crash**, which is exactly why it is worth
checking: the app keeps running and every field that needs a model comes back unchecked.

**There is nothing to paste.** The key lives in `backend/.env`, which is gitignored, and
`continuity/env.py` walks upward from wherever the process starts, so it is found whether you
launch from the repository root or from `backend/`. Local Postgres authenticates by user
rather than by password, which is why every database URL here is `postgresql:///name` with no
credentials in it. The KiCad image is public and needs no Docker login. The only credentials
you type anywhere are the two demo accounts in §2.

If the key ever has to be replaced, put the new one in `backend/.env` as
`CONTINUITY_LLM_API_KEY=…` and set `CONTINUITY_LLM_BASE_URL=https://api.deepseek.com`
beside it. Do not echo it into a terminal on the way there: scrollback outlives the command.

`check_mail.py` should say `signed in` and a message count. If it warns that messages are
sitting in a spam folder, one of them is probably the notice: the poller reads `INBOX` only,
on purpose, because acting on a document the provider has judged hostile is not a thing to do
in a system whose output is an engineering change request. Fix it with a Gmail filter rather
than by reading the folder. `not configured` means the three `CONTINUITY_MAIL_*` variables are
not in `backend/.env`, and the whole demo still runs by upload.

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

**If the notice is to arrive by email**, `backend/.env` also needs the line that says whose
mailbox it is:

```
CONTINUITY_MAIL_ORG=engineer@northwind.example
```

An address rather than an organisation id, because a reseed mints a new id every time and a
stale one fails by quietly finding no product lines. With exactly one company in the database
this can be left out entirely; the demo world has two if anybody has ever signed up, which is
why it is here.

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

This is the beat in the order it is told. Nine steps, about twenty minutes at a walk.

The story it tells: a company's products are described here, a change notice arrives by
email, Continuity finds every product that carries the retired part, re-checks all of them
at once, reaches a different answer for each, asks the desk that owns the failing rule, and
on approval changes the part in the bill of materials, on the power tree and on the board.

### Step 1 · Sign in, and what a product line is

`http://localhost:5173` → **GET_STARTED** → sign in as the engineer.

You land on `/lines`. There is no tour and no first-run redirect; both were deleted with the
walkthrough on 8 September.

**Say what this is.** Five product lines. Each one is a thing Northwind ships: a revision, a
bill of materials by reference designator, an operating profile, and a KiCad project. That
is what a company knows about its own products, and it is what everything after this reads.

Click **Sensor node**.

**Look for**, on `/lines/:id`, in this order down the page:

- The subtitle: `Rev C · 3 parts · 25 °C ambient` and the rails.
- **The power tree.** Which part makes each rail and what that rail feeds, drawn from the
  operating profile the line states. The caption says plainly that nothing here has read a
  schematic, because the picture would otherwise be taken for one.
- **Bill of materials**: `U1 AMS1117-3.3`, with the manufacturer and the footprint.
- **Board**: whether a KiCad project is attached.

**Would be a bug:** the words *"What are you building?"*, or a status computed from whether
somebody has run a design here. A product line is not a run. Both were true in the build
before 8 September and both are what Phase 5 exists to have fixed.

### Step 2 · How a product line gets here

Back to `/lines` → **NEW PRODUCT LINE**.

You do not have to finish this. The point is to show the way in: an engineer describes the
product, or uploads a bill of materials, and from then on Continuity knows what the company
ships. Press escape and go back.

**Then say the line that frames everything after it:** *these are Northwind's five product
lines, and three of them carry the same regulator.*

### Step 3 · Attach a board to the Sensor node

Do this before the notice, so the board view has something to answer with.

```bash
cd backend/fixtures/kicad && zip -r ~/ProPico.zip propico && cd -
```

On `/lines/Sensor node` press **ATTACH BOARD** and pick `~/ProPico.zip`.

That is [ProPico](https://github.com/diminDDL/ProPico), MIT licensed, drawn in KiCad 7 by
somebody who has never heard of us, carrying a real AMS1117-3.3 in SOT-223 at U3.

**Look for:** *"ProPico attached to Sensor node. The line already had a bill of materials, so
it was kept."* **Would be a bug:** the seeded bill replaced without being asked, or a silent
success with no sentence.

### Step 4 · The notice arrives by email

This is the trigger, and it is the step that changed most.

Open `/notices` and leave it on screen. Then, from your own mail, forward
`docs/world-finals/notices/PCN-2026-114.pdf` to the mailbox in `backend/.env`, **with a
subject line**.

Within about fifteen seconds the server reads it, and within ten more the screen shows it
without anybody pressing anything.

**Say the cost while it flies.** Resolving an end-of-life part with one that is already
approved costs about $1,300. Redesigning the board costs upwards of $950,000. What separates
them is whether anyone can prove the cheaper option works, and industry averages forty weeks
over that proof.

**Look for:**

- `AMS1117-3.3`, `ADVANCED MONOLITHIC SYSTEMS`, **last order 2027-03-31**, recommends
  `NCP1117ST33T3G`.
- *read from: "Affected part: AMS1117-3.3 (SOT-223)"* — the line the part number came from,
  in the document's own words.
- *Affects 3 product lines: Cabinet controller, Gateway, Sensor node.*

**Would be a bug:** 2027-09-30 as the last order date. That is the last time **ship** date and
it is the mistake this document was built to catch. Also a bug: nothing appearing at all,
which almost always means the message went to spam. `../.venv/bin/python tools/check_mail.py`
says so in one line.

**The fallback, if the mailbox cannot be reached:** press **RECEIVE A NOTICE** and pick the
same PDF. Everything after this point is identical, and nothing downstream knows or cares how
the notice arrived.

### Step 5 · The review, and three different answers

Press **START THE REVIEW**.

Do not type anything into **TRY A PARTICULAR PART TOO**. The candidates are *found*, and
saying so is the point: the notice's own recommendation first, then the approved manufacturer
list in the same category, then the distributor's catalogue in the same package. That box is
an override for a part somebody wants tried anyway, and it is deliberately not the way in.

Three columns run **at the same time**, on one stream, and the discovery lines above them are
said once because the same part is retired on every board. About a minute against live
sourcing.

| Product line | Answer | Why |
|---|---|---|
| Cabinet controller | **NCP1117ST33T3G** | clears everything with 11 °C to spare |
| Gateway | **TLV1117LV33DCYR** | 35 °C to spare, after NCP1117 reaches **159 °C against a 150 °C limit** |
| Sensor node | **NCP1117ST33T3G** | 84 °C to spare |

That is the whole argument in one screen. The manufacturer's own recommended replacement is
right for two of these products and would cook the third, and the third survives on a
different part for a reason that is about that board and no other.

**Look for:** every rejection carrying the sentence that killed it, the desk named above each
question before the buttons rather than after, and `LD1117-3.3` surfacing from the catalogue
as *electrically fine here, and not on the approved manufacturer list*.

**Would be a bug:** three identical answers, a rejection with no sentence, or the columns
sitting on CHECKING with nothing above them for forty seconds.

**Known, and worth saying before a judge asks:** every column currently ends at engineering,
because TLV1117 is on the AML and clears the Gateway. The *"this is not your decision"* beat
does not fire in the seeded world. It is logged 🟡 in [DEFERRED.md](DEFERRED.md).

### Step 6 · Approve, and watch the product change

In the **Sensor node** column, press **APPROVE AND APPLY**.

**Look for:** *Applied · U1 is NCP1117ST33T3G · Rev D*.

Four things happened in that one press, and they are the difference between a recommendation
and a change:

- the part was written into the bill of materials,
- the revision moved from Rev C to Rev D,
- the approval was recorded with who signed it and why,
- and the **successful precedent** was written, so the next notice does not re-litigate it.

### Step 7 · The product line, changed

Go to `/lines` → **Sensor node**.

**Look for:** the subtitle now reads **Rev D**, the bill of materials shows `U1
NCP1117ST33T3G` with onsemi beside it, and the power tree draws the new part making the 3.3 V
rail.

**Would be a bug:** the applied part with no manufacturer or no footprint. Resolving a part by
MPN alone is ambiguous — three manufacturers list AMS1117-3.3 — and this is the screen where
that failure shows.

### Step 8 · The board

Back on `/notices`, inside the **Sensor node** change request, find **THE BOARD** and press
**PLACE NCP1117ST33T3G ON THIS BOARD**. About forty seconds.

**Look for:** *No connections break at U3, SOT-223 → SOT-223*, two crops of the same twelve
millimetres of board before and after, and the datasheet line the pin functions were read
from. The two pictures are all but identical, which is the correct answer for a true drop-in:
the pads it lands on are the pads that are already there.

The other half of that argument is in the tests, because no SOT-23-5 part is a sourced
candidate yet: placing an `ME6211C33M5G-N` at the same position takes unconnected items from
1 to 4 and adds four shorting items and three clearance violations. See
`backend/tests/test_boards.py::test_a_smaller_package_breaks_connections_on_this_board`.

**Would be a bug:** a picture not centred on U3, or a board consequence for a part with no
pinout on file. Ask for `LD1117S33TR` and it refuses by name, because ST publishes its pin
connections as a figure and a figure is not extractable text.

### Step 9 · Memory, which is the company's record

`/memory`.

Search `AMS1117`. The retired part sorts first, marked **NRND** because its last order date
has not passed yet, carrying the notice's own words and the boards it is still on.

Search `NCP1117`. **WHAT WAS DECIDED** reads as a history, and every line of it comes from a
different table:

- **RECOMMENDED** for AMS1117-3.3, quoting the notice.
- **WORKED** on the Sensor node.
- **APPROVED** on the Sensor node, with the margin and who signed.
- **WAITING ON A DESK** for the Cabinet controller, if you have not answered that one.

**Look for:** the verified datasheet readings underneath, each with the line it was read from
in quotation marks, and the ones with no line saying so plainly instead of pretending to a
citation.

**Would be a bug:** another company's parts here, or one approval listed twice.

---

## 3a · The other things worth showing, if there is time

### The matrix, which is the working

`/matrix` → select the three affected lines → position `u1` → candidates:

```
AMS1117-3.3, NCP1117ST33T3G, LD1117S33TR, TLV1117LV33DCYR
```

**CHECK EVERY LINE.** The change request is the deliverable; this is the grid it came from.
Every cell carries the five coverage labels, and clicking one opens the evidence.

**Look for:** the same part green on one line and red on another, and a margin printed on a
cell that only just holds.

### What the reader refuses to invent

`/notices` → **RECEIVE A NOTICE** → `docs/world-finals/notices/PCN-2026-118.pdf`.

The preliminary notice withholds the two fields a reader is most tempted to fill: no last
order date, and the recommendation is the word *none*.

**Would be a bug:** the notice's own issue date of 2026-09-01 appearing as the last order
date, or a part called `none` being proposed. Both passed every check this system had before
item 17.

### The design flow, which is the Singapore story

`/lines` → **NEW PRODUCT LINE** → a brief:

```
temp and humidity sensor, wifi and ble, usb-c powered with li-ion backup, small oled
```

Fifty to a hundred and thirty seconds. Inside Northwind the AML is live, so the run stops on
the first part that is not on it, and the question carries the roles that may answer it.

**A brand-new signup gets its own company with no lists kept**, and there the design flow
plays as it did in Singapore with no qualification gate at all. `None` for a list that is not
kept and an empty list that approves nothing are different things, and this is where the
difference shows.

---

## 3b · Resetting between run-throughs

Approving changes the world, so a second run-through needs it back.

```bash
cd backend
PYTHONPATH=. ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo --reset
```

Then delete the notice from the mailbox, or the poller will not re-read it: its read position
lives in `mail_cursor`, which the reset clears, so a message still sitting in the inbox is
read again on the next poll. That is usually what you want. It is also why the demo database
can end up with two `AMS1117-3.3` notices, one mailed and one uploaded, each recording how it
arrived.

**`--reset` used to fail on any world that had been used.** It was fixed on 8 September, and
the cause is in [DEFERRED.md](DEFERRED.md) under the seed. If it ever fails again with a
foreign key error on `decisions`, that is the same bug and the fix is in `tools/seed_world.py`.

---

## 4 · Every route

| Route | What it is |
|---|---|
| `/` | landing |
| `/signup`, `/login` | email and password, no verification, no reset |
| `/lines` | every product line this company ships |
| `/lines/:id` | one product: revision, power tree, bill of materials, board, what is coming |
| `/design/:lineId` | brief entry, then the workspace |
| `/design` | single-user local mode, no account |
| `/notices` | notices received, the review, the decisions, the change requests, the board |
| `/matrix` | every candidate against every product line |
| `/memory` | the company's record: parts, boards, notices, and what was decided |

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
../.venv/bin/python -m pytest                                    # 905 passed, 195 skipped, ~9s

# with a database
CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1082 passed, 18 skipped, ~25s

# with a database and KiCad
CONTINUITY_KICAD=docker CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1092 passed, 8 skipped, ~76s

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
| Every call fails, console shows CORS | Vite is not on 5173 or 5174. Restart with `--strictPort` |
| `401` on `/auth/me` before signing in | Normal. Two of these on the landing page are expected |
| The board section says no KiCad is configured | `CONTINUITY_KICAD=docker` was not set on the API, or Docker is not running |
| `no matching manifest for linux/arm64` | The `--platform linux/amd64` flag is missing |
| A notice upload fails with nothing readable | No model key, or no network. The parse is the one step with no offline path |
| The run finishes fast with no real MPNs | `CONTINUITY_LLM_API_KEY` did not load |
| Accounts vanish on restart | The API was started without `DATABASE_URL` |
| Twelve collection errors from pytest | Anaconda's Python. Use `.venv/bin/python` |
| A forwarded notice never appears | It is in spam. `tools/check_mail.py` says so and names the filter |
| The mailbox is configured and nothing polls | More than one company and no `CONTINUITY_MAIL_ORG` |
| A mailed notice appears against no product lines | `CONTINUITY_MAIL_ORG` holds an organisation id from before a reseed. Use the address form |
| `--reset` fails on `decisions_line_id_fkey` | Fixed 8 Sep. An old `tools/seed_world.py` |

---

## 9 · What is deliberately not here

[DEFERRED.md](DEFERRED.md) carries everything found and not fixed, with a severity against
each. The ones you will notice during a run-through, and what to say if a judge notices them
first:

- **Every column ends at engineering.** TLV1117 is on the AML and clears the Gateway, so the
  *"this is not your decision"* beat does not fire in the seeded world. The routing exists and
  is enforced at the HTTP boundary; the seeded world just does not reach it. 🟡
- **An engineer can qualify a part alone.** `roles.py` addresses `part_qualification` to
  engineering *and* quality with the words "it needs both", and the code reads that list as
  "any one of these may answer". Faithful would be two signatures, which the `decisions` row
  cannot express: it has one state and one `decided_by`. 🟡
- **The annual volume has no input any more**, so every change request is missing the
  recurring half of its cost and says *"no annual volume stated"*. It belongs on the product
  line beside the ambient rather than being typed per review. 🟡
- **A deployed instance has no KiCad**, so the board section is unavailable anywhere but a
  machine with the container.
- **The board consequence is not stored**, so it is not part of the change request document
  and has to be asked for again on a later visit.
- **The AML and AVL have no screen.** The lists are read correctly by the gates and written
  only by the seed and the store. Memory shows what was decided against them, which is the
  part a person asks about.

Two things listed here before 8 September are now done and are in the run-through above:
approvals are shown, on `/memory` under **WHAT WAS DECIDED**, and a successful precedent is
written the moment a substitution is approved rather than only proposed.
