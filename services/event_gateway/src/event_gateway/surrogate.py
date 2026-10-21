"""Preserve model responses and atomically queue eligible TCAD proposals."""
from uuid import UUID, uuid5
from psycopg.types.json import Jsonb
from .contracts import CorrectionProposal
from .repository import EventConflict
from .ml_contracts import validate_model_response
from .ml_execution import store_ml_execution


def ingest_surrogate(repository, event, run_id, settings):
    db=repository.connection
    payload=event.payload
    with db.transaction():
        # Match the normal event lock ordering before acquiring a job row lock.
        receipt=repository._insert_event(event,run_id)
        row=db.execute('SELECT run_id,request_id,stage_attempt,task_type,request_body,result_event_id,status '
                       'FROM inference_jobs WHERE job_id=%s FOR UPDATE',(UUID(payload['job_id']),)).fetchone()
        if (not row or row[:4]!=(run_id,UUID(payload['request_id']),int(payload['attempt']),'surrogate')
                or event.source!='jetson.surrogate'):
            raise EventConflict('ML result does not match request')
        if row[5] is not None:
            if row[5]!=event.event_id:raise EventConflict('ML job already closed')
            return receipt
        if row[6]=='cancelled':raise EventConflict('ML job cancelled')
        response=payload['response']
        parsed=validate_model_response('surrogate',response)
        if (response.get('request_id')!=str(row[1]) or response.get('job_id')!=payload['job_id']
                or response.get('result_origin')!=row[4].get('surrogate_mode','mock')):
            raise EventConflict('ML response identity or origin mismatch')
        status=response.get('status')
        if status not in {'succeeded','failed'}:raise EventConflict('invalid ML status')
        route='failed' if status=='failed' else 'normal'
        proposal_id=None
        mode,_,_,baseline=repository.resolve_run(run_id,settings.tcad_mode,settings.unity_mode)
        if status=='succeeded' and response.get('anomaly_detected') is True:
            route='review_required'
            raw=response.get('tcad_proposal')
            supported=(response.get('model_contract_version')==row[4].get('model_contract_version')=='fab-ml-v1')
            if raw and supported and not (mode=='prod' and response['result_origin']=='mock'):
                try:
                    proposal=CorrectionProposal.model_validate(raw)
                    if proposal.run_id!=run_id or proposal.baseline_version!=baseline:
                        raise ValueError('proposal scope mismatch')
                except ValueError:
                    proposal=None
                if proposal is not None:
                    endpoint=settings.tcad_mock_url if mode=='mock' else settings.tcad_prod_url
                    if endpoint:
                        repository.ingest_proposal(event,proposal,uuid5(event.event_id,'tcad-verification'),mode,endpoint)
                        route='verification_queued';proposal_id=proposal.proposal_id
        elif status=='succeeded' and response.get('anomaly_detected') is not False:
            route='review_required'
        db.execute('INSERT INTO surrogate_results(job_id,source_event_id,response_body,routing_status,proposal_id) '
                   'VALUES (%s,%s,%s,%s,%s)',(UUID(payload['job_id']),event.event_id,Jsonb(response),route,proposal_id))
        db.execute('UPDATE inference_jobs SET status=%s,result_event_id=%s,updated_at=now() WHERE job_id=%s',
                   ('failed' if status=='failed' else 'completed',event.event_id,UUID(payload['job_id'])))
        store_ml_execution(db,event.event_id,UUID(payload['job_id']),payload['attempt'],'surrogate',response,
                           payload.get('execution_attempt',1))
        db.execute("UPDATE inference_dispatches SET status='completed' WHERE job_id=%s",(UUID(payload['job_id']),))
        return receipt
