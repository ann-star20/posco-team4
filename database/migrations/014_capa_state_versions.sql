CREATE TABLE factory_object_versions (
    factory_session_id UUID NOT NULL REFERENCES factory_sessions(factory_session_id),
    object_key TEXT NOT NULL,
    state_version INTEGER NOT NULL CHECK (state_version > 0),
    last_event_id UUID NOT NULL REFERENCES events(event_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (factory_session_id, object_key)
);
