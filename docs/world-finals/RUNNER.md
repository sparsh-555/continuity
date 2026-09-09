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

It also records **a described design run against every line**, which is what step 2 opens.
Confirm one landed:

```bash
psql postgresql:///continuity_demo -t -c \
  "select l.name, t.status, count(r.*) from threads t
     join product_lines l on l.id = t.line_id
     left join run_events r on r.thread_id = t.id group by 1,2 order by 1"
```

Expect five rows, each `done` with 36 frames.

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

This is the beat in the order it is told. Ten steps, about twenty-five minutes at a walk.

The story it tells: a company describes what it ships, a change notice arrives **by email**,
Continuity finds every product carrying the retired part, re-checks all of them at once,
reaches a different answer for each, asks the desk that owns the failing rule, and on approval
changes the part in the bill of materials, on the power tree and on the board.

**Two surfaces, and knowing which is which is the whole navigation.** `/changes` is the
company view: what arrived, what it reaches, and every affected line running together.
`/lines/:id` is one product: its power tree, its bill, its board, and its own review. The same
endpoint runs both, narrowed by `line_id`, so they cannot come to disagree about what a review
is.

### Step 1 · Sign in, and what a product line is

`http://localhost:5173` → **GET_STARTED** → sign in as the engineer.

You land on `/lines`. Five rows, each a thing Northwind ships. Click **Gateway**.

`/lines/:id` is **the design workspace pointed at a product that already exists**: the same
three panes, the same proportions, the same components as `/design`. Left to right:

| Pane | What it is |
|---|---|
| **THE REVIEW** | what has been said about this board |
| **Component Logic Graph** | the power tree, with **COMPONENTS / BOARD** in its header |
| **Bill of Materials** | what the product is made of |

**Look for**, in this order:

- The header: `Rev C · 3 parts · 45 °C ambient · 3V3 at 420 mA · 5 V · WS2812Controller`.
- The chip beside it: **`1 end of life · 22 checks`**, and the **End of life (1)** button.
- **The power tree, every part green except U1.** Green because this product ships and the
  engine confirms it — the page runs a check against the line's own ambient, rail and load on
  every visit. U1 is red because a notice retires it, which is a manufacturer's statement
  rather than a verdict of ours.
- In the review pane, under **THE ENGINE, ON THE PARTS FITTED TODAY**: *22 checks, nothing
  failed*. That heading is load-bearing. Beside a red part it would otherwise read as a
  contradiction, and it is not one — the notice is about 2027, and no rule fails on the board
  as it ships today.
- **The bill lights the same part red**, with a warning glyph beside `AMS1117-3.3`. The graph
  and the bill are two views of one board and must never disagree about it.

**Would be a bug:** the words *"What are you building?"*; a grey part; content in a narrow
strip with an empty field around it; a part red on the graph and ordinary in the bill; or any
sentence on this page about what could not be checked. The last one is not a style note — a
product whose pitch is that it checks parts must never open by naming the ones it did not. See
BUILD.md's second governing rule.

**Also a bug:** anything on this page navigating to `/changes`. A whole run-through was once
spent looking for a review that was on another page.

### Step 2 · How a product line got here

Back to `/lines`. On the **Gateway** row, the three-dot menu → **Design runs**.

A finished workspace opens: the validation trace on the left, the board in the middle, the
bill with prices on the right, and *Complete — 3/3 placed*. **The seed records the run in
which each product line was described** — its parts, its rails, and every check
`rules.evaluate` produced on the board those two make. It is not a synthesis and does not
pretend to be: a product that ships did not arrive by somebody being asked what to build.

Say the way in while it is on screen: an engineer describes the product, or uploads a bill of
materials, and from then on Continuity knows what the company ships. **NEW PRODUCT LINE** on
`/lines` is that door; you do not have to walk through it here.

**Would be a bug:** *"NO DESIGN RUNS ON THIS PRODUCT LINE"* on a seeded line, or a brief screen
asking what you are building about a product with a revision and a KiCad project.

**Then say the line that frames everything after it:** *these are Northwind's five product
lines, and three of them carry the same regulator.*

### Step 3 · The boards are already there

Nothing to do. Each affected product line ships with a real KiCad project, attached by the
seed, because a company that ships five products has its CAD.

