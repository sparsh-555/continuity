# Notice Arrival Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `blueprint` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Announce mailed notices and refresh affected product views wherever an authenticated user is.

**Architecture:** A shell-level React context owns the existing notice-list polling cadence and detects new notice IDs after an initial silent baseline. It queues dismissible toasts and exposes an arrival revision. Existing `/lines` and `/lines/:id` loaders react to that revision and refetch their API-backed state.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite.

---

### Task 1: Shell-level arrival provider

**Files:**
- Create: `frontend/src/app/hooks/useNoticeArrivals.tsx`
- Modify: `frontend/src/app/shell/AppShell.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Write a failing provider test**

Create an isolated test that mocks `listNotices` with an empty initial response and then a
notice. Assert that the second poll exposes an incremented `arrival` revision and a toast
containing `AMS1117-3.3` and `3 product lines`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && bun test src/app/hooks/useNoticeArrivals.test.tsx`
Expected: FAIL because `NoticeArrivalProvider` does not exist.

- [ ] **Step 3: Implement the minimal provider**

Use `listNotices()` on mount and every 10 seconds. Keep the first successful IDs as baseline;
on later successful reads fetch `exposureTo(notice.mpn)`, enqueue one toast per unseen ID, and
increment the revision. Clear timers on unmount and reset state when the authenticated user
changes.

- [ ] **Step 4: Run the provider test**

Run: `cd frontend && bun test src/app/hooks/useNoticeArrivals.test.tsx`
Expected: PASS.

### Task 2: Subscribe existing product loaders

**Files:**
- Modify: `frontend/src/app/routes/changes.tsx`
- Modify: `frontend/src/app/routes/lines.tsx`
- Modify: `frontend/src/app/routes/line.tsx`

- [ ] **Step 1: Write failing route tests**

Render each route beneath the provider. Advance the mocked arrival revision and assert that
`listLines`, `getLineOverview`, and `checkLine` are invoked again; assert `/changes` has no
independent interval.

- [ ] **Step 2: Run the route tests to verify they fail**

Run: `cd frontend && bun test src/app/routes/notice-arrivals.test.tsx`
Expected: FAIL because routes do not consume the arrival revision.

- [ ] **Step 3: Implement minimal subscriptions**

Remove the `/changes` polling effect. Add the shared arrival revision to the existing load
effects in `/lines` and `/lines/:id`; reuse their existing loaders rather than client-side
patching notice state.

- [ ] **Step 4: Run route tests and build**

Run: `cd frontend && bun test src/app/routes/notice-arrivals.test.tsx && bun run build`
Expected: PASS and a successful production bundle.

### Task 3: Prove the complete user journey

**Files:**
- Modify: `docs/world-finals/DEFERRED.md`

- [ ] **Step 1: Start the seeded demo and open `/lines`**

Run: `./demo.sh`
Expected: seeded local demo starts.

- [ ] **Step 2: Deliver one notice after the provider baseline**

Use the documented mailbox route or `POST /notices` while `/lines` remains open.
Expected: toast names the notice and affected count; each affected row changes to the existing
notice status without browser navigation.

- [ ] **Step 3: Verify an open affected product line**

Open that line before delivery and repeat.
Expected: existing notice count, bill conflict state, and power-tree conflict state refresh.

- [ ] **Step 4: Record the outcome accurately**

Move the BUILD 28 row to the resolved section only if all prior steps passed. Otherwise append
the precise failed behavior to the live table; do not hide it or describe it as completed.
