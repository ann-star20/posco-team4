ALTER TABLE inference_jobs DROP CONSTRAINT inference_jobs_task_type_check;
ALTER TABLE inference_jobs ADD CONSTRAINT inference_jobs_task_type_check
    CHECK (task_type IN ('aoi','surrogate','diagnosis'));

CREATE TABLE diagnosis_results (
    job_id UUID PRIMARY KEY REFERENCES inference_jobs(job_id),
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    response_body JSONB NOT NULL CHECK (jsonb_typeof(response_body) = 'object'),
    top_category TEXT,
    top_probability DOUBLE PRECISION,
    compensation_route TEXT CHECK (
        compensation_route IN ('tcad_verify','no_action','manual')
    ),
    high_confidence BOOLEAN,
    routing_status TEXT NOT NULL CHECK (
        routing_status IN ('normal','verification_queued','review_required','failed')
    ),
    proposal_id UUID REFERENCES correction_proposals(proposal_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ml_inference_executions (
    execution_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES inference_jobs(job_id),
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    task_type TEXT NOT NULL CHECK (task_type IN ('surrogate','diagnosis')),
    model_name TEXT,
    model_version TEXT,
    model_artifact_hash TEXT,
    training_data_version TEXT,
    device TEXT,
    precision TEXT,
    status TEXT NOT NULL CHECK (status IN ('succeeded','failed')),
    error_code TEXT,
    queue_wait_ms DOUBLE PRECISION,
    inference_duration_ms DOUBLE PRECISION,
    service_duration_ms DOUBLE PRECISION,
    stage_metrics JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(stage_metrics) = 'array'),
    runtime_metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(runtime_metadata) = 'object'),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(job_id, attempt)
);

CREATE INDEX diagnosis_results_category_idx
    ON diagnosis_results(top_category, created_at DESC);
CREATE INDEX ml_inference_executions_model_idx
    ON ml_inference_executions(model_name, model_version, completed_at DESC);
