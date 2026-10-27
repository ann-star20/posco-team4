CREATE TABLE events (
    sequence       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id       UUID NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL,
    event_type     TEXT NOT NULL,
    source         TEXT NOT NULL,
    severity       TEXT NOT NULL,
    correlation_id TEXT,
    causation_id   UUID,
    payload        JSONB NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    received_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (schema_version > 0),
    CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical'))
);

CREATE INDEX events_type_sequence_idx
    ON events (event_type, sequence);

CREATE INDEX events_correlation_sequence_idx
    ON events (correlation_id, sequence)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX events_occurred_at_idx
    ON events (occurred_at);
