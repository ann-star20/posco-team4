CREATE TABLE surrogate_results (
    job_id UUID PRIMARY KEY REFERENCES inference_jobs(job_id),
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    response_body JSONB NOT NULL CHECK (jsonb_typeof(response_body)='object'),
    routing_status TEXT NOT NULL CHECK (routing_status IN ('normal','verification_queued','review_required','failed')),
    proposal_id UUID REFERENCES correction_proposals(proposal_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE commands ADD COLUMN delivery_target TEXT NOT NULL DEFAULT 'jetson'
    CHECK (delivery_target IN ('jetson','unity'));
CREATE INDEX commands_unity_pending_idx ON commands(run_id,created_at)
    WHERE delivery_target='unity' AND status IN ('pending','sent');
