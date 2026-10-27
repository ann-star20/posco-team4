ALTER TABLE tcad_verification_candidates
    ADD COLUMN spec_verdict JSONB CHECK (spec_verdict IS NULL OR jsonb_typeof(spec_verdict) = 'object');
