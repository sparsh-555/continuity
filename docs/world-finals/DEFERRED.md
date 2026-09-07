# Deferred — world finals

Every inconsistency, rough edge and shortcut found while building Continuity 2.0 that was
**not** resolved at the time. Nothing here is a surprise; everything here is a decision.

Same format and the same rules as [`docs/DEFERRED.md`](../DEFERRED.md), which covers the
preliminary build and is still live. This file is scoped to the finals work so the two do not
have to be read together. Items are removed when fixed.

**Severity:** 🔴 would be wrong on stage · 🟡 wrong but survivable · ⚪ cosmetic or future ·
🔵 researched and deferred by decision — the direction is settled, a prerequisite is not

| | Item | Where |
|---|---|---|
| 🔴 | Test data left in the production database — a `labels-check@example.com` account and six threads across three throwaway projects, all 7 Sep. `backend/.env` points `DATABASE_URL` at Neon, so local runs write to production. | Neon `neondb` |
| 🟡 | `not_assessed` and `not_applicable` are correct in the data and invisible on screen. Now that they are scoped to `board` rather than to the first slot, no view renders them — three declared coverage boundaries a user cannot see. | frontend · item 12 |
| 🟡 | `margin` has never been observed travelling end to end on a real run. The field serialises and a unit test covers it, but no live board has yet produced a satisfied-and-narrow check. The LD1117 1 °C cell is the demo beat that depends on it. | `api/events.py` · frontend |
| 🟡 | A local run cannot be isolated from production. There is no separate development database, so any browser verification writes real rows. | `backend/.env` |
| ⚪ | The θJA package table is knowingly optimistic for SOT-223 — 62 °C/W against a 66–136 spread TI measured. Left alone by decision: it is a fallback so a part with no published figure does not halt a run, no cell in the demo depends on it, and no single number is defensible when the board's copper is unstated. | `engine/packages.py` |
| ⚪ | Most rows of that table have never been checked against a datasheet. Seven have; the module docstring names which. | `engine/packages.py` |
| ⚪ | `QFN-32-EP(5x5)` and its siblings resolve to no θJA at all. The exposed-pad guard refuses to match `QFN32`, whose values already assume a thermal pad, so QFN regulators go thermally unchecked. | `engine/packages.py` |
| ⚪ | Codex cannot run the full test suite — its sandbox is denied the PostgreSQL socket. Every delegated task has reported a partial count, and twice the full run found failures the partial did not. Every agent result needs the suite run again by hand. | tooling |
| 🔵 | The operating profile is not persisted. Ambient, copper and rail load reach the engine but live only in a fixture; storing them against a product line is item 10, which is where product lines first exist. | `api/store.py` · item 10 |

## Resolved here, kept for the reasoning

| | Item | Where |
|---|---|---|
| ✅ | ~~`api/memory.py` recorded a repair as successful when the check still failed~~ — the guard compared against `"fail"`, a spelling the five labels retired, so it matched nothing. Now confirms only on `satisfied`, 7 Sep | `api/memory.py` |
| ✅ | ~~Board-wide verdicts blamed on whichever part was placed first~~ — `BOARD_SUBJECT`, 7 Sep | `engine/rules.py` |
| ✅ | ~~A package-table entry stopped the engine fetching a published θJA~~ — the gate treated "we have an approximation" as "this is answered", 7 Sep | `graph/sourcing.py` |
| ✅ | ~~The ambient was a silent default of 25 °C~~ — `ambient_source`, 7 Sep | `engine/models.py` |
