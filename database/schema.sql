-- Hiring AI Assistant
-- The whole database: 6 tables. Safe to run more than once.
--
--   departments   company departments
--   users         HR / Recruitment logins + HODs and interviewers (records only, they do not log in)
--   jobs          open positions, with the AI shortlist threshold and screening criteria
--   candidates    one row per CV: AI score, where the process is now, and every decision of the process
--   activity_log  history: every step, who recorded it, when, and the details (channel, notes...)
--   login_tokens  who is logged in: one row per login, valid for 7 days

CREATE TABLE IF NOT EXISTS departments (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    full_name      VARCHAR(150) NOT NULL,
    email          VARCHAR(150) UNIQUE NOT NULL,
    role           VARCHAR(20)  NOT NULL CHECK (role IN ('HR', 'HOD', 'INTERVIEWER')),
    department_id  INT REFERENCES departments(id),
    password_hash  TEXT,                 -- only HR / Recruitment users have one (they are the only ones who log in)
    created_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id                   SERIAL PRIMARY KEY,
    title                VARCHAR(200) NOT NULL,
    description          TEXT NOT NULL,
    department_id        INT NOT NULL REFERENCES departments(id),
    shortlist_threshold  INT NOT NULL DEFAULT 70 CHECK (shortlist_threshold BETWEEN 0 AND 100),
    screening_criteria   JSONB,               -- what CVs are checked against: required skills + minimum years
    created_by           INT REFERENCES users(id),
    created_at           TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidates (
    id                  SERIAL PRIMARY KEY,
    job_id              INT NOT NULL REFERENCES jobs(id),
    full_name           VARCHAR(150),
    email               VARCHAR(150),
    cv_file             VARCHAR(255),
    cv_text             TEXT,
    ai_score            INT,
    ai_reason           TEXT,

    -- Where the process is now (current_step is NULL when the process is closed)
    status              VARCHAR(60) DEFAULT 'Screening',
    current_step        VARCHAR(50),

    -- Stage 1: Screening
    shortlist_decision  VARCHAR(20) CHECK (shortlist_decision IN ('Shortlisted', 'Not shortlisted')),

    -- Stage 2: M1 round (interviewers assigned by the HOD, the schedule, the interviewer's feedback)
    interviewer_ids     INT[] NOT NULL DEFAULT '{}',
    m1_scheduled_at     TIMESTAMP,
    m1_location         VARCHAR(255),
    m1_decision         VARCHAR(20) CHECK (m1_decision IN ('Selected', 'Unselected')),
    m1_feedback_by      INT REFERENCES users(id),
    m1_comments         TEXT,

    -- Stage 3: M2 round (the HOD interview and the HOD's final feedback)
    m2_scheduled_at     TIMESTAMP,
    m2_location         VARCHAR(255),
    m2_decision         VARCHAR(20) CHECK (m2_decision IN ('Selected', 'Rejected')),
    m2_feedback_by      INT REFERENCES users(id),
    m2_comments         TEXT,

    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS activity_log (
    id            SERIAL PRIMARY KEY,
    candidate_id  INT REFERENCES candidates(id) ON DELETE CASCADE,
    step          VARCHAR(50) NOT NULL,
    user_id       INT REFERENCES users(id),   -- the HR user who recorded the step (NULL = automatic)
    details       JSONB,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS login_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  CHAR(64) UNIQUE NOT NULL,   -- SHA-256 of the token; the token itself is only in the browser cookie
    expires_at  TIMESTAMP NOT NULL,         -- 7 days after login
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Upgrade an existing database from an older version of this app
-- (adds the new columns; the old tables are moved and removed by setup_db.py).
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE jobs  ADD COLUMN IF NOT EXISTS shortlist_threshold INT NOT NULL DEFAULT 70
    CHECK (shortlist_threshold BETWEEN 0 AND 100);
ALTER TABLE jobs  ADD COLUMN IF NOT EXISTS screening_criteria JSONB;

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS shortlist_decision VARCHAR(20) CHECK (shortlist_decision IN ('Shortlisted', 'Not shortlisted')),
    ADD COLUMN IF NOT EXISTS interviewer_ids    INT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS m1_scheduled_at    TIMESTAMP,
    ADD COLUMN IF NOT EXISTS m1_location        VARCHAR(255),
    ADD COLUMN IF NOT EXISTS m1_decision        VARCHAR(20) CHECK (m1_decision IN ('Selected', 'Unselected')),
    ADD COLUMN IF NOT EXISTS m1_feedback_by     INT REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS m1_comments        TEXT,
    ADD COLUMN IF NOT EXISTS m2_scheduled_at    TIMESTAMP,
    ADD COLUMN IF NOT EXISTS m2_location        VARCHAR(255),
    ADD COLUMN IF NOT EXISTS m2_decision        VARCHAR(20) CHECK (m2_decision IN ('Selected', 'Rejected')),
    ADD COLUMN IF NOT EXISTS m2_feedback_by     INT REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS m2_comments        TEXT;
