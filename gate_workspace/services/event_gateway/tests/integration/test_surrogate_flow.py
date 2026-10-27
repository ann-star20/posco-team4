from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from event_gateway.config import Settings
from event_gateway.contracts import EventCreate
from event_gateway.inference_jobs import submit_inference_job, claim_due_aoi_requests
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository, EventConflict
from event_gateway.ros_adapter import store_ros_event
from mock_surrogate.app import predict


def test_ml_response_is_preserved_and_creates_one_verification(test_connection):
    apply_migrations(test_connection, Path(__file__).parents[4] / 'database/migrations')
    request = dict(request_id=str(uuid4()), run_id=str(uuid4()), lot_id='L1', unit_id='U1',
                   stage_id='electrical', stage_attempt=1, model_contract_version='fab-ml-v1',
                   input_payload={'scenario': 'anomaly', 'measurement': {'vgs': 4}})
    accepted = submit_inference_job(test_connection, request, 'mock', 'mock', 'surrogate')
    dispatch = claim_due_aoi_requests(test_connection)[0]
    assert dispatch['task_type'] == 'surrogate'
    response = predict(dispatch)
    event = EventCreate(schema_version=1,event_id=uuid4(),event_type='surrogate.completed',
                        source='jetson.surrogate',severity='warning',occurred_at=datetime.now(timezone.utc),
                        payload={**dispatch, 'response': response})
    repo = EventRepository(test_connection)
    settings = Settings(database_url='unused')
    first = store_ros_event(repo,event,request['run_id'],settings)
    assert store_ros_event(repo,event,request['run_id'],settings) == first
    assert test_connection.execute('SELECT count(*) FROM verification_jobs').fetchone() == (1,)
    assert test_connection.execute('SELECT response_body FROM surrogate_results WHERE job_id=%s',
                                   (accepted['job_id'],)).fetchone()[0] == response
    assert test_connection.execute('SELECT status FROM inference_jobs').fetchone() == ('completed',)


@pytest.mark.parametrize('scenario', ['normal', 'missing_candidate', 'failed'])
def test_ml_non_actionable_results_never_call_tcad(test_connection, scenario):
    apply_migrations(test_connection, Path(__file__).parents[4] / 'database/migrations')
    request = dict(request_id=str(uuid4()),run_id=str(uuid4()),lot_id='L1',unit_id='U1',
                   stage_id='electrical',stage_attempt=1,model_contract_version='fab-ml-v1',
                   input_payload={'scenario':scenario})
    submit_inference_job(test_connection,request,'mock','mock','surrogate')
    dispatch=claim_due_aoi_requests(test_connection)[0]
    event=EventCreate(schema_version=1,event_id=uuid4(),event_type='surrogate.completed',
                      source='jetson.surrogate',severity='info',occurred_at=datetime.now(timezone.utc),
                      payload={**dispatch,'response':predict(dispatch)})
    store_ros_event(EventRepository(test_connection),event,request['run_id'],Settings(database_url='unused'))
    assert test_connection.execute('SELECT count(*) FROM verification_jobs').fetchone() == (0,)
