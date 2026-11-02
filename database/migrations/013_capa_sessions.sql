CREATE TABLE factory_sessions (
    factory_session_id UUID PRIMARY KEY,
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    ended_event_id UUID REFERENCES events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((status = 'ended') = (ended_at IS NOT NULL)),
    CHECK ((ended_event_id IS NULL) = (ended_at IS NULL))
);

CREATE TABLE factory_session_equipment (
    factory_session_id UUID NOT NULL REFERENCES factory_sessions(factory_session_id),
    equipment_id TEXT NOT NULL,
    equipment_kind TEXT NOT NULL CHECK (
        equipment_kind IN ('oxidation','film_inspection','ion_implant','aoi','oht','stocker')
    ),
    slot_count INTEGER CHECK (slot_count IS NULL OR slot_count > 0),
    source_event_id UUID NOT NULL REFERENCES events(event_id),
    registered_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (factory_session_id, equipment_id)
);

CREATE INDEX factory_session_equipment_session_idx
    ON factory_session_equipment(factory_session_id);

CREATE TABLE factory_lots (
    factory_session_id UUID NOT NULL REFERENCES factory_sessions(factory_session_id),
    lot_id TEXT NOT NULL,
    lot_kind TEXT NOT NULL CHECK (lot_kind IN ('wafer_route','aoi_product')),
    carrier_id TEXT,
    representative_wafer_id TEXT,
    product_id TEXT,
    recipe_version TEXT,
    source_event_id UUID NOT NULL REFERENCES events(event_id),
    registered_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (factory_session_id, lot_id),
    CHECK (
        (lot_kind = 'wafer_route' AND representative_wafer_id IS NOT NULL AND product_id IS NULL)
        OR
        (lot_kind = 'aoi_product' AND product_id IS NOT NULL AND representative_wafer_id IS NULL)
    )
);

CREATE INDEX factory_lots_session_idx
    ON factory_lots(factory_session_id);
