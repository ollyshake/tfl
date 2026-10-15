CREATE TABLE collection_runs (
    id UUID PRIMARY KEY,
    endpoint TEXT NOT NULL,
    target TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'error')),
    http_status INTEGER,
    error TEXT,
    raw_response JSONB
);

CREATE INDEX collection_runs_target_time_idx
    ON collection_runs (target, collected_at DESC);