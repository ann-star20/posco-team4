CREATE TABLE inference_jobs (
    job_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    run_id UUID NOT NULL REFERENCES integration_runs(run_id),
    task_type TEXT NOT NULL CHECK (task_type IN ('aoi', 'surrogate')),
    lot_id TEXT NOT NULL CHECK (length(btrim(lot_id)) > 0),
    unit_id TEXT NOT NULL CHECK (length(btrim(unit_id)) > 0),
    stage_id TEXT NOT NULL CHECK (length(btrim(stage_id)) > 0),
    stage_attempt INTEGER NOT NULL CHECK (stage_attempt > 0),
    expected_stage_version INTEGER,
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    request_body JSONB NOT NULL CHECK (jsonb_typeof(request_body) = 'object'),
    status TEXT NOT NULL DEFAULT 'queued'
      CHECK (status IN ('queued','dispatching','accepted','running','completed','failed','cancelled')),
    result_event_id UUID REFERENCES events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX inference_jobs_active_scope_idx
ON inference_jobs(run_id,unit_id,stage_id)
WHERE status IN ('queued','dispatching','accepted','running');

CREATE TABLE inference_dispatches (
    job_id UUID PRIMARY KEY REFERENCES inference_jobs(job_id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','completed')),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    CHECK ((lease_token IS NULL) = (lease_until IS NULL))
);

CREATE INDEX inference_dispatches_due_idx ON inference_dispatches(next_attempt_at)
WHERE status = 'pending';
