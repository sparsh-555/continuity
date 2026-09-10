# Task · BUILD item 35 — a decision holds more than one signature

**Repository** `~/Documents/GitHub/continuity`. **Baseline** 1115 passed, 20 skipped.
**Depends on** item 34.

`answer_decision` (`api/review.py:671-774`) authorises with
`allowed.intersection(user.roles)` — **first-response semantics**, where the first valid
answer is decisive. `roles.py:20` addresses `part_qualification` to engineering *and* quality
with the words *"it needs both"*, and one signature settles it.

The published guidance is direct: first response *"reduces waiting, but the first valid
response becomes decisive. It is unsafe when two independent controls or separation of duties
are required."* All-must-approve *"keeps the request in review until every current reviewer
approves."*

**Parallel, not sequential.** Sequential review adds a stage of latency per desk, and the round
trips are the thing this product exists to remove. Every required desk may sign at any time.

## The table already exists

`approvals` carries `id, org_id, thread_id, user_id, user_email, roles[], rule, subject, mpn,
revision, rationale, created_at, decision_id, line_id`. **No migration.**

And `api/review.py:737` **already writes a row** on approval. What is missing is that it writes
it *after* settling the decision, and nothing ever reads them back.

## 1 · Invert the order — `continuity/api/review.py`

Today: check role → apply the change → settle approved → record the approval.

Required:

1. Resolve the desks this answer speaks for: `signing = set(user.roles) & set(decision["roles"])`.
   Empty is the existing 403 and its message is already good.
2. **Refuse a second signature from the same desk.** Read the approvals for this decision; if
   `signing` is already covered, 409 with the desk named and who signed it.
3. Record the approval, with `roles=sorted(signing)` rather than `sorted(user.roles)` — the row
   must say which desk it was given as, not which desks the person happens to hold.
4. Recompute: `outstanding = set(decision["roles"]) - signed_so_far`.
5. If outstanding is non-empty, **return without applying**:
   `{"state": "pending", "signed": [...], "outstanding": [...]}`.
6. If empty, apply the substitution, `settle_decision(state="approved")`, and write the
   precedent, exactly as today.

The 409 for *"that decision was already approved"* stays for a settled decision. The applying
half — `applied`, the revision bump, `record_precedents` — moves inside step 6 unchanged. Read
it carefully before moving it; the *"is no longer on this product line's bill"* 409 has to stay
attached to the apply and not fire on an intermediate signature.

**A decline settles immediately.** Any required desk declining stops the change; it does not
wait for the others. That matches the pattern literature and it matches how a change board
works. Record the declining desk in the rationale.

## 2 · The store — `continuity/api/store.py`

```python
async def approvals_for_decision(self, decision_id: str, org_id: str) -> list[dict]:
```

`approvals` has `decision_id` and an index on `line_id`; add
`approvals_decision_idx (decision_id)` in `schema.sql` in the additive style the file already
uses.

`settle_decision` is unchanged. `decisions.state` stays the record of the outcome; the
approvals are the record of who got there.

## 3 · The trace and the replay

`stream.line_done` carries `proposal`, `conditional` and `reason`. A replayed review of a
part-signed decision should show what it is waiting for, so `api/replay.frames_from` gains the
outstanding desks from the decision row. Keep the existing rule that a replay does not re-raise
the **question** — whether it is still answerable is the decision row's business — but *"waiting
on production"* is a fact about the decision and belongs in the trace.

## 4 · The screens

`review/ReviewLanes.tsx` and `review/useLineReview.ts` both call `answerDecision` and set
`settled` from `outcome.state`. Both now have a third outcome:

- `approved` — applied, as today.
- `declined` — as today.
- `pending` — **signed, and waiting.** Show which desks have signed and which have not, in
  words. Do not encode progress in colour or position alone.

The APPROVE AND APPLY button is wrong for a desk that is not the last to sign. Two labels:
**APPROVE** when others are outstanding, **APPROVE AND APPLY** when this signature completes it.
The server is the authority on which; take it from `outstanding` on the decision.

## 5 · Tests

- A decision addressed to two desks stays `pending` after the first signature; the bill is
  unchanged and the revision has not moved.
- The second desk applies it, and the bill and revision change exactly as they do today.
- The same desk signing twice is a 409.
- A person holding two required desks signs for both at once, and the row records both.
- Any required desk declining settles it declined without waiting.
- **Rewrite `test_a_decision_can_only_be_answered_once`**, which asserts the behaviour being
  replaced. Keep a test of that name meaning *a settled decision cannot be re-answered*.

## Done when

The Sensor node's substitution needs four signatures, the bill does not move until the fourth,
and `part_qualification` finally means what `roles.py` has claimed since 8 September. This
closes the 🟡 *"an engineer can qualify a part on their own"*.
