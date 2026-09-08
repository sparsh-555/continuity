-- Application tables. Applied idempotently at startup, beside `checkpointer.setup()`.
--
-- ## Why these exist alongside the LangGraph checkpointer
--
-- The checkpointer is a key-value store keyed by thread: `list(config)` and
-- `get_state_history(config)` both require a `thread_id`, and nothing in its API answers
-- "which threads belong to this user". Every question a dashboard asks is therefore one
-- it structurally cannot serve, so ownership, naming and listing live here instead.
--
-- Nothing in this file duplicates graph state. A row here records who owns a run, what
-- was asked, and the two things needed to resume it honestly — `last_seq` and the BOM.
--
-- ## Why no migration tool
--
-- `CREATE TABLE IF NOT EXISTS` is the same contract `checkpointer.setup()` offers, and
-- it is enough while the schema only grows. The moment a column has to change type or
-- back-fill, this stops being sufficient and a real migration belongs here.

-- Added 7 Sep 2026. A project was the original name for the container an enterprise
-- ships; product line is the name the product now uses everywhere. This runs before
-- `CREATE TABLE IF NOT EXISTS product_lines`: doing it afterwards would create an empty
-- new table on an old deployment and make the required table rename impossible. Each
-- guard makes startup safe after the migration has already run.
ALTER TABLE IF EXISTS projects RENAME TO product_lines;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'threads' AND column_name = 'project_id') THEN
        ALTER TABLE threads RENAME COLUMN project_id TO line_id;
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'findings' AND column_name = 'project_id') THEN
        ALTER TABLE findings RENAME COLUMN project_id TO line_id;
    END IF;
END $$;

-- Renaming a table leaves its primary key index under the old name, so a migrated
-- database and a fresh one would otherwise disagree about what that index is called.
-- Cosmetic to Postgres, and exactly the drift this rename exists to remove.
ALTER INDEX IF EXISTS projects_pkey RENAME TO product_lines_pkey;
ALTER INDEX IF EXISTS projects_user_idx RENAME TO product_lines_user_idx;
ALTER INDEX IF EXISTS threads_project_idx RENAME TO threads_line_idx;
ALTER INDEX IF EXISTS findings_user_project_idx RENAME TO findings_user_line_idx;

