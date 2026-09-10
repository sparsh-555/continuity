# Task · BUILD item 38 — three product lines, three desks

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** item 32, which is what makes this possible at all.

Items 31 to 37 make every department sign every change. This one makes the three product lines
**stop in three different places**, so the run-through shows routing rather than a chorus.

**This item changes the seeded world**, so every number in it has to be a fact a real Northwind
would have, and one he is happy to say out loud on stage. Nothing here invents a failure.

## Where it stands today

All three lines reach a candidate that clears every rule, so the only thing separating them is
which part they land on. Two levers exist and both are real.

## 1 · Procurement, through volume

`availability` fails below `requirements.min_stock`, which defaults to 100
(`engine/models.py:468`), and the candidates have thousands at JLCPCB — which is why the Sensor
node's card shows availability green with a lifecycle note.

`TLV1117LV33DCYR` has **1,133 in stock**. A product line shipping at volume needs more than
that, and *"how many do you need to be able to buy"* is a property of the product, not of the
review.

- Put `min_stock` on the operating profile in `profile.py`, beside the ambient and the rails,
  where `annual_volume` should also eventually live.
- Give the Gateway a figure that reflects a product shipping in volume, and leave the other two
  at the default.
- The Gateway's answer is then TLV1117 **gated on availability**, addressed to procurement.

**Before writing the number, check it against the recorded stock** in `backend/fixtures/`. A
figure chosen to be just above whatever JLCPCB happened to hold on 10 September is a figure
that breaks when the fixtures are re-recorded. Pick a round production number that is true of
the product and let the stock fall where it falls.

## 2 · Quality, through the approved list

`LD1117-3.3` is already electrically fine on all three boards and off the approved manufacturer
list, and it loses only because a clear candidate exists. On a line where no clear candidate
does, it is proposed and gated on `part_qualification`, which is engineering **and** quality —
the two-signature case item 35 built.

Do not remove a part from the AML to force this. If the Gateway going to procurement leaves
another line's best answer as LD1117, take it; if not, leave this lever alone rather than
bending the world to produce it.

## 3 · What the run-through should then show

| Product line | Answer | Stops at |
|---|---|---|
| Sensor node | NCP1117ST33T3G, 84 °C to spare | all four sign, nothing gated |
| Gateway | TLV1117LV33DCYR | **procurement**, on stock |
| Cabinet controller | NCP1117ST33T3G, 11 °C to spare | all four sign |

One notice, three products, and the desks differ. Update RUNNER.md's step 5 table and
DEMO-DAY.md's step 5 to match **what the run actually produces**, verified by running it, not
by predicting it.

## 4 · Fixtures

Changing `min_stock` does not change which parts are searched, so the recordings still cover it.
If any candidate set changes, `./demo.sh --live` re-records, and the new files are committed
with the change. Check `git status backend/fixtures` before finishing.

## 5 · Tests

- The Gateway's review proposes TLV1117 gated on `availability` addressed to procurement.
- The other two lines propose with nothing gated.
- `tests/test_seed.py` asserts the three lines end at the three expected desks, so a later
  change to the world that flattens them fails the suite rather than the rehearsal.

## Done when

`./demo.sh` and one notice produce three answers that stop in three different places, and the
run-through documents say what the run says.
