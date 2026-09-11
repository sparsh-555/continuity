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
no one person can sign for two departments.

**Sign in as all four desks with one press.** The sign-in screen carries **SIGN IN ALL FOUR
DESKS · DEMO WORLD**: it authenticates the four seeded accounts into this browser and leaves
the **engineer** active, which is the desk step 1 opens with. Do it before the camera rolls —
demonstration practice is to pre-authenticate and never sign in live, and the four sessions
coexist in one browser by design.

**Switching does not sign you out.** The rail carries a four-letter button above the settings
cog showing which desk you are; press it to move between every session this browser holds.
Every page's header says the desk in words as well, because the documented failure of a
multi-persona demonstration is the audience losing track of whose view is on screen. Three of the five
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
- [ ] The legend in the graph's corner names only the states this board is actually in. A resting board offers **Fitted · unchecked**; a row for a state nothing on screen is wearing is a bug.
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
- [ ] The list row carries the notice's own number and the day it arrived: **`AMS-PCN-2026-114 · received`** and today's date. A row labelled with the part number alone is a bug — that is what made the full notice and the preliminary one indistinguishable.
- [ ] *Affects 3 product lines: Cabinet controller, Gateway, Sensor node.*
- [ ] Back on `/lines` → **Gateway**: U1 is red on the power tree and in the bill, and the chip reads `1 end of life`.

**If the mailbox cannot be reached**, press **UPLOAD ONE INSTEAD** and pick the same PDF.
Everything after this point is identical.

- [ ] Doing both leaves **one** notice, not two. The same change arriving twice is one change, and the list shows one row.
- [ ] The date is **today where you are**, not a UTC date. A reader east of Greenwich before 08:00 would see yesterday from a naive UTC slice.

**For the other notice**, `PCN-2026-118.pdf` is the preliminary one: same part, no last-order
date, no recommendation. Delivering it leaves **two** rows that are now told apart by their own
numbers, `AMS-PCN-2026-118` and `AMS-PCN-2026-114`. Worth doing if a judge asks what the list
looks like when a part is retired twice.

**Reading the notice replays**, as of 10 September, like every distributor call: 1903 ms live
and 7 ms from `backend/fixtures/`, the same reading either way. It is keyed on the text the
document extracts to, so a forwarded copy and an uploaded one hit the same recording. **A
document nobody has recorded is refused rather than read** — the screen says *no fixture for
notice_read*, which is correct rather than a bug. Both committed notices are recorded; to
demonstrate a third, run `./demo.sh --live` and forward it once.

---

## Step 5 · Three lanes, one stream

**Do.** Press **START THE REVIEW**. Type nothing into **TRY A PARTICULAR PART TOO**.

- [ ] Discovery is said once, above the lanes, rather than three times.
- [ ] **Leave the page and come back.** `/lines` and then `/changes` again: the three lanes, their traces and their questions are all still there, with nothing pressed and nothing re-run. An empty review where a run had been is a bug — that was the state until 11 September.
- [ ] Three lanes advance together, one row per product, each showing the newest thing that board has said and its state. **Replayed they fill in over about twenty seconds**, staggered rather than metronomic, with **SKIP TO THE END** offered throughout.
- [ ] The three answers are these three, and they stop in two different places:

| Product line | Answer | Where it stops |
|---|---|---|
| Cabinet controller | **NCP1117ST33T3G** | four signatures, 11 °C to spare |
| **Gateway** | **TLV1117LV33DCYR** | **procurement**, on 1,133 in stock against a 5,000 build |
| Sensor node | **NCP1117ST33T3G** | four signatures, 84 °C to spare |

- [ ] The verdicts stack vertically in one column and disagree.
- [ ] Expanding one lane opens its full trace in place and leaves the other two as they were, with the verdicts grouped under **DESIGN**, **PROCUREMENT**, **PRODUCTION** and **QUALITY**.
- [ ] Every rejection carries the sentence that killed it, including `LD1117-3.3` arriving from the catalogue as *electrically fine here, and not on the approved manufacturer list*.
- [ ] Each question names **every** desk that must sign, above the buttons, and reads *and* rather than *or*. The question sits outside the fold.
- [ ] The Gateway's lane says procurement is being asked to accept a stock shortfall. The other two failed nothing.
- [ ] **No lane leads with a rule the engine declined to attempt.** Until 11 September a collapsed lane summarised itself as *NOT ASSESSED · signal integrity*; `emc`, `output_capacitor_stability` and `signal_integrity` are real checks now and all three are satisfied here. A lane leading with an admission is a bug.