CREATE TABLE IF NOT EXISTS users (
    id            text PRIMARY KEY,
    email         text NOT NULL UNIQUE,   -- stored lowercased; the app folds before writing
    password_hash text NOT NULL,
    onboarded_at  timestamptz,            -- NULL means the walkthrough has never run
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- The cookie value is never stored, only its SHA-256. A dump of this table is then not a
-- set of live sessions.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash text PRIMARY KEY,
    user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS product_lines (
    id         text PRIMARY KEY,
    user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS product_lines_user_idx ON product_lines(user_id, updated_at DESC);

-- `id` is the LangGraph thread_id, so this row and the checkpoint share a key without a
-- join table. `user_id` is denormalised off `product_lines` on purpose: `/resume` and
-- `/export` authorise on it, and an ownership check should not depend on a join.
CREATE TABLE IF NOT EXISTS threads (
    id         text PRIMARY KEY,
    line_id    text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt     text NOT NULL,
    status     text NOT NULL DEFAULT 'running'
               CHECK (status IN ('running', 'awaiting', 'done', 'error', 'abandoned')),
    -- -1 means nothing has been sent. The client initialises its high-water mark to the
    -- same value, so that seq 0 survives. See `events.EventStream`.
    last_seq   integer NOT NULL DEFAULT -1,
    bom        jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS threads_line_idx ON threads(line_id, created_at DESC);
CREATE INDEX IF NOT EXISTS threads_user_idx ON threads(user_id);

-- Added 10 Aug. `CREATE TABLE IF NOT EXISTS` above does nothing to a table that already
-- exists, so growth arrives as its own idempotent statement.
--
-- Verbatim `done.summary` from the contract: slots, placed, conflicts_resolved,
-- elapsed_s. A record of what the engine reported, never a recomputation — which is why
-- it is one opaque column rather than four typed ones the dashboard could drift from.
ALTER TABLE threads ADD COLUMN IF NOT EXISTS summary jsonb;

-- `CREATE TABLE IF NOT EXISTS` leaves an existing CHECK constraint unchanged, so update
-- its fixed vocabulary separately for databases created before abandoned runs existed.
ALTER TABLE threads DROP CONSTRAINT IF EXISTS threads_status_check;
ALTER TABLE threads ADD CONSTRAINT threads_status_check
    CHECK (status IN ('running', 'awaiting', 'done', 'error', 'abandoned'));

-- Added 10 Aug. Lets `/design/demo` find the walkthrough it already created instead of
-- making a second one. The endpoint is reached twice in development — React re-runs
-- effects — and was not idempotent, so every new account got two "Welcome to Continuity"
-- product lines, one of them abandoned mid-stream.
ALTER TABLE product_lines ADD COLUMN IF NOT EXISTS is_walkthrough boolean NOT NULL DEFAULT false;

-- Added 7 Sep 2026. A product line carries the production BOM and the conditions its
-- boards operate under. `user_id` is denormalised deliberately: exposure matching is an
-- authorisation boundary, so ownership must be checked without depending on a join.
ALTER TABLE product_lines ADD COLUMN IF NOT EXISTS revision text;
ALTER TABLE product_lines ADD COLUMN IF NOT EXISTS profile jsonb;

CREATE TABLE IF NOT EXISTS line_parts (
    line_id      text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    user_id      text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refdes       text NOT NULL,
    mpn          text NOT NULL,
    manufacturer text,
    footprint    text,
    populated    boolean NOT NULL DEFAULT true,
    PRIMARY KEY (line_id, refdes)
);

CREATE INDEX IF NOT EXISTS line_parts_mpn_idx ON line_parts(user_id, mpn);

-- Findings are a user-facing record of what the engine reported. They are never input
-- to a rule, planner, or reviewer: a part can correctly fail on one board and pass on
-- another under different electrical conditions.
CREATE TABLE IF NOT EXISTS findings (
    id              text PRIMARY KEY,
    thread_id       text NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    line_id         text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    user_id         text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rule            text NOT NULL,
    slot            text NOT NULL,
    mpn             text NOT NULL,
    manufacturer    text,
    lifecycle       text,
    verdict         text NOT NULL,
    outcome         text NOT NULL CHECK (outcome IN ('repaired', 'accepted', 'unresolved')),
    action          text CHECK (action IS NULL OR action IN ('swap', 'change_topology', 'change_rail')),
    replacement_mpn text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS findings_user_mpn_idx ON findings(user_id, mpn);
CREATE INDEX IF NOT EXISTS findings_user_line_idx ON findings(user_id, line_id);

-- Added 12 Aug. A successful repair can guide a matching future conflict without ever
-- retaining a replacement part as a promptable precedent.
ALTER TABLE findings ADD COLUMN IF NOT EXISTS signature text;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS worked boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS findings_precedent_idx
    ON findings(user_id, signature) WHERE worked;

-- Facts here are intrinsic to an MPN across every board. Never store a verdict,
-- conflict, pass/fail, score, or any other result that depends on a board's conditions.
CREATE TABLE IF NOT EXISTS part_facts (
    mpn         text NOT NULL,
    field       text NOT NULL,
    value       text NOT NULL,
    source      text,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (mpn, field)
);

-- Added 12 Aug. The board checkpoint is the source of truth for state; this is the
-- compact, user-visible trace that explains how it got there. BOM frames stay on
-- `threads.bom`, where their larger payload is already stored once.
CREATE TABLE IF NOT EXISTS run_events (
    thread_id text NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    seq       integer NOT NULL,
    event     jsonb NOT NULL,
    PRIMARY KEY (thread_id, seq)
);

-- Added 7 Sep 2026. A product line is a thing a *company* ships, and an end-of-life notice
-- reaches three departments looking at one run. Ownership was fifteen `WHERE user_id = %s`
-- clauses, each saying "you may see what you personally created" — correct for a person
-- designing a board alone, and the reason the second reviewer of a change gets a 404.
--
-- `user_id` stays on every table. It stops being the authorisation boundary and becomes
-- what it honestly always was: who created this. A change request that cannot say who
-- raised it is worse than one nobody can share.
CREATE TABLE IF NOT EXISTS organisations (
    id         text PRIMARY KEY,
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id text REFERENCES organisations(id);

-- A set, not a single value. People wear more than one hat, and the demo needs one account
-- that can walk every gate while single-role accounts prove the refusal. The default keeps
-- every existing account working unchanged: today's only interruption is an engineering
-- trade-off — accept the temperature, relax the requirement.
ALTER TABLE users ADD COLUMN IF NOT EXISTS roles text[] NOT NULL DEFAULT '{engineering}';

ALTER TABLE product_lines ADD COLUMN IF NOT EXISTS org_id text REFERENCES organisations(id);
ALTER TABLE threads       ADD COLUMN IF NOT EXISTS org_id text REFERENCES organisations(id);
ALTER TABLE findings      ADD COLUMN IF NOT EXISTS org_id text REFERENCES organisations(id);
ALTER TABLE line_parts    ADD COLUMN IF NOT EXISTS org_id text REFERENCES organisations(id);

-- The back-fill. Every existing account becomes an organisation of one, so nothing changes
-- hands and no row becomes unreachable. The id is derived from the user id exactly as
-- `_derived_id` derives the scratch line, so running this a second time inserts nothing and
-- updates nothing — which matters, because this file runs at every boot.
INSERT INTO organisations (id, name)
SELECT 'org-' || u.id, u.email
  FROM users u WHERE u.org_id IS NULL
    ON CONFLICT (id) DO NOTHING;

UPDATE users SET org_id = 'org-' || id WHERE org_id IS NULL;

UPDATE product_lines p SET org_id = u.org_id FROM users u
 WHERE u.id = p.user_id AND p.org_id IS NULL;
UPDATE threads t SET org_id = u.org_id FROM users u
 WHERE u.id = t.user_id AND t.org_id IS NULL;
UPDATE findings f SET org_id = u.org_id FROM users u
 WHERE u.id = f.user_id AND f.org_id IS NULL;
UPDATE line_parts lp SET org_id = u.org_id FROM users u
 WHERE u.id = lp.user_id AND lp.org_id IS NULL;

-- Only once the back-fill has run can `org_id` be read as authoritative, so the NOT NULL
-- goes on afterwards. `IF EXISTS`-style guards do not exist for this, so each is wrapped:
-- setting a column NOT NULL twice is an error, not a no-op.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'users' AND column_name = 'org_id'
                 AND is_nullable = 'YES') THEN
        ALTER TABLE users ALTER COLUMN org_id SET NOT NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'product_lines' AND column_name = 'org_id'
                 AND is_nullable = 'YES') THEN
        ALTER TABLE product_lines ALTER COLUMN org_id SET NOT NULL;
        ALTER TABLE threads       ALTER COLUMN org_id SET NOT NULL;
        ALTER TABLE findings      ALTER COLUMN org_id SET NOT NULL;
        ALTER TABLE line_parts    ALTER COLUMN org_id SET NOT NULL;
    END IF;
END $$;

-- Each mirrors the `user_id` index it replaces as the authorisation boundary. The old ones
-- stay: `user_id` is still read, just no longer to decide who may look.
CREATE INDEX IF NOT EXISTS product_lines_org_idx ON product_lines(org_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS threads_org_idx       ON threads(org_id);
CREATE INDEX IF NOT EXISTS findings_org_mpn_idx  ON findings(org_id, mpn);
CREATE INDEX IF NOT EXISTS findings_org_line_idx ON findings(org_id, line_id);
CREATE INDEX IF NOT EXISTS line_parts_org_mpn_idx ON line_parts(org_id, mpn);
CREATE INDEX IF NOT EXISTS users_org_idx         ON users(org_id);

-- Added 8 Sep 2026. Two lists, deliberately separate, because they answer different
-- questions and are kept by different people. The AML says which parts engineering and
-- quality have qualified; the AVL says which sources procurement will buy from. A part can
-- be qualified and only available from an unapproved vendor, and an approved vendor can
-- stock a part nobody has qualified — one combined list makes both unsayable.
--
-- An organisation with no rows in a table has *no list*, which is not the same as a list
-- that approves nothing. `store.approved_lists` reports the difference, and the rules
-- report `not_applicable` rather than failing every part on every board.
CREATE TABLE IF NOT EXISTS approved_parts (
    org_id       text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    mpn          text NOT NULL,
    manufacturer text,
    qualified_by text REFERENCES users(id) ON DELETE SET NULL,
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, mpn)
);

CREATE TABLE IF NOT EXISTS approved_vendors (
    org_id      text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    distributor text NOT NULL,
    approved_by text REFERENCES users(id) ON DELETE SET NULL,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, distributor)
);

-- Whether an organisation keeps a list at all is a fact about the organisation, and it
-- cannot be derived from an empty table. Without this, an AML that deliberately approves
-- nothing and an AML that was never set up are the same query result.
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS keeps_aml boolean NOT NULL DEFAULT false;
ALTER TABLE organisations ADD COLUMN IF NOT EXISTS keeps_avl boolean NOT NULL DEFAULT false;

-- Who decided, when, on what, and why. A waiver that cannot name its author is not an
-- approval — it is a setting. `rationale` is NOT NULL for the same reason: an approval
-- with no stated reason tells a later reader that somebody clicked, and nothing else.
--
-- `user_id` survives the person leaving: a decision that vanishes from the record when an
-- account is deleted takes the audit trail with it, so this does not cascade.
CREATE TABLE IF NOT EXISTS approvals (
    id         text PRIMARY KEY,
    org_id     text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    thread_id  text NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    user_id    text REFERENCES users(id) ON DELETE SET NULL,
    user_email text NOT NULL,
    roles      text[] NOT NULL,
    rule       text NOT NULL,
    subject    text NOT NULL,
    mpn        text,
    revision   text,
    rationale  text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS approvals_org_idx ON approvals(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS approvals_thread_idx ON approvals(thread_id);

-- Added 8 Sep 2026. The trigger the whole enterprise flow hangs off. Stored because a
-- notice is evidence: item 15's change request has to cite the document that caused it,
-- and "somebody said this part was going away" is not a citation.
--
-- `mpn_line` and its siblings are the quoted lines the reader was believed on. They travel
-- with the values for the same reason a θJA travels with its mounting: a fact whose source
-- cannot be checked is a fact nobody can act on.
CREATE TABLE IF NOT EXISTS notices (
    id                  text PRIMARY KEY,
    org_id              text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id             text REFERENCES users(id) ON DELETE SET NULL,
    mpn                 text NOT NULL,
    mpn_line            text NOT NULL,
    manufacturer        text,
    effective_date      date,
    effective_date_line text,
    replacement_mpn     text,
    replacement_line    text,
    reason              text,
    source              text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notices_org_idx ON notices(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notices_mpn_idx ON notices(org_id, mpn);

-- Added 8 Sep 2026. What actually gets sent to a person: one per affected product line,
-- because the answer differs per line and a single company-wide recommendation is the thing
-- this product exists to replace.
--
-- The whole document is one jsonb column on purpose. It is a *record of what was decided
-- and on what basis*, read back whole and never queried into — and a change request whose
-- fields could drift from the run that produced them would be worse than none. The columns
-- beside it are only the ones something needs to find a request by.
CREATE TABLE IF NOT EXISTS change_requests (
    id         text PRIMARY KEY,
    org_id     text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    notice_id  text REFERENCES notices(id) ON DELETE SET NULL,
    line_id    text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    user_id    text REFERENCES users(id) ON DELETE SET NULL,
    proposal   text,
    document   jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS change_requests_org_idx ON change_requests(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS change_requests_notice_idx ON change_requests(notice_id);

-- Added 8 Sep 2026. What was decided before, so the next notice does not re-litigate it.
--
-- Both directions, and they are not symmetrical. A **rejection** is scoped to the board it
-- happened on and blocks only that board: NCP1117 cooking the gateway says nothing about
-- the sensor node, which runs 20 °C cooler on half the current. A **success** is evidence
-- anywhere in the company — a part already qualified on one line is the cheap answer on
-- the next, which is the entire gap between roughly $1,281 and $15,656 per resolution.
--
-- Keyed by conflict *signature* rather than by rule alone: the signature is engine-owned
-- categorical tokens, so it matches the shape of a problem rather than its wording.
CREATE TABLE IF NOT EXISTS precedents (
    org_id      text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    line_id     text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    signature   text NOT NULL,
    mpn         text NOT NULL,
    outcome     text NOT NULL CHECK (outcome IN ('worked', 'rejected')),
    detail      text,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, line_id, signature, mpn)
);

CREATE INDEX IF NOT EXISTS precedents_lookup_idx ON precedents(org_id, signature, outcome);

-- Added 8 Sep 2026. The design a product line is actually built from.
--
-- One board per line, which is what a product line *is*: a revision of one design. A second
-- upload replaces the first rather than accumulating, because two boards for one line would
-- leave every later question — which one carries U3, which one gets rendered — with two
-- answers and no way to choose.
--
-- The bundle is stored whole, as bytes, rather than unpacked into rows. Nothing here queries
-- into a KiCad project: every fact this system takes from one comes back out of KiCad itself,
-- so what has to survive is the file exactly as it was uploaded. Anything less and a render
-- months later would be of a board we reassembled rather than the board they gave us.
CREATE TABLE IF NOT EXISTS line_boards (
    line_id     text PRIMARY KEY REFERENCES product_lines(id) ON DELETE CASCADE,
    org_id      text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id     text REFERENCES users(id) ON DELETE SET NULL,
    filename    text NOT NULL,
    project     text NOT NULL,
    bundle      bytea NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS line_boards_org_idx ON line_boards(org_id);

-- Added 8 Sep 2026. A substitution waiting for the desk that owns it.
--
-- The run that produced it is not suspended anywhere: the evidence is computed, the
-- proposal is chosen, and what remains is a person saying yes. So this is a row rather than
-- a checkpointed graph — it survives a restart, a reload and a different browser, and the
-- answer can arrive tomorrow from somebody who was not watching.
--
-- `roles` is who may answer, copied from the rule that raised it rather than looked up
-- later: the routing table can change, and a decision that was quality's when it was raised
-- stays quality's. `document` is the whole run — every candidate tried and every verdict —
-- because a decision without its evidence is a signature on nothing.
CREATE TABLE IF NOT EXISTS decisions (
    id          text PRIMARY KEY,
    org_id      text NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    line_id     text NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    notice_id   text REFERENCES notices(id) ON DELETE SET NULL,
    user_id     text REFERENCES users(id) ON DELETE SET NULL,
    slot_id     text NOT NULL,
    retiring    text NOT NULL,
    proposal    text NOT NULL,
    gate_rule   text,
    roles       text[] NOT NULL,
    detail      text NOT NULL,
    document    jsonb NOT NULL,
    state       text NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'approved', 'declined')),
    decided_by  text REFERENCES users(id) ON DELETE SET NULL,
    rationale   text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    decided_at  timestamptz
);

CREATE INDEX IF NOT EXISTS decisions_org_idx ON decisions(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS decisions_line_idx ON decisions(line_id, state);
CREATE INDEX IF NOT EXISTS decisions_notice_idx ON decisions(notice_id);
