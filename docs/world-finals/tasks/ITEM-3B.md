# Task · BUILD item 3b — the labels on the wire and on the screen

**Repository** `~/Documents/GitHub/continuity`. Backend in `backend/`, frontend in `frontend/`.
**Baseline** 748 passed, 5 skipped. **Do not commit or push.**

Item 3a replaced the engine's three check statuses with five and added a `margin` attribute.
The wire still passes whatever the engine produces, so the new labels are *already* reaching
the browser, and `frontend/src/app/lib/types.ts` still declares `'pass' | 'warn' | 'fail'`.
This task closes that gap and makes the screen say something honest with it.

| Label | Meaning |
|---|---|
| `satisfied` | Checked, and it holds. May carry a `margin`. |
| `failed` | Checked, and it does not hold |
| `not_applicable` | No subject for this check on this board |
| `not_assessed` | We do not perform this check at all |
| `evidence_missing` | We would check it, but an input is absent |

---

## 1 · `backend/continuity/api/events.py`

`check()` already forwards `verdict.status`. Add `margin`:

```python
margin=verdict.margin,
```

It is `None` on every label except `satisfied`, and it is the reason the item exists — a check
that holds by 1 °C and one that holds by 80 are both green, and only the margin separates them.

## 2 · Legacy runs — **do not skip this**

`run_events` stores raw stream frames as JSON. Every project already in the deployed database
carries `"status": "pass" | "warn" | "fail"` frozen in its rows, including the walkthrough that
every new account replays and the project behind the submitted demo link. Replay those
unmapped and the browser meets statuses its types do not contain.

Map them where stored events are replayed — `_replay` in `backend/continuity/api/app.py:627`,
which already rewrites frames on the way out, so this belongs beside what is there:

| Stored | Replayed as |
|---|---|
| `pass` | `satisfied` |
| `fail` | `failed` |
| `warn` | `evidence_missing` |

**`warn` maps to `evidence_missing`, and that is a deliberate loss.** An old `warn` might have
been a narrow pass or an unmeasurable constraint, and nothing in the stored row says which.
Mapping it to `satisfied` would silently promote historical checks to a standard they were
never held to. The conservative reading is the honest one. Put that reasoning in a comment —
it is the kind of decision someone will otherwise "fix" later.

Legacy frames have no `margin`; leave it absent rather than inventing one.

## 3 · `frontend/src/app/lib/types.ts`

```ts
export type EventStatus =
  | 'satisfied' | 'failed' | 'not_applicable' | 'not_assessed' | 'evidence_missing'
```

`Verdict.status` takes the same union, and both `Verdict` and the check event gain
`margin?: string | null`.

**Do not touch `SlotStatus` or `EdgeStatus`.** They also contain the string `'pass'` and they
are a different vocabulary about a different thing — a slot is `pending | searching | pass |
conflict`. `ComponentNode.tsx` reads slot status, not check status; leave it alone.

## 4 · `frontend/src/app/design/ChatPanel.tsx` — the caption that currently lies

`captionFor()` at line 54 does this:

```ts
const passed = results.filter((check) => check.status === 'pass').length
return `${passed}/${results.length} checks passed.`
```

That denominator is the exact number the project stopped quoting. It counts checks that had no
subject on the board and checks that could not run as though they were checks that ran and
passed. With five labels there is no longer any excuse for it.

Replace it with a tally that separates the kinds, in that order of interest, omitting any
count that is zero:

> `11 satisfied · 2 could not be checked · 3 not assessed`

Keep the existing behaviour that **a failure wins over the tally** — the function's own
docstring explains why, and it is right. When nothing has failed and the tightest satisfied
margin is worth seeing, name it: `11 satisfied, tightest margin 1 °C · 2 could not be checked`.

Use readable prose for the labels, not the raw enum. `not_applicable` should not reach a user
as `not_applicable`; it is either folded into the sentence or omitted — a check with no subject
on this board is usually not worth a user's attention, and the counts that matter are what was
satisfied, what could not be checked, and what we do not check at all.

## 5 · Wherever a check's detail is rendered

Where a satisfied check shows its detail, show its margin beside it. Do not build a new panel
for this — find the existing rendering and add to it. If there is no place a satisfied check's
detail is currently shown, say so in your report rather than inventing a screen; the matrix
that gives margin a proper home is a later build item.

---

## Tests

Backend, in the file that covers the API stream:

1. **A check frame carries `margin`** when the verdict has one, and `null`/absent when it does not.
2. **A replayed legacy frame is mapped** — a stored `"pass"` arrives as `satisfied`, a stored
   `"warn"` as `evidence_missing`, and a stored `"fail"` as `failed`.
3. **A replayed legacy frame carries no invented margin.**

Frontend, wherever `ChatPanel` or its helpers are covered — if there is no existing frontend
test setup, say so in your report rather than standing one up:

4. **The caption separates the kinds** and does not report a check that could not run as passed.
5. **A failure still wins over the tally.**

---

## Environment

Backend: **use the project virtualenv**,
`/Users/sparshjain/Documents/GitHub/continuity/.venv/bin/python`. The anaconda Python on the
PATH has no `langgraph` and produces 12 collection errors unrelated to your work.

    cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest

Do not pass `-q`; it swallows the summary line here. **If PostgreSQL is unreachable in your
sandbox, say so plainly rather than reporting a partial count as the whole suite.** That has
happened on both previous tasks and each time the full run found failures the partial did not.

Frontend: `bun` is the runtime here, not node. Typecheck with what `frontend/package.json`
already defines — do not add tooling.

`timeout` does not exist on this machine.

## Do not

- **Do not touch `backend/fixtures/*.json` or `backend/cache/`.** Recorded distributor
  responses, intentionally modified in git. Never `git checkout` or `git stash` them.
- **Do not commit, push, or branch.**
- **Do not edit anything under `docs/`.**
- **Do not change `engine/`.** The labels are settled; this task carries them, it does not
  revisit them.
- **Do not touch `SlotStatus` or `EdgeStatus`,** in either language.
- **Do not restyle or redesign anything.** Vocabulary and one caption. If a component needs
  more than a label change to compile, report it rather than reworking it.
- **Do not run a browser.** Verification in a browser is done separately, by hand.

## Report

1. Exact pytest counts before and after, and the frontend typecheck result. If either could
   not run, say so explicitly.
2. Every file changed and what changed in it.
3. Where a satisfied check's detail is rendered today, or that there is nowhere.
4. Anything in this brief that did not reconcile with the code.
