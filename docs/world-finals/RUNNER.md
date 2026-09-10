# RUNNER.md

The run-through, and nothing else. What to do, and what should be on the screen when you have
done it.

Walk it before every rehearsal and before the day itself. **Anything that does not match a box
below is a bug.** Fix it there and then, or write it into [DEFERRED.md](DEFERRED.md) with a
severity and carry on to the next step.

Three documents, three jobs.

| | |
|---|---|
| **RUNNER.md** | this file. The flow, and what a correct screen looks like |
| **[DEMO-DAY.md](DEMO-DAY.md)** | what you say while each of these screens is up, and the answers to what a judge asks |
| **[OPERATING.md](OPERATING.md)** | the machine around it: what the start script checks, running the pieces by hand, every route and variable, what breaks and why |

---

## Start

```bash
./demo.sh
```

It checks, rebuilds the world, starts both servers, prints the URL, and holds the terminal so
ctrl-c stops both. **The world is rebuilt on every start**, so a run always begins with no
notice received and no decision pending. `--keep` goes back to a pass that is still in
progress. Anything that fails a check is explained in [OPERATING.md](OPERATING.md).

| Account | Password | Desk |
|---|---|---|
| `engineer@northwind.example` | `continuity-demo-2026` | engineering |
| `procurement@northwind.example` | `continuity-demo-2026` | procurement |
| `production@northwind.example` | `continuity-demo-2026` | production |
| `quality@northwind.example` | `continuity-demo-2026` | quality |

**Northwind Instruments**, four people, five products, both standing lists. One desk each, so
no one person can sign for two departments. Three of the five
carry the part the notice retires, at three different ambients on three different rails, which
is what makes one recommendation right for one product and wrong for another.

| Product line | Regulator | Rail | Ambient | Load |
|---|---|---|---|---|
| Sensor node | **AMS1117-3.3** | 5 V | 25 °C | 150 mA |
| Gateway | **AMS1117-3.3** | 5 V | 45 °C | 420 mA |
| Cabinet controller | **AMS1117-3.3** | 12 V | 55 °C | 60 mA |
| Bench supply | TLV1117LV33DCYR | — | — | — |
| Handheld meter | NCP1117ST33T3G | — | — | — |

---

## Step 1 · Sign in, and open a product line

**Do.** `http://localhost:5173` → **GET_STARTED** → sign in as the engineer → on `/lines`,
click **Gateway**.

- [ ] Five rows on `/lines`, one per product Northwind ships.
- [ ] The header reads **Gateway**, and under it `Rev C · 3 parts · 45 °C ambient · 3V3 at 420 mA · 5 V`.
- [ ] The chip beside it reads **`0 end of life · 22 checks`**, and **End of life (0)** is disabled.
- [ ] Three panes, left to right: **THE REVIEW**, **Component Logic Graph**, **Bill of Materials**.
- [ ] Every part on the power tree is green.
- [ ] The review pane reads *22 checks, nothing failed* under **THE ENGINE, ON THE PARTS FITTED TODAY**, and it is on screen the moment the page is.
- [ ] The bill has three rows and no red.
- [ ] **COMPONENTS / BOARD** sits in the graph pane's header. Press **BOARD**: the real `WS2812Controller`, drawn by KiCad, named in that pane's own title, in well under a second.
- [ ] Nothing on this page navigates to `/changes`.

---

## Step 2 · How the product line got here

**Do.** Back to `/lines`. On the **Gateway** row, the three-dot menu → **Design runs**.

- [ ] A finished workspace opens: the validation trace on the left, the board in the middle, the bill with prices on the right.
- [ ] It reads *Complete — 3/3 placed*.
- [ ] Every affected line has one. None of the five says it has no design runs.

---

## Step 3 · The boards are already there

**Do.** Nothing. Each affected product line ships with a real KiCad project, attached by the
seed.

