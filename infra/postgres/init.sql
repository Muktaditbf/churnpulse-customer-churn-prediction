-- ChurnPulse v2 database schema (runs once when the Postgres volume is created).

-- Customer master data: identity, contact and persona. The live profile used
-- for scoring is held by Flink and mirrored into customer_scores.profile.
CREATE TABLE customers (
    customer_id   TEXT PRIMARY KEY,
    name          TEXT        NOT NULL,
    email         TEXT,
    phone         TEXT,
    city          TEXT,
    zip_code      TEXT,
    profile       JSONB       NOT NULL,          -- initial persona profile
    persona       JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- psychographic extras (not model inputs)
    cltv          DOUBLE PRECISION,              -- lifetime value (dataset) - display only
    actual_churn  BOOLEAN,                       -- dataset label, NULL for new members
    source        TEXT        NOT NULL DEFAULT 'dataset' CHECK (source IN ('dataset', 'manual', 'import')),
    archived      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX customers_search ON customers (lower(name), lower(email), lower(city));
CREATE INDEX customers_source ON customers (source, created_at DESC);

CREATE UNLOGGED TABLE customers_staging (LIKE customers INCLUDING DEFAULTS);

-- Latest score per customer: what the dashboard lists and sorts.
CREATE TABLE customer_scores (
    customer_id          TEXT PRIMARY KEY REFERENCES customers (customer_id),
    probability          DOUBLE PRECISION NOT NULL,
    previous_probability DOUBLE PRECISION,
    risk_band            TEXT NOT NULL,
    will_churn           BOOLEAN NOT NULL,
    model_used           TEXT NOT NULL,
    reasons              JSONB,
    signals              JSONB,
    profile              JSONB NOT NULL,
    monthly_charges      DOUBLE PRECISION NOT NULL,
    last_event_type      TEXT,
    alert                TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX customer_scores_probability ON customer_scores (probability DESC);
CREATE INDEX customer_scores_band ON customer_scores (risk_band);

-- Every prediction, for per-customer history and the live feed.
CREATE TABLE prediction_events (
    id                   BIGSERIAL PRIMARY KEY,
    customer_id          TEXT NOT NULL,
    event_id             TEXT NOT NULL UNIQUE,
    event_type           TEXT NOT NULL,
    event_source         TEXT,
    probability          DOUBLE PRECISION NOT NULL,
    previous_probability DOUBLE PRECISION,
    risk_band            TEXT NOT NULL,
    model_used           TEXT,
    alert                TEXT,
    reasons              JSONB,
    end_to_end_ms        DOUBLE PRECISION,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX prediction_events_customer ON prediction_events (customer_id, created_at DESC);
CREATE INDEX prediction_events_time ON prediction_events (created_at DESC);
CREATE INDEX prediction_events_alerts ON prediction_events (created_at DESC) WHERE alert IS NOT NULL;

-- 10-second stream summaries computed by Flink.
CREATE TABLE stream_stats (
    window_end         TIMESTAMPTZ PRIMARY KEY,
    predictions        INTEGER NOT NULL,
    live_events        INTEGER NOT NULL,
    alerts             INTEGER NOT NULL,
    high_risk          INTEGER NOT NULL,
    avg_probability    DOUBLE PRECISION,
    avg_processing_ms  DOUBLE PRECISION
);

-- Retention actions: what was suggested, what was done, what happened.
-- This is the feedback log for measuring real action effectiveness.
CREATE TABLE retention_actions (
    id                  BIGSERIAL PRIMARY KEY,
    customer_id         TEXT NOT NULL REFERENCES customers (customer_id),
    action_id           TEXT NOT NULL,
    title               TEXT NOT NULL,
    channel             TEXT,
    probability_before  DOUBLE PRECISION NOT NULL,
    probability_after   DOUBLE PRECISION NOT NULL,
    expected_value      DOUBLE PRECISION NOT NULL,
    cost                DOUBLE PRECISION NOT NULL,
    status              TEXT NOT NULL DEFAULT 'contacted'
                        CHECK (status IN ('contacted', 'accepted', 'declined')),
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX retention_actions_customer ON retention_actions (customer_id, created_at DESC);
CREATE INDEX retention_actions_status ON retention_actions (status, updated_at DESC);
