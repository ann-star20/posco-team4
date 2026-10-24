from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
import pytest
from event_gateway.migrate import apply_migrations
from event_gateway.inference_jobs import submit_inference_job,claim_due_aoi_requests
from mock_surrogate.app import predict
from event_gateway.contracts import EventCreate
from event_gateway.repository import EventRepository
from event_gateway.ros_adapter import store_ros_event
from event_gateway.config import Settings
from event_gateway.commands import approve_proposal
from event_gateway.command_dispatcher import claim_due_commands
from event_gateway.unity_delivery import accept_applied, UnityConflict


def test_unity_ack_is_idempotent_and_ros_does_not_receive_unity_command(test_connection):
    db=test_connection
    apply_migrations(db,Path(__file__).parents[4]/'database/migrations')
    request=dict(request_id=str(uuid4()),run_id=str(uuid4()),lot_id='L1',unit_id='U1',
                 stage_id='electrical',stage_attempt=1,model_contract_version='fab-ml-v1',input_payload={'scenario':'anomaly'})
    submit_inference_job(db,request,'mock','mock','surrogate')
    dispatch=claim_due_aoi_requests(db)[0];response=predict(dispatch)
    event=EventCreate(schema_version=1,event_id=uuid4(),event_type='surrogate.completed',source='jetson.surrogate',
                      severity='info',occurred_at=datetime.now(timezone.utc),payload={**dispatch,'response':response})
    store_ros_event(EventRepository(db),event,request['run_id'],Settings(database_url='unused'))
    proposal_id=response['tcad_proposal']['proposal_id']
    db.execute("UPDATE correction_proposals SET status='verified',result_origin='mock',y_verified='{}' WHERE proposal_id=%s",(proposal_id,))
    command_id=approve_proposal(db,proposal_id,'tester','L2',target='unity')
    assert claim_due_commands(db)==[]
    command=claim_due_commands(db,target='unity',run_id=request['run_id'])[0]
    ack={'command_id':str(command_id),'run_id':request['run_id'],'effective_from_lot':'L2','x_applied':command['x_candidate']}
    with pytest.raises(UnityConflict):accept_applied(db,{**ack,'effective_from_lot':'wrong'})
    receipt=accept_applied(db,ack)
    assert accept_applied(db,ack)==receipt
    assert db.execute('SELECT status FROM commands WHERE command_id=%s',(command_id,)).fetchone()==('applied',)
