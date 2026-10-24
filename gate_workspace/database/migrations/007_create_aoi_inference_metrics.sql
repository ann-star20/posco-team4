CREATE TABLE aoi_inference_metrics (
    job_id UUID NOT NULL,
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    part_inference_ms DOUBLE PRECISION NOT NULL CHECK (part_inference_ms >= 0),
    defect_inference_ms DOUBLE PRECISION NOT NULL CHECK (defect_inference_ms >= 0),
    total_processing_ms DOUBLE PRECISION NOT NULL CHECK (total_processing_ms >= 0),
    part_model JSONB NOT NULL CHECK (jsonb_typeof(part_model) = 'object'),
    defect_model JSONB NOT NULL CHECK (jsonb_typeof(defect_model) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, attempt)
);

CREATE INDEX aoi_inference_metrics_created_idx
ON aoi_inference_metrics(created_at);
