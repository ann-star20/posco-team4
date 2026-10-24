ALTER TABLE tcad_verification_candidates
    ADD COLUMN result_origin TEXT CHECK (result_origin IS NULL OR result_origin IN ('mock', 'prod'));