| Product line | Project | Licence | Regulator at |
|---|---|---|---|
| Sensor node | [ProPico](https://github.com/diminDDL/ProPico) | MIT | **U3** |
| Gateway | [WS2812Controller](https://github.com/klein0r/pcb-ws2812-wifi-controller) | MIT | **U1** |
| Cabinet controller | [OpenJBOD-RP2040](https://github.com/OpenJBOD/rp2040) | CERN-OHL-P-2.0 | **U2** |

Three different designs drawn by three people who have never heard of us, each carrying a real
AMS1117-3.3 in SOT-223, each at a **different reference designator**. That last part is worth
saying out loud if anyone asks how the substitution finds the part: it resolves the position
per board, because no two products put the same chip in the same place.

Press **BOARD** in the graph pane's header now if you want it early — the real PCB is drawn by
KiCad and the page warms it on arrival, so the toggle is a switch rather than a wait.

**Worth knowing:** OpenJBOD carries 687 copper zones and found two defects the day it arrived,
both fixed. See `backend/fixtures/kicad/README.md`.

**Would be a bug:** a product line reporting no board, two of them reporting the same one, or
the toggle missing before a review has run.

### Step 4 · The notice arrives by email

This is the trigger.

Open `/changes` — the rail's third icon, a circle of arrows — and leave it on screen. Then,
from your own mail, forward `docs/world-finals/notices/PCN-2026-114.pdf` to the mailbox in
`backend/.env`, **with a subject line**.

Within about fifteen seconds the server reads it, and within ten more the screen shows it
without anybody pressing anything.

**Say the cost while it flies.** Resolving an end-of-life part with one that is already
approved costs about $1,300. Redesigning the board costs upwards of $950,000. What separates
them is whether anyone can prove the cheaper option works, and industry averages forty weeks
over that proof.

**Look for:**

- `AMS1117-3.3`, `ADVANCED MONOLITHIC SYSTEMS`, **last order 2027-03-31**, recommends
  `NCP1117ST33T3G`.
- *read from: "Affected part: AMS1117-3.3 (SOT-223)"* — the line the part number came from, in
  the document's own words.
- *Affects 3 product lines: Cabinet controller, Gateway, Sensor node.*

**Would be a bug:** 2027-09-30 as the last order date. That is the last time **ship** date and
it is the mistake this document was built to catch. Also a bug: nothing appearing at all,
which almost always means the message went to spam. `../.venv/bin/python tools/check_mail.py`
says so in one line.

**The fallback, if the mailbox cannot be reached:** press **UPLOAD ONE INSTEAD** and pick the
same PDF. Everything after this point is identical, and nothing downstream knows or cares how
the notice arrived.

### Step 5 · Three lanes, one stream

Press **START THE REVIEW**.

Do not type anything into **TRY A PARTICULAR PART TOO**. The candidates are *found*, and
saying so is the point: the notice's own recommendation first, then the approved manufacturer
list in the same category, then the distributor's catalogue in the same package. That box is
an override for a part somebody wants tried anyway, and it is deliberately not the way in.

Discovery is said once, above the lanes, because the same part is retired on every board. Then
**three lanes advance together** — one row per product, each showing the newest thing that
board has said and its state. About a minute against live sourcing.

| Product line | Answer | Why the obvious one lost |
|---|---|---|
| Cabinet controller | **NCP1117ST33T3G** | clears everything with 11 °C to spare |
| Gateway | **TLV1117LV33DCYR** | NCP1117 reaches **159 °C against a 150 °C limit** |
| Sensor node | **NCP1117ST33T3G** | 84 °C to spare |

**Point at the right-hand column.** The three verdicts stack vertically and disagree, and that
disagreement is the whole argument: the manufacturer's own recommended replacement is right
for two of these products and would cook the third, and the third survives on a different part
for a reason that is about that board and no other.

Expand one lane. Its full trace opens in place and **the other two stay as they are** — every
rejection carrying the sentence that killed it, including `LD1117-3.3` surfacing from the
catalogue as *electrically fine here, and not on the approved manufacturer list*.

**Look for:** the desk named above each question before the buttons rather than after, and the
question sitting outside the fold — a decision waiting on somebody should never need a row
expanded to be found.

**Would be a bug:** three identical answers; three columns of streaming monospace side by
side; a rejection with no sentence; expanding one lane collapsing another; or the lanes sitting
on CHECKING with nothing above them for forty seconds.

**Known, and worth saying before a judge asks:** every lane currently ends at engineering,
because TLV1117 is on the AML and clears the Gateway. The *"this is not your decision"* beat
does not fire in the seeded world. It is logged 🟡 in [DEFERRED.md](DEFERRED.md).

### Step 6 · Approve, and watch the product change

In the **Sensor node** lane, press **APPROVE AND APPLY**.

**Look for:** *Applied · U1 is NCP1117ST33T3G · Rev D*.

Four things happened in that one press, and they are the difference between a recommendation
and a change:

- the part was written into the bill of materials,
- the revision moved from Rev C to Rev D,
- the approval was recorded with who signed it and why,
- and the **successful precedent** was written, so the next notice does not re-litigate it.

Under the lanes, the change requests appear — one per affected product line. That is the
document somebody signs: proposal, every rejection with its sentence, evidence, the two
coverage admissions, cost, and the desks required.

### Step 7 · The product line, changed

Go to `/lines` → **Sensor node**.

**Look for:** the header now reads **Rev D**, the bill shows `U1 NCP1117ST33T3G` with onsemi
beside it, the power tree draws the new part making the 3.3 V rail, **every part is green, the
bill's red row is gone, and the End of life button reads (0)**. The notice is joined to the
fitted bill, so applying the change takes it away rather than leaving a warning about a part
the board no longer carries.

**And the left pane now holds the whole review that changed it** — replayed from what the run
recorded, ending in the part it chose. Reopening a reviewed product line shows the working,
not just the answer.

**Would be a bug:** the applied part with no manufacturer or no footprint. Resolving a part by
MPN alone is ambiguous — three manufacturers list AMS1117-3.3 — and this is the screen where
that failure shows. Also a bug: the verdict chip reading **NO VIABLE PART** on a board that
shipped.

### Step 8 · The same review, on one product

Go to `/lines` → **Cabinet controller**, which has not been approved yet.

Press **End of life (1)** in the header. The notice opens in the drawer on the right, **where
a design run puts its conflict**, taking the bill's place. Inside it: the part, the
manufacturer, the last order date, the recommendation, the reason the manufacturer gave, and
**REVIEW THIS LINE**. Press that.

This is the same endpoint, the same engine and the same frames as step 5, narrowed to one
board. The difference is who it is for: step 5 is the company view, this is the view for one
product somebody wants to go deep on.

**Look for**, in order:

- **U1 turns cyan the instant you press it** and holds for the whole run. Red was the notice's
  statement, cyan is work in progress, green is a verdict — three colours, three different
  kinds of claim.
- The trace filling the review pane. **Narration is neutral and only a rule's verdict is
  coloured**: green ticks for satisfied, a red cross for a failure, a dash for the three rules
  that decline to answer on any board.
- **Action Required** at the end, with *engineering decides* above the buttons:
  **NCP1117ST33T3G on the Cabinet controller. Clears every check on this board, with 11 °C to
  spare.**

Then press **BOARD** in the graph pane's header. The real OpenJBOD project, before and after,
cropped to the same rectangle around the regulator, and *"No connections break … SOT-223 →
SOT-223."* The two pictures are all but identical, which is the correct answer for a true
drop-in: the pads it lands on are the pads that are already there.

The board names the part **U2** while the power tree beside it names **U1**, and that is not a
fault: the bill this company keeps and the project somebody else drew are two documents, and
the substitution finds the position in each on its own terms. It is step 3's point, visible in
one picture.

The other half of that argument is in the tests, because no SOT-23-5 part is a sourced
candidate yet: placing an `ME6211C33M5G-N` at the same position takes unconnected items from 1
to 4 and adds four shorting items and three clearance violations. See
`backend/tests/test_boards.py::test_a_smaller_package_breaks_connections_on_this_board`.

**Would be a bug:** the regulator staying red for the whole run; a green tick beside a sentence
about a part that failed; the review opening a different page; a board picture that is a stamp
in the middle of a black rectangle; or a board consequence for a part with no pinout on file.
Ask for `LD1117S33TR` and it refuses by name, because ST publishes its pin connections as a
figure and a figure is not extractable text.

**Known:** the run is quiet for a stretch between the candidate list and the first line about
this board, while the line's own parts resolve. It is logged in [DEFERRED.md](DEFERRED.md).

### Step 9 · The document, one click from the product

Still on a product line that has been reviewed, look at the bottom of the review pane:
**Change request · NCP1117ST33T3G**. Press it and the document opens in the right-hand drawer.

Two artefacts, deliberately kept apart. The **trace** is how this board reached its answer and
lives in the left pane, because that is what somebody on this product wants. The **change
request** is what somebody signs — cost, approvals, the board consequence, and the two coverage
admissions — and it is one line at the end rather than the answer to every click. `/changes`
lists the same document for every affected line, which is the company view of it.

**Would be a bug:** clicking a notice opening the change request instead of the notice.

### Step 10 · Memory, which is the company's record

`/memory`.

Search `AMS1117`. The retired part sorts first, marked **NRND** because its last order date has
not passed yet, carrying the notice's own words and the boards it is still on.

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

`/changes` → **UPLOAD ONE INSTEAD** → `docs/world-finals/notices/PCN-2026-118.pdf`.

The preliminary notice withholds the two fields a reader is most tempted to fill: no last order
date, and the recommendation is the word *none*.

**Would be a bug:** the notice's own issue date of 2026-09-01 appearing as the last order date,
or a part called `none` being proposed. Both passed every check this system had before item 17.

### The design flow, which is the Singapore story

`/lines` → **NEW PRODUCT LINE** → a brief:

```
temp and humidity sensor, wifi and ble, usb-c powered with li-ion backup, small oled
```

Fifty to a hundred and thirty seconds. Inside Northwind the AML is live, so the run stops on
the first part that is not on it, and the question carries the roles that may answer it.

**A brand-new signup gets its own company with no lists kept**, and there the design flow plays
as it did in Singapore with no qualification gate at all. `None` for a list that is not kept
and an empty list that approves nothing are different things, and this is where the difference
shows.

---

## 3b · Resetting between run-throughs

Approving changes the world, so a second run-through needs it back.

```bash
cd backend
PYTHONPATH=. ../.venv/bin/python tools/seed_world.py postgresql:///continuity_demo --reset
```

It reseeds five product lines, three boards, both standing lists, and **a described design run
against every line** — which is what step 2 opens. Expect it to print all five with their ids.

**Then deal with the mailbox, because the reset alone leaves the demo already spoiled.**

`mail_cursor` cascades off the organisation, so a reset wipes the read position. The message
from the last run-through is still in the inbox, the poller sees a mailbox it has never read,
and within fifteen seconds the notice is back. You sign in to a fresh world that has already
received its change notice, and step 4 has nothing left to show. **This was confirmed again on
9 September**: a reset was followed by a clean `notices` table, and the next page load showed
`1 end of life`.

Two ways to fix it, and the second is better:

```bash
# Either: throw away what was auto-read, and leave the cursor where it is.
psql postgresql:///continuity_demo -c "DELETE FROM notices"

# Or: delete the message from the mailbox first, then reseed. Nothing to re-read.
```

Either way, forward a **new** message for step 4. It gets the next UID and is read live, which
is the thing being demonstrated.

This is also why the demo database can end up with two `AMS1117-3.3` notices, one mailed and
one uploaded, each recording how it arrived. That is correct rather than a duplicate — but two
identical notices render as two rows in the drawer and two lanes' worth of confusion, so clear
them between passes.

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
| `/lines/:id` | one product, as a workspace: power tree or board, bill, its own review, and the notice against it |
| `/design/:lineId` | the run in which this line was described; a brief screen only if it has none |
| `/design` | single-user local mode, no account |
| `/changes` | notices received, the company-wide review in lanes, the change requests |
| `/matrix` | every candidate against every product line |
| `/memory` | the company's record: parts, boards, notices, and what was decided |

Two endpoints have no screen and are worth knowing about:

```bash
curl -s -b cookies.txt 'http://localhost:8000/exposure?mpn=AMS1117-3.3'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/bom'
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/reviews'      # a finished review, replayed
curl -s -b cookies.txt 'http://localhost:8000/lines/<id>/board/render' # the board, cached after the first
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
../.venv/bin/python -m pytest                                    # 920 passed, 213 skipped, ~9s

# with a database
CONTINUITY_TEST_DB=postgresql:///continuity_test \
  ../.venv/bin/python -m pytest                                  # 1113 passed, 20 skipped, ~30s

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
| Every call fails, console shows CORS | Vite is not on 5173 or 5174. Restart with `--strictPort` |
| `401` on `/auth/me` before signing in | Normal. Two of these on the landing page are expected |
| The BOARD view says no KiCad is configured | `CONTINUITY_KICAD=docker` was not set on the API, or Docker is not running |
| BOARD takes three seconds the first time | Expected. The render is cached on the bundle after that, and the page warms it on arrival. A server restart empties the cache |
| A reviewed line shows a verdict but no trace | The API predates `/lines/:id/reviews`. Restart it |
| Two identical notices in the drawer | A reseed re-read the mailed message. See §3b |
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

- **Every lane ends at engineering.** TLV1117 is on the AML and clears the Gateway, so the
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
  and is computed again on a later visit. The picture itself is cached per board for as long
  as the API is up, so it costs about three seconds once and nothing afterwards.
- **A replayed review cannot say where each candidate came from.** The live trace narrates
  *"Trying LD1117-3.3 — found in the distributor's catalogue"*; only the manufacturer and
  package are stored per attempt, so the replay says *"Trying LD1117-3.3."* One field would
  close it.
- **A review left waiting on a desk replays without its buttons.** Reopening the line shows
  its trace and its proposal; whether that decision is still answerable is the decision row's
  business, and the trace does not re-raise the question.
- **The AML and AVL have no screen.** The lists are read correctly by the gates and written
  only by the seed and the store. Memory shows what was decided against them, which is the
  part a person asks about.

Two things listed here before 8 September are now done and are in the run-through above:
approvals are shown, on `/memory` under **WHAT WAS DECIDED**, and a successful precedent is
written the moment a substitution is approved rather than only proposed.
