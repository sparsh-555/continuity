# Brief · working DEFERRED.md

Written to be handed to a coding agent whole. Self-contained: everything it needs to know
that is not in the repository is here, and everything that is in the repository is pointed
at rather than copied.

---

## The paste

> You are working on **Continuity**, at `~/Documents/GitHub/continuity`. Your job is to work
> through `docs/world-finals/DEFERRED.md`, most damaging first, and close items properly.
>
> **Read these before touching anything**, in this order:
>
> - `docs/world-finals/FLOW.md` — what the product is and where every stage lives.
> - `docs/world-finals/BUILD.md` — the two governing rules at the top, then the work items.
>   **Items 1 to 39 are all built**, item 28 last, on 10 September.
> - `docs/world-finals/DEFERRED.md` — your work list.
> - `docs/world-finals/RESEARCH-3rd-Passthrough.md` — several DEFERRED rows point into it by
>   anchor and it has the code reading, the options and the published work for each.
> - `docs/world-finals/OPERATING.md` — how to run it, every route and variable, what breaks.
>
> `docs/DEFERRED.md`, `docs/STATUS.md`, `docs/PROPOSAL.md` and `RUN.md` are **Singapore-era**
> and each says so at the top. Never read them for the current state.
>
> ### The rules that govern this codebase
>
> 1. **Nothing ships behind a label we could have built.**
> 2. **Continuity's entire pitch is that it checks parts, so a surface saying it could not
>    check one destroys the claim in seconds.** A failure to check is a bug to fix, not a
>    state to render. Coverage honesty belongs in the change request where somebody is
>    deciding whether to sign, never on a page seen for five seconds. **Do not draw an
>    affordance that cannot be used**, and do not add explanatory prose to demo surfaces.
> 3. **A gap is work, not a talking point.** If you find yourself writing a sentence whose
>    job is to make an absence sound acceptable, stop and put the item in DEFERRED instead.
>
> ### How to work an item
>
> - **Verify before asserting.** Read the code and cite `file:line`. The row's own claim may
>   be stale; check it against the code before believing it.
> - **Write the test first and watch it fail.** Then fix it, then watch it pass, then
>   **revert the fix and confirm the test fails again**. A test that passes for the wrong
>   reason is worse than no test, and that has happened here twice.
> - **Measure before and after** anything about speed, and put both numbers in the row.
> - **Change the product, not around it.** If a capability belongs on an existing screen,
>   put it there. Building a second screen beside an existing one has cost this project two
>   whole phases.
> - **One commit per item**, `type: description` with no scope, ending with the attribution
>   lines the repo already uses (copy the format from `git log`).
> - When an item is done, **move its row** to *Resolved here, kept for the reasoning* as
>   `| ✅ | ~~original text~~ — what fixed it and the date | where |`, and update the counts
>   in the header. Check the counts by actually counting the rows.
>
> **The editing trap:** DEFERRED's table header `| | Item | Where |` appears in **all three**
> sections. Replacing against it without a count once wrote ten rows three times each. Match
> on a unique line, or count rows programmatically after every edit.
>
> ### Order
>
> Start with anything red, then work the 🟡s in the live table, then the 🟡s in the 8
> September section. **Check the red before working it**: the newest one is a credential
> rotation, which is a console and not a commit, so the first *code* item may be an amber. Several rows are **decisions rather than defects** — they say so — and
> those need Sparsh, not you: surface them and move on rather than picking for him.
>
> ### Environment
>
> - `.venv/bin/python`. Anaconda's has no langgraph.
> - `cd backend && CONTINUITY_TEST_DB=postgresql:///continuity_test ../.venv/bin/python -m pytest`
> - `cd frontend && bun run build` typechecks then bundles. Use `bun`, never `node`.
> - **`backend/.env` points `DATABASE_URL` at production Neon.** Always name the database on
>   the command line. `./demo.sh` does on every command it issues.
> - `./demo.sh` starts the whole app and **rebuilds the demo world every time**; `--keep`
>   keeps it. `--check` runs the preflight only. It writes pid files to `.demo/`, so do not
>   run a second copy of it against the same directory — `--stop` from either kills both.
> - `timeout` does not exist on macOS. Use `curl --max-time`.
> - Four accounts, one desk each, password `continuity-demo-2026`: `engineer@`,
>   `procurement@`, `production@`, `quality@`, all `northwind.example`.
>
> ### Do not
>
> - Do not `git checkout` or clean `backend/cache/**`, which is deliberately untracked.
> - Do not echo the model key or the mailbox password into a terminal. Scrollback outlives
>   the command.
> - Do not push. Commit locally and say what you committed.
> - Do not add a delay anywhere to make work look slower. Replay is disclosed, not disguised.
> - Do not reason about a venue, a booth or conference wifi. The final is an online demo and
>   its format is not settled; if an item seems to depend on that, say so and skip it.

---

## What the list looks like right now

**This section was written on 10 September and the list has moved twice since.** It is kept
because the *shape* of the advice below still holds — start at the top, work the amber rows,
leave the decisions to Sparsh — but **do not read its counts or its red as current**. Count
them from the file.

As of 11 September the live table holds **14 🟡, 24 ⚪ and 2 🔵**, plus 4 🟡 and 11 ⚪ from the
8 September pass, with 75 resolved rows kept for their reasoning. No red.

**The red that was here is closed.** A broad `grep` over `backend/.env` on 11 September put
the model key and the mailbox app password into a session transcript; both were rotated the
same evening. No database credential was exposed — `.env` held a local socket URL with no
password in it by then. The row is kept below with the correction, because the lesson is that
editing a file to remove a hazard is not the same act as rotating what already leaked.

**BUILD item 28, the red this brief was written for, is built.** A mailed notice now announces
itself through one provider above the router, and `/changes`, `/lines` and an open product
line all react to the same signal.

**The 🟡s worth doing first**, in my reading as of 10 September, and the agent should say if
it disagrees. Four of these five have since been closed — the lanes' traces, the board
evidencing itself, the memory graph and the matrix's breadcrumb all landed on 10 and 11
September — so read this as a worked example of how to rank a list rather than as a list:

| | Why it is near the top |
|---|---|
| The lanes drop every `candidate` and `check` frame | The data is already on the wire and the single-line pane already renders it. Frontend only, and it is the difference between three verdicts and three traces |
| No change request shows a board | The strongest artefact in the product sits behind a button nobody presses. The real fix is storing the consequence, which is its own row |
| A running review is lost on navigation | `api/replay.frames_from` already rebuilds a line's trace; the missing piece is the notice-level endpoint |
| A retired part is nearly indistinguishable in the memory graph | One file, four ordered changes, and the research is written |
| The before and after boards are indistinguishable | Both renders are already in the DOM; an overlay is a filter and a blend mode |

**Rows that are decisions, not defects** — do not pick these alone: `/changes` doing three
jobs, the three not-assessed rules, the substitution matrix's place in the demo, and anything
that changes the seeded world's numbers.

## What has just changed, so the agent is not surprised

Phase 8 landed on 10 September: four desks, every department signing what it examined, a queue
per desk at `/approvals`, a switcher holding four real sessions, and the Gateway stopping at
procurement on a stock shortfall. Ten DEFERRED rows closed with it. Anything in an older
document that says every lane ends at engineering is out of date; RUNNER, DEMO-DAY, OPERATING,
FLOW and BUILD were all updated the same day.
