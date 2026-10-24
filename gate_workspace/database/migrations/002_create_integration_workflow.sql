CREATE TABLE integration_runs (
    run_id UUID PRIMARY KEY,
    tcad_mode TEXT NOT NULL CHECK (tcad_mode IN ('mock', 'prod')),
    unity_mode TEXT NOT NULL CHECK (unity_mode IN ('mock', 'prod')),
    input_origin TEXT NOT NULL CHECK (input_origin IN ('synthetic', 'model')),
    baseline_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE events ADD COLUMN run_id UUID REFERENCES integration_runs(run_id);
CREATE INDEX events_run_sequence_idx ON events(run_id, sequence);

CREATE TABLE correction_proposals (
    proposal_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES integration_runs(run_id),
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    representation TEXT NOT NULL CHECK (representation = 'normalized_ratio'),
    x_current JSONB NOT NULL CHECK (jsonb_typeof(x_current) = 'object'),
    delta_x JSONB NOT NULL CHECK (jsonb_typeof(delta_x) = 'object'),
    x_candidate JSONB NOT NULL CHECK (jsonb_typeof(x_candidate) = 'object'),
    y_observed JSONB NOT NULL CHECK (jsonb_typeof(y_observed) = 'object'),
    targets JSONB NOT NULL CHECK (jsonb_typeof(targets) = 'object'),
    y_verified JSONB,
    result_origin TEXT CHECK (result_origin IN ('mock', 'prod')),
    status TEXT NOT NULL DEFAULT 'proposed'
      CHECK (status IN ('proposed', 'verifying', 'verified', 'rejected', 'failed', 'approved', 'applied')),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status NOT IN ('verified','rejected','approved','applied')
           OR (y_verified IS NOT NULL AND result_origin IS NOT NULL)),
    CHECK (status NOT IN ('approved','applied')
           OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE verification_jobs (
    request_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL UNIQUE REFERENCES correction_proposals(proposal_id),
    tcad_mode TEXT NOT NULL CHECK (tcad_mode IN ('mock','prod')),
    endpoint_url TEXT NOT NULL,
    remote_job_id TEXT,
    request_body JSONB NOT NULL,
    response_body JSONB,
    status TEXT NOT NULL DEFAULT 'queued'
      CHECK (status IN ('queued','running','succeeded','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((lease_token IS NULL) = (lease_until IS NULL))
);
CREATE INDEX verification_jobs_due_idx ON verification_jobs(next_attempt_at)
    WHERE status IN ('queued','running');

CREATE TABLE commands (
    command_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL UNIQUE REFERENCES correction_proposals(proposal_id),
    run_id UUID NOT NULL REFERENCES integration_runs(run_id),
    scope TEXT NOT NULL CHECK (scope = 'simulation'),
    effective_from_lot TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','sent','applied','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    applied_event_id UUID UNIQUE REFERENCES events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    CHECK ((lease_token IS NULL) = (lease_until IS NULL)),
    CHECK (status <> 'applied' OR
           (applied_event_id IS NOT NULL AND applied_at IS NOT NULL))
);
CREATE INDEX commands_due_idx ON commands(next_attempt_at)
    WHERE status IN ('pending','sent');
