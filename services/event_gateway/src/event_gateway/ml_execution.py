"""Extract queryable execution metrics while preserving original model metadata."""

from uuid import uuid5

from psycopg.types.json import Jsonb


def store_ml_execution(db, event_id, job_id, attempt, task_type, response):
    metadata = response.get("metadata") or {}
    model = metadata.get("model") or {}
    timing = metadata.get("timing_ms") or {}
    execution_id = uuid5(event_id, "ml-execution")
    db.execute(
        "INSERT INTO ml_inference_executions("
        "execution_id,job_id,attempt,task_type,model_name,model_version,model_artifact_hash,"
        "training_data_version,device,precision,status,error_code,queue_wait_ms,"
        "inference_duration_ms,service_duration_ms,stage_metrics,runtime_metadata) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (execution_id, job_id, int(attempt), task_type, model.get("name"), model.get("version"),
         model.get("artifact_hash"), model.get("training_data_version"), model.get("device"),
         model.get("precision"), response["status"], response.get("error_code"),
         timing.get("queue_wait"), timing.get("inference_total"), timing.get("service_total"),
         Jsonb(metadata.get("stages") or []), Jsonb(metadata)),
    )
    return execution_id