| Product line | Project | Licence | Regulator at |
|---|---|---|---|
| Sensor node | [ProPico](https://github.com/diminDDL/ProPico) | MIT | **U3** |
| Gateway | [WS2812Controller](https://github.com/klein0r/pcb-ws2812-wifi-controller) | MIT | **U1** |
| Cabinet controller | [OpenJBOD-RP2040](https://github.com/OpenJBOD/rp2040) | CERN-OHL-P-2.0 | **U2** |

- [ ] Each of the three reports its own project, and no two report the same one.
- [ ] The regulator sits at a different reference designator on each.
- [ ] The **BOARD** toggle is there before any review has run.

---

## Step 4 · The notice arrives by email

**Do.** Open `/changes`, the rail's third icon, and leave it on screen. From your own mail,
forward `docs/world-finals/notices/PCN-2026-114.pdf` to the mailbox in `backend/.env`, **with a
subject line**.

- [ ] Within about fifteen seconds the server reads it, and within ten more the screen shows it without anybody pressing anything.
- [ ] `AMS1117-3.3`, `ADVANCED MONOLITHIC SYSTEMS`, **last order 2027-03-31**, recommends `NCP1117ST33T3G`.
- [ ] *read from: "Affected part: AMS1117-3.3 (SOT-223)"*, the line the part number came from.
- [ ] *Affects 3 product lines: Cabinet controller, Gateway, Sensor node.*
- [ ] Back on `/lines` → **Gateway**: U1 is red on the power tree and in the bill, and the chip reads `1 end of life`.

**If the mailbox cannot be reached**, press **UPLOAD ONE INSTEAD** and pick the same PDF.
Everything after this point is identical.

---

## Step 5 · Three lanes, one stream

**Do.** Press **START THE REVIEW**. Type nothing into **TRY A PARTICULAR PART TOO**.

- [ ] Discovery is said once, above the lanes, rather than three times.
- [ ] Three lanes advance together, one row per product, each showing the newest thing that board has said and its state. Replayed they finish in about a quarter of a second.
- [ ] The three answers are these three:

| Product line | Answer | Margin |
|---|---|---|
| Cabinet controller | **NCP1117ST33T3G** | 11 °C to spare |
| Gateway | **TLV1117LV33DCYR** | NCP1117 reaches **159 °C against a 150 °C limit** |
| Sensor node | **NCP1117ST33T3G** | 84 °C to spare |

- [ ] The verdicts stack vertically in one column and disagree.
- [ ] Expanding one lane opens its full trace in place and leaves the other two as they were.
- [ ] Every rejection carries the sentence that killed it, including `LD1117-3.3` arriving from the catalogue as *electrically fine here, and not on the approved manufacturer list*.
- [ ] The desk that owns each question is named **above** the buttons, and the question sits outside the fold.

---

## Step 6 · Approve, and watch the product change

**Do.** In the **Sensor node** lane, press **APPROVE AND APPLY**.

- [ ] *Applied · U1 is NCP1117ST33T3G · Rev D*.
- [ ] Under the lanes, the change requests appear, one per affected product line.

---

## Step 7 · The product line, changed

**Do.** `/lines` → **Sensor node**.

- [ ] The header now reads **Rev D**.
- [ ] The bill shows `U1 NCP1117ST33T3G` with **onsemi** beside it. A part with no manufacturer or no footprint is a bug.
- [ ] The power tree draws the new part making the 3.3 V rail, and every part is green.
- [ ] The bill's red row is gone and **End of life** reads **(0)**.
- [ ] The left pane holds the whole review that changed it, replayed, ending in the part it chose.

---

## Step 8 · The same review, on one product

**Do.** `/lines` → **Cabinet controller**, which has not been approved. Press **End of life (1)**
in the header, then **REVIEW THIS LINE** inside the drawer.

- [ ] The notice opens in the drawer on the right, where a design run puts its conflict, taking the bill's place.
- [ ] It carries the part, the manufacturer, the last order date, the recommendation, the reason the manufacturer gave, and **REVIEW THIS LINE**.
- [ ] **U1 turns cyan the instant you press it** and holds for the whole run. Red was the notice's statement, cyan is work in progress, green is a verdict.
- [ ] The trace fills the review pane. Narration is neutral and only a rule's verdict is coloured: a green tick for satisfied, a red cross for a failure, a dash for the three rules that decline to answer on any board.
- [ ] **Action Required** at the end, with *engineering decides* above the buttons: **NCP1117ST33T3G on the Cabinet controller. Clears every check on this board, with 11 °C to spare.**

**Then press BOARD** in the graph pane's header.

- [ ] The real OpenJBOD project, before and after, cropped to the same rectangle around the regulator.
- [ ] *"No connections break … SOT-223 → SOT-223."*
- [ ] The two pictures are all but identical, which is the correct answer for a true drop-in.
- [ ] The board names the part **U2** while the power tree beside it names **U1**. That is step 3 visible in one picture, not a fault.

---

## Step 9 · The document, one click from the product

**Do.** Still on a reviewed product line, look at the bottom of the review pane: **Change
request · NCP1117ST33T3G**. Press it.

- [ ] The document opens in the right-hand drawer: the proposal, every rejection with its sentence, evidence, the two coverage admissions, cost, and the desks required.
- [ ] Clicking a **notice** opens the notice, not the change request.

---

## Step 10 · Memory, which is the company's record

**Do.** `/memory`. Search `AMS1117`, then `NCP1117`.

- [ ] `AMS1117-3.3` sorts first, marked **NRND** because its last order date has not passed, carrying the notice's own words and the boards it is still on.
- [ ] **WHAT WAS DECIDED** for NCP1117 reads as a history: **RECOMMENDED** for AMS1117-3.3 quoting the notice, **WORKED** on the Sensor node, **APPROVED** on the Sensor node with the margin and who signed, and **WAITING ON A DESK** for the Cabinet controller if you have not answered it.
- [ ] The verified datasheet readings underneath each carry the line they were read from in quotation marks, and the ones with no line say so rather than inventing a citation.
- [ ] No other company's parts are here, and no approval is listed twice.

---

## If there is time

### The matrix, which is the working

`/matrix` → the three affected lines → position `u1` → candidates:

```
AMS1117-3.3, NCP1117ST33T3G, LD1117S33TR, TLV1117LV33DCYR
```

- [ ] **CHECK EVERY LINE** fills the grid, every cell carrying the five coverage labels.
- [ ] Clicking a cell opens the evidence.
- [ ] The same part is green on one line and red on another, and a cell that only just holds prints its margin.

### What the reader refuses to invent

`/changes` → **UPLOAD ONE INSTEAD** → `docs/world-finals/notices/PCN-2026-118.pdf`.

- [ ] No last order date, because the preliminary notice does not give one. The notice's own issue date of 2026-09-01 appearing there is a bug.
- [ ] The recommendation reads *none*, and no part called `none` is proposed.

### The design flow, which is the Singapore story

`/lines` → **NEW PRODUCT LINE** → a brief:

```
temp and humidity sensor, wifi and ble, usb-c powered with li-ion backup, small oled
```

- [ ] Fifty to a hundred and thirty seconds, and it stops on the first part not on the AML.
- [ ] The question carries the roles that may answer it.
- [ ] A brand-new signup gets its own company with no lists kept, and there the same flow runs with no qualification gate at all.

---

## Between passes

Approving changes the world. Stop `./demo.sh` and start it again: the rebuild is the reset, it
takes about three seconds, and it moves the mailbox read position past everything already in
the inbox so the next forwarded notice is read live. The by-hand version is in
[OPERATING.md](OPERATING.md).

---

## Known, so do not report these

Four things you will see on a pass that are already written down.

- **Every lane ends at engineering.** Known, and **not** in the same class as the other three: this is an open 🔴, because the assigned scenario is about three departments and the demo shows one. Do not spend a pass re-finding it.
- **A change request says *"no annual volume stated"***, because the volume has no input any more.
- **The Gateway's bill reads `TLV1117LV33DCYR · JSMSEMI`** after the substitution, which is the distributor's manufacturer rather than the datasheet's.
- **A replayed review says *"Trying LD1117-3.3."*** where the live one said where the candidate came from. The origin is not stored.

The rest of the list, with severities, is in [DEFERRED.md](DEFERRED.md).

---

## Reporting what you find

Add a row to [DEFERRED.md](DEFERRED.md) with a severity and the file it lives in.

🔴 would be wrong on stage · 🟡 wrong but survivable · ⚪ cosmetic or future · 🔵 researched and
deferred by decision

Its table header appears in all three sections of that file, so anything editing it
automatically must match on a unique line rather than on the header.
