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
