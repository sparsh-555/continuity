# Line Workspace Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `blueprint` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/lines/:id` use the same responsive workspace constraints as `/design/:id`, while retaining product-line review, notice, board, and BOM behavior.

**Architecture:** Restore the shared `ComponentGraph` as a responsive `viewBox` diagram with no internal scroll container. Keep the existing product-line data flow, but use the design workspace's three-pane sizing and drawer replacement pattern. Share one selected reference-designator between the graph and BOM so the two representations remain synchronized.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vite, Playwright browser verification.

---

### Task 1: Restore responsive graph rendering

**Files:**
- Modify: `frontend/src/app/design/ComponentGraph.tsx`

- [ ] Remove the fixed SVG dimensions and scrolling wrapper introduced for the line page.
- [ ] Keep the graph's `viewBox` and `preserveAspectRatio="xMidYMid meet"`, and size the SVG to its pane (`width="100%"`, `height="100%"`).
- [ ] Preserve the existing graph header, legend, node status colours, and repair interactions.
- [ ] Verify at 1200px and 2560px that no graph scrollbar exists and all nodes remain visible.

### Task 2: Align the line workspace and synchronize BOM focus

**Files:**
- Modify: `frontend/src/app/routes/line.tsx`
- Modify: `frontend/src/app/design/ComponentGraph.tsx`
- Modify: `frontend/src/app/review/LineBom.tsx`

- [ ] Match the design workspace pane contract: fixed review pane, flexible graph/board pane, and fixed right drawer/BOM pane.
- [ ] Add optional selected-slot and selection callbacks to the graph and BOM.
- [ ] Set selected slot from either graph node or BOM row; retain EOL/conflict status styling while adding an unambiguous shared focused state.
- [ ] Keep board switching available before a review and keep notice/request drawers in the BOM position.

### Task 3: Verify the real demo journey

**Files:**
- Verify only: local seeded demo database and Playwright session

- [ ] Reseed the documented demo world.
- [ ] Confirm five product lines and restored design runs.
- [ ] Confirm normal and widescreen component graph sizing, EOL drawer, permanent board toggle, board rendering, and graph/BOM focus synchronization.
- [ ] Confirm `/changes` still starts the company-wide review and product-line change requests remain local to the relevant board.
