CREATE TABLE equipment_state_intervals (
    interval_id UUID PRIMARY KEY,
    factory_session_id UUID NOT NULL REFERENCES factory_sessions(factory_session_id),
    equipment_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('idle','running','blocked','paused','down')),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    start_event_id UUID NOT NULL REFERENCES events(event_id),
    end_event_id UUID REFERENCES events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE UNIQUE INDEX equipment_state_intervals_open_idx
    ON equipment_state_intervals(factory_session_id, equipment_id)
    WHERE ended_at IS NULL;

CREATE INDEX equipment_state_intervals_session_idx
    ON equipment_state_intervals(factory_session_id, started_at);

CREATE TABLE lot_activity_intervals (
    interval_id UUID PRIMARY KEY,
    factory_session_id UUID NOT NULL REFERENCES factory_sessions(factory_session_id),
    lot_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('activity','disposition')),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    start_event_id UUID NOT NULL REFERENCES events(event_id),
    end_event_id UUID REFERENCES events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR ended_at >= started_at),
    CHECK (
        (category = 'activity' AND status IN ('waiting','processing','transferring'))
        OR
        (category = 'disposition' AND status IN ('result_wait','quality_hold','completed','removed'))
    )
);

CREATE UNIQUE INDEX lot_activity_intervals_open_idx
    ON lot_activity_intervals(factory_session_id, lot_id, category)
    WHERE ended_at IS NULL;

CREATE INDEX lot_activity_intervals_session_idx
    ON lot_activity_intervals(factory_session_id, started_at);
