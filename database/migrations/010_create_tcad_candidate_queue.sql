CREATE TABLE tcad_proposal_groups (
    proposal_id UUID PRIMARY KEY,
    diagnosis_job_id UUID NOT NULL UNIQUE REFERENCES inference_jobs(job_id),
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    run_id UUID NOT NULL REFERENCES integration_runs(run_id),
    original_request_id UUID NOT NULL,
    model_contract_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    routing_snapshot JSONB NOT NULL CHECK (jsonb_typeof(routing_snapshot) = 'object'),
    candidate_count INTEGER NOT NULL CHECK (candidate_count > 0),
    terminal_count INTEGER NOT NULL DEFAULT 0
      CHECK (terminal_count >= 0 AND terminal_count <= candidate_count),
    status TEXT NOT NULL DEFAULT 'queued'
      CHECK (status IN ('queued','running','completed','failed','cancelled','review_required')),
    selected_tcad_request_id UUID,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((approved_by IS NULL) = (approved_at IS NULL))
);

CREATE TABLE tcad_verification_candidates (
    tcad_request_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL REFERENCES tcad_proposal_groups(proposal_id),
    candidate_index INTEGER NOT NULL CHECK (candidate_index >= 0),
    process_parameters JSONB NOT NULL CHECK (jsonb_typeof(process_parameters) = 'object'),
    predicted_outputs JSONB NOT NULL CHECK (jsonb_typeof(predicted_outputs) = 'object'),
    requested_outputs JSONB NOT NULL CHECK (jsonb_typeof(requested_outputs) = 'array'),
    request_body JSONB NOT NULL CHECK (jsonb_typeof(request_body) = 'object'),
    acceptance_body JSONB CHECK (
      acceptance_body IS NULL OR jsonb_typeof(acceptance_body) = 'object'
    ),
    latest_response_body JSONB CHECK (
      latest_response_body IS NULL OR jsonb_typeof(latest_response_body) = 'object'
    ),
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','submitting','queued','running','succeeded','failed','cancelled','expired')),
    queue_position INTEGER CHECK (queue_position IS NULL OR queue_position >= 0),
    progress JSONB CHECK (progress IS NULL OR jsonb_typeof(progress) = 'object'),
    result_payload JSONB CHECK (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'),
    prediction_error JSONB CHECK (
      prediction_error IS NULL OR jsonb_typeof(prediction_error) = 'object'
    ),
    metadata JSONB CHECK (metadata IS NULL OR jsonb_typeof(metadata) = 'object'),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ NOT NULL,
    last_stage TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(proposal_id, candidate_index),
    CHECK ((lease_token IS NULL) = (lease_until IS NULL))
);

ALTER TABLE tcad_proposal_groups
    ADD CONSTRAINT tcad_proposal_groups_selected_candidate_fk
    FOREIGN KEY (selected_tcad_request_id)
    REFERENCES tcad_verification_candidates(tcad_request_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX tcad_verification_candidates_due_idx
    ON tcad_verification_candidates(next_attempt_at, created_at)
    WHERE status IN ('pending','submitting','queued','running');

CREATE INDEX tcad_verification_candidates_group_idx
    ON tcad_verification_candidates(proposal_id, candidate_index);
