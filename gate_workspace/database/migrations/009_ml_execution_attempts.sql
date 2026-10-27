ALTER TABLE ml_inference_executions
    DROP CONSTRAINT ml_inference_executions_job_id_attempt_key;

ALTER TABLE ml_inference_executions
    ADD COLUMN execution_attempt INTEGER NOT NULL DEFAULT 1
    CHECK (execution_attempt > 0);

ALTER TABLE ml_inference_executions
    ADD CONSTRAINT ml_inference_executions_job_attempt_execution_key
    UNIQUE(job_id, attempt, execution_attempt);
