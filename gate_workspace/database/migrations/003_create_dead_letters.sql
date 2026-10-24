CREATE TABLE dead_letters (
    message_hash TEXT PRIMARY KEY,
    event_id UUID,
    run_id UUID,
    raw_message TEXT NOT NULL,
    error_code TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX dead_letters_run_idx ON dead_letters(run_id, last_seen_at);