---

## Step 6 · Four desks sign, and only then does the product change

**Do.** In the **Sensor node** lane, press **SIGN FOR MY DESK** as the engineer. Then switch
desk from the rail — the four-letter button above the settings cog — and sign as each of the
other three. The first time you switch, sign in as that account; after that both sessions
stay live and switching is one click.

- [ ] After the first signature: *Signed by DESIGN. Waiting on PROCUREMENT and PRODUCTION and QUALITY.*
- [ ] **The bill still reads AMS1117-3.3** after one, two and three signatures. Check it on `/lines` → Sensor node if you want to be sure.
- [ ] The fourth signature applies it: *Applied · U1 is NCP1117ST33T3G · Rev D*.
- [ ] The same desk pressing again is refused, and the refusal names who it is waiting for.
- [ ] **Each lane ends with its change request** — one per affected product line, naming every department that must sign and what each of them found. It is the lane's last layer rather than a stack under all three, so the request for the board you have just read is the one directly below it.
- [ ] Each change request ends with what was checked before anybody was asked: parts, departments, product lines.

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
- [ ] The trace fills the review pane. Narration is chronological and neutral; the verdicts group under **DESIGN**, **PROCUREMENT**, **PRODUCTION** and **QUALITY**, each with its own count.
- [ ] Only a rule's verdict is coloured: a green tick for satisfied, a red cross for a failure.
- [ ] **Action Required** at the end, with *engineering decides* above the buttons: **NCP1117ST33T3G on the Cabinet controller. Clears every check on this board, with 11 °C to spare.**

**Then press BOARD** in the graph pane's header.

- [ ] While it works the pane says **Loading the board…**, never *Drawing*.
- [ ] The real OpenJBOD project, before and after, cropped to the same rectangle around the regulator.
- [ ] *"No connections break … SOT-223 → SOT-223."*
- [ ] A caption above the pair states the identities in full: **FOOTPRINT: SOT-223 → SOT-223 (DROP-IN) · FITTED PART: AMS1117-3.3 → NCP1117ST33T3G**.
- [ ] The **AFTER** crop carries a violet tint and a violet border, and the **BEFORE** one does not. Violet means *this is the changed one*, never *this one is safe*.
- [ ] Under the tint the two pictures are all but identical, which is the correct answer for a true drop-in.
- [ ] Toggling back to **COMPONENTS** and forward to **BOARD** shows the picture again immediately. A second **PLACING…** is a bug — the board was already placed — and so is a pair of empty crops with the caption still above them.
- [ ] The board names the part **U2** while the power tree beside it names **U1**. That is step 3 visible in one picture, not a fault.

---

## Step 9 · The document, one click from the product

**Do.** Still on a reviewed product line, look at the bottom of the review pane: **Change
request · NCP1117ST33T3G**. Press it.

- [ ] The document opens in the right-hand drawer: the proposal, every rejection with its sentence, **every department that examined the change with its own result**, evidence, anything that could not be checked, cost, the desks required, and what was checked before anybody was asked.
- [ ] **The recurring cost is a real figure**, because the line's own profile states an annual volume with a source. The Gateway reads **$2,344 a year**, under **+$0.1172 a unit at 20,000/yr**; the Sensor node $171.60 and the Cabinet controller $68.64. *No annual volume stated* would be a bug.
- [ ] **Nothing on this document says a rule could not be checked.** Until 11 September `signal_integrity` did, on all three requests, because the datasheet figures it stacks never reached the engine. A `COULD NOT CHECK` block here is now a bug rather than a known state.
- [ ] **THE BOARD says what it did to *this* board**: the pads carried by function with their real net names, what DRC found before and after, and **WHAT RAN** — five operations with the seconds each took, timed in the container.
- [ ] The request carries **WHAT THE MISSING ROUND TRIPS ARE WORTH**, naming both constants and their sources, and saying in the same sentence that it is an estimate.
- [ ] **The Gateway's request carries a DISPOSITION and the other two do not.** Only the Gateway states a build quantity, and only its answer is short of it; a disposition on a line that clears outright is a bug.
- [ ] Every request carries an **EFFECTIVITY** line.
- [ ] **The board is already on the card**, before and after, with its caption — and **no *PLACE … ON THIS BOARD* button beside it**. The run computed it and the document carries it, so a button offering to compute it again has nothing to do. The pictures take a few seconds to arrive after a run; a card with the button is right for a world with no KiCad and wrong for this one a minute later.
- [ ] Clicking a **notice** opens the notice, not the change request.

