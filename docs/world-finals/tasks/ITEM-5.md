# Task · BUILD item 5 — θJA bound to the right column, from the right document

**Repository** `~/Documents/GitHub/continuity`, work in `backend/`.
**Baseline** 754 passed, 5 skipped. **Do not commit or push.**

---

## The problem, in one table

ST's LD1117 datasheet, DocID2572 Rev 38, Table 2:

```
Symbol  Parameter                            SOT-223  SO-8  DPAK  TO-220  Unit
RthJC   Thermal resistance junction-case         15     20     8       5   °C/W
RthJA   Thermal resistance junction-ambient     110     55   100      50   °C/W
```

Every validation `datasheet.py` performs today passes for **all four** of those numbers. The
quote appears verbatim in the document (`_fact_from_reply`), the row names junction-to-ambient
and not junction-to-case (`_is_theta_ja_line`), and every value sits inside the 5–500 range. So
the extractor can return 50 — TO-220's figure — for a SOT-223 part, and nothing catches it.

`ThermalFact.package_column` looks like it guards this and does not: it stores the package that
was *asked about*, passed straight through from the caller.

This is not hypothetical. Reading that table by eye is how LD1117 briefly appeared to have no
published SOT-223 figure at all, and reading it carelessly the other way attaches a TO-220
number to a SOT-223 part — which understates temperature rise, the direction that passes a
board that cooks. See [PARTS.md](../PARTS.md).

## The approach

**Do not parse the table header in Python.** A toy header parser handles ST's
`Symbol Parameter SOT-223 SO-8 DPAK TO-220 Unit` and then fails on TI's
`THERMAL METRIC | TLV1117LV DCY (SOT-223) 4 PINS | UNIT`, and the failure is silent.

The model is good at reading a table and bad at arithmetic. We are the reverse. So the model
returns its reading as a **checkable claim**, and code verifies that claim against the document.

### What the model returns

Extend `SYSTEM` and the reply schema to require, alongside the existing `theta_ja` and
`source_line`:

| Key | Meaning |
|---|---|
| `columns` | The value columns of the table it read, left to right, verbatim as printed |
| `column_index` | Which of those columns it took the value from, zero-based |
| `mounting` | The condition the figure was measured under, verbatim, or null |
| `revision` | The document revision as printed, e.g. `"DocID2572 Rev 38"`, or null |

For a single-column thermal table, `columns` has one entry and `column_index` is 0. That is not
a special case, it is the same rule.

### What the code verifies

In `_fact_from_reply`, after the checks that already exist. **Every one of these failing means
return `None`** — declining is always correct, and a wrong θJA is worse than no θJA.

1. `columns` is a non-empty list of strings and `column_index` indexes into it.
2. The count of numeric values on `source_line` equals `len(columns)`. On Rev 26, whose `RthJA`
   row carries one number against four columns, this fails and the extraction correctly declines.
3. The value at `column_index` among those numbers equals the returned `theta_ja`. This is the
   arithmetic check the model cannot be trusted to do for itself.
4. `columns[column_index]` names the part's package. Match loosely — TI prints
   `DCY (SOT-223) 4 PINS` for what the distributor calls `SOT-223` — but it must match
   *something*: normalise both through `engine.packages` the way that module already folds
   spellings, and require a shared token.
5. Every entry of `columns` appears in the document text, so a fabricated header set is caught.

`ThermalFact` gains `mounting` and `revision` and stores the **verified** column rather than the
requested package.

### Where it lands

`normalize.py` already routes a `ThermalFact` onto `PartSpec.theta_ja` and
`theta_ja_source_line`. Route `mounting` onto `PartSpec.theta_ja_mounting`, which exists and is
currently only ever set by hand in the demo fixture. The thermal verdict already renders it.

## The cache is keyed by the wrong thing

`_cache_path(mpn)` — so a *different document* for the same MPN returns the first one's answer.
Uploading a corrected datasheet during a demo would silently return the stale figure, and the
Rev 26 / Rev 38 pair is exactly two documents for one MPN.

**Key the cache by document identity**: a hash of the PDF bytes, or of the extracted text when
the bytes are not to hand. Keep the MPN in the stored record for debugging, but not in the key.
`theta_ja_from_text` takes text rather than bytes, so hash what it has.

Check every caller — `normalize._fetch_theta_ja`, `graph/sourcing.choose`, and the
`/datasheet` endpoint in `api/app.py` — and make sure none of them still assumes MPN keying.

## The package table must stop answering substitution questions

`rules.py:834`:

```python
theta = regulator.theta_ja or packages.theta_ja(regulator.package)
```

That fallback is right for design mode, where a brief has to be answered even when nobody
published a figure, and the verdict already cites the table rather than a datasheet so the
substitution is disclosed. It is wrong when the question is *"is this substitute safe on this
board"*, because a generic per-package number is not evidence about a specific part.

The engine cannot tell those two questions apart today. **Do not invent a mode flag for it** —
that decision belongs with the fan-out in item 12, which does not exist yet. What this task
does is make the distinction *available*: `_check_rail_thermal` already knows whether the θJA
came from the part or the table, and the verdict's status should reflect it. A thermal result
computed on a package-table figure is not `satisfied` — it is `evidence_missing`, with a detail
naming what would settle it.

Check what that does to the existing suite before assuming it is free. If it moves a test that
is asserting design-mode behaviour, report it rather than updating the expectation — this is a
real behaviour change and it needs a decision, not a green tick.

---

## Tests

1. **The Rev 38 row binds to SOT-223.** Feed the four-column table and assert 110, not 50.
2. **The same row binds to TO-220 when that is the package.** Assert 50. Same document, same
   row, different answer — this is the check that proves binding rather than luck.
3. **Rev 26 declines.** One value against four columns; the result is `None`, not a guess.
4. **A single-column table still works.** TI's `DCY (SOT-223)` yields 62.9.
5. **A value that is not at `column_index` is rejected**, even when everything else is
   consistent — the model claiming 55 while pointing at column 0 must fail.
6. **A fabricated column header is rejected.**
7. **Mounting and revision reach `PartSpec`** and appear on the thermal verdict's evidence.
8. **Two different documents for one MPN return two different values** — the cache-key test,
   and the live-demo hazard it exists to prevent.

## Environment

**Use the project virtualenv**, `/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`.
The anaconda Python on the PATH has no `langgraph` and produces 12 collection errors unrelated
to your work.

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

Do not pass `-q`; it swallows the summary line here. **If PostgreSQL is unreachable in your
sandbox, say so plainly** rather than reporting a partial count as the whole suite. That has
happened on four previous tasks.

`timeout` does not exist on this machine.

## Do not

- **Do not add a PDF dependency.** `pypdf` is what the project has. Word coordinates would
  solve column binding directly and are not worth a 20 MB binary in a Render build; the
  claim-and-verify approach above is why.
- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not commit, push, or branch.** Do not edit anything under `docs/`.
- **Do not make the extractor guess.** Every ambiguity returns `None`. There is no partial
  credit for a θJA.
- **Do not change `engine/packages.py`'s values.** Use its spelling-folding helpers only.

## Report

1. Exact pytest counts before and after. Say explicitly if the full suite could not run.
2. Every file changed and what changed in it.
3. Any existing test whose expectation moved, and why — particularly anything caused by the
   package-table change.
4. Anything in this brief that did not reconcile with the code.
