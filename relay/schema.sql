-- Loop Relay swarm.db schema
-- Implements Vera's architecture v1-2026-03-01
-- Compatible with SQLite 3.x

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─── JOBS ────────────────────────────────────────────────────────────────────
-- One row per loop/job. "job" and "loop" are used interchangeably in code.
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,          -- UUID v4
    name            TEXT,                      -- human-readable label
    domain          TEXT NOT NULL,             -- e.g. "research", "yapcad", "security"
    status          TEXT NOT NULL DEFAULT 'active',
                                               -- 'active' | 'complete' | 'abandoned' | 'converged'
    created_utc     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_utc     TEXT NOT NULL DEFAULT (datetime('now')),
    total_cost_usd  REAL NOT NULL DEFAULT 0.0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    sprint_count    INTEGER NOT NULL DEFAULT 0,
    worker_prompt_version TEXT NOT NULL DEFAULT 'v1',
    config_json     TEXT NOT NULL DEFAULT '{}'  -- job-specific parameters
);

-- ─── SPRINTS ─────────────────────────────────────────────────────────────────
-- One row per sprint attempt. A crashed sprint and its re-run are separate rows.
CREATE TABLE IF NOT EXISTS sprints (
    job_id              TEXT NOT NULL,
    sprint_num          INTEGER NOT NULL,
    status              TEXT NOT NULL DEFAULT 'running',
                                               -- 'running' | 'summarizing' | 'complete'
                                               -- | 'budget_exhausted' | 'forced' | 'crashed'
    worker_session_id   TEXT,                  -- OpenClaw session ID
    orchestrator_session_id TEXT,
    started_utc         TEXT NOT NULL DEFAULT (datetime('now')),
    ended_utc           TEXT,
    baton_json          TEXT,                  -- outgoing baton (NULL until complete/forced)
    findings_count      INTEGER NOT NULL DEFAULT 0,
    tokens_consumed     INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0.0,
    handoff_type        TEXT,                  -- 'clean' | 'budget_exhausted' | 'forced' | 'crashed'
    notes               TEXT,                  -- orchestrator notes on this sprint
    PRIMARY KEY (job_id, sprint_num),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- ─── FINDINGS ────────────────────────────────────────────────────────────────
-- Raw findings — NEVER deleted. Append-only.
CREATE TABLE IF NOT EXISTS findings (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    job_id          TEXT NOT NULL,
    sprint_num      INTEGER NOT NULL,
    thesis_id       TEXT,                      -- links to a thesis (nullable)
    question_id     TEXT,                      -- links to a question (nullable)
    source          TEXT,                      -- URL, document ref, tool name
    content         TEXT NOT NULL,             -- the finding, verbatim
    confidence      REAL,                      -- 0.0-1.0
    is_anchor       INTEGER NOT NULL DEFAULT 0,-- 1 = never compress away
    content_hash    TEXT,                      -- sha256 of content for dedup
    created_utc     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- ─── QUESTIONS ───────────────────────────────────────────────────────────────
-- Open research questions, tracked across sprints.
CREATE TABLE IF NOT EXISTS questions (
    job_id              TEXT NOT NULL,
    question_id         TEXT NOT NULL,
    text                TEXT NOT NULL,
    priority            TEXT NOT NULL DEFAULT 'medium',  -- 'high' | 'medium' | 'low'
    status              TEXT NOT NULL DEFAULT 'open',    -- 'open' | 'resolved' | 'dropped'
    suggested_sources   TEXT,                            -- JSON array of strings
    raised_sprint       INTEGER,
    resolved_sprint     INTEGER,
    created_utc         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_utc         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, question_id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- ─── BATONS ──────────────────────────────────────────────────────────────────
-- Baton history. One row per sprint completion. Append-only.
CREATE TABLE IF NOT EXISTS batons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    sprint_num      INTEGER NOT NULL,          -- sprint that produced this baton
    schema_version  INTEGER NOT NULL DEFAULT 2,
    baton_json      TEXT NOT NULL,             -- full baton as JSON
    quality_score   REAL,                      -- digest quality score if applicable
    created_utc     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- ─── EVENTS ──────────────────────────────────────────────────────────────────
-- Audit log. Every significant orchestrator action lands here.
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT,                      -- NULL for system events
    sprint_num      INTEGER,
    event_type      TEXT NOT NULL,             -- 'job_created' | 'sprint_started' | 'sprint_complete'
                                               -- | 'sprint_crashed' | 'baton_generated' | 'summarized'
                                               -- | 'zombie_detected' | 'job_complete' | 'job_abandoned'
                                               -- | 'convergence_triggered' | 'orchestrator_started'
    payload_json    TEXT,                      -- event-specific data
    created_utc     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─── DIGESTS ─────────────────────────────────────────────────────────────────
-- Summarization history. Append-only — never overwrite.
CREATE TABLE IF NOT EXISTS digests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL,
    generated_sprint    INTEGER NOT NULL,
    sprint_range_start  INTEGER NOT NULL,
    sprint_range_end    INTEGER NOT NULL,
    content             TEXT NOT NULL,
    model               TEXT,
    quality_score       REAL,
    token_count         INTEGER,
    created_utc         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- ─── THESES ──────────────────────────────────────────────────────────────────
-- Thesis state tracking across sprints.
CREATE TABLE IF NOT EXISTS theses (
    job_id              TEXT NOT NULL,
    thesis_id           TEXT NOT NULL,
    text                TEXT,
    status              TEXT NOT NULL DEFAULT 'open',
                                               -- 'open' | 'confirmed' | 'refuted' | 'degraded'
    confidence          REAL,
    last_updated_sprint INTEGER,
    created_utc         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_utc         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, thesis_id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sprints_job_status     ON sprints(job_id, status);
CREATE INDEX IF NOT EXISTS idx_sprints_job_num        ON sprints(job_id, sprint_num);
CREATE INDEX IF NOT EXISTS idx_findings_job_sprint    ON findings(job_id, sprint_num);
CREATE INDEX IF NOT EXISTS idx_findings_job_thesis    ON findings(job_id, thesis_id);
CREATE INDEX IF NOT EXISTS idx_findings_hash          ON findings(content_hash);
CREATE INDEX IF NOT EXISTS idx_findings_anchor        ON findings(job_id, is_anchor);
CREATE INDEX IF NOT EXISTS idx_questions_job_status   ON questions(job_id, status);
CREATE INDEX IF NOT EXISTS idx_batons_job_sprint      ON batons(job_id, sprint_num);
CREATE INDEX IF NOT EXISTS idx_events_job             ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_type            ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_digests_job_sprint     ON digests(job_id, generated_sprint);
CREATE INDEX IF NOT EXISTS idx_jobs_status            ON jobs(status);