---

## Step 9a · What each desk owes

**Do.** The rail's **Waiting on you** entry, the one carrying a count. Switch desks and open
it again.

- [ ] It names the desk you hold, at the top.
- [ ] Every pending decision that desk may answer, across every product line, with what is being replaced and on which product.
- [ ] The Gateway's row says procurement is being asked to accept the stock shortfall, and names the rule.
- [ ] A decision this desk has already signed shows what it signed rather than buttons that would be refused.
- [ ] A desk with nothing waiting says so plainly.
- [ ] The count on the rail matches the number of rows you can act on.

---

## Step 9b · The shortfall procurement accepted, on the released design

**Do.** Sign the **Gateway** with all four desks, the way step 6 signed the Sensor node. Then
`/lines` → **Gateway**.

This is the only product line whose change needed somebody to accept a failure rather than
merely approve one, so it is the only place this state exists.

- [ ] The header reads **Rev D** and the bill reads `U1 TLV1117LV33DCYR` with **Texas Instruments** beside it. **JSMSEMI** there is a bug.
- [ ] U1 on the power tree is **amber and dashed**, not green and not red. The legend in the graph's corner has gained an **Accepted** row, and only this board shows one.
- [ ] The review pane leads with **U1 failed and accepted: availability**, and under it the rule's own arithmetic: *TLV1117LV33DCYR: 1,133 in stock at JLCPCB, below the 5,000 minimum.*
- [ ] A green *nothing failed* here would be a bug, and so would a red conflict. The shortfall is real, somebody signed for it, and the screen says both.
- [ ] The trace below is the review as it ran, with procurement's `availability` still marked failed. That is a record of the moment, not a contradiction: the signature came after it.

---

## Step 10 · Memory, which is the company's record

**Do.** `/memory`. Look at the graph before searching anything, then search `AMS1117`, then
`NCP1117`.

- [ ] **`AMS1117-3.3` reads as retired without being clicked**: a duller, browner fill than every other part, a heavier ring, and the word **NRND** under the part number. If it is the same orange as the rest, that is a bug.
- [ ] Its edges to the boards that still carry it are **warm and dashed**, and they are the most obvious lines on the picture. An edge that was replaced is dashed and grey; a healthy one is solid and grey. Three states, three edges.
- [ ] A **legend** sits in the bottom-left corner, four rows. A graph with no key is a bug.
- [ ] `AMS1117-3.3` sorts first, marked **NRND** because its last order date has not passed, carrying the notice's own words and the boards it is still on.
- [ ] **WHAT WAS DECIDED** for NCP1117 reads as a history: **RECOMMENDED** for AMS1117-3.3 quoting the notice, **WORKED** on the Sensor node, **APPROVED** on the Sensor node with the margin and who signed, and **WAITING ON A DESK** for the Cabinet controller if you have not answered it.
- [ ] The verified datasheet readings underneath each carry the line they were read from in quotation marks, and the ones with no line say so rather than inventing a citation.
- [ ] No other company's parts are here, and no approval is listed twice.

---

## If there is time

### The appendix, which is the working

Scroll a change request to **CONSIDERED AND REJECTED**, at the end of its lane.

- [ ] Every candidate the review tried is named, with the one sentence that killed it.
- [ ] Opening one shows its whole check set — satisfied, failed and not-applicable — and each line names the desk it belongs to.
- [ ] The failing line is the one the lane's own verdict quoted, so the appendix and the runway agree.
- [ ] Nothing reads *not found at the distributor*: these verdicts were computed by the run, on this board, and not looked up again.

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

Three things you will see on a pass that are already written down.

- **The Gateway's bill reads `TLV1117LV33DCYR · JSMSEMI`** after the substitution, which is the distributor's manufacturer rather than the datasheet's.
- **A replayed review says *"Trying LD1117-3.3."*** where the live one said where the candidate came from. The origin is not stored.

**And one that is still open and still red:** a mailed notice raises no notification, so `/changes` is the only screen that reacts to one on its own. BUILD item 28.

The rest of the list, with severities, is in [DEFERRED.md](DEFERRED.md).

---

## Reporting what you find

Add a row to [DEFERRED.md](DEFERRED.md) with a severity and the file it lives in.

🔴 would be wrong on stage · 🟡 wrong but survivable · ⚪ cosmetic or future · 🔵 researched and
deferred by decision

Its table header appears in all three sections of that file, so anything editing it
automatically must match on a unique line rather than on the header.
