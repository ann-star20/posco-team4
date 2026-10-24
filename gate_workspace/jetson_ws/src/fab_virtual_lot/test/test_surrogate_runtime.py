from uuid import uuid4
import json

from fab_virtual_lot.surrogate_worker import SurrogateRuntime


def test_ml_request_survives_restart_and_result_waits_for_ack(tmp_path):
    request=dict(job_id=str(uuid4()),request_id=str(uuid4()),run_id=str(uuid4()),
                 task_type='surrogate',attempt=1,model_contract_version='fab-ml-v1',input_payload={'x':1})
    runtime=SurrogateRuntime(tmp_path/'ml.sqlite')
    runtime.accept(request);runtime.accept(request);runtime.close()
    runtime=SurrogateRuntime(tmp_path/'ml.sqlite')
    calls=[]
    runtime.process_next(lambda body: calls.append(body) or {'status':'succeeded'})
    runtime.process_next(lambda body: calls.append(body))
    assert len(calls)==1
    events=runtime.pending_events()
    assert len(events)==1
    event=json.loads(events[0][2])
    assert runtime.ack(event['event_id'],event['run_id'],9)
    assert runtime.pending_events()==[]
    runtime.close()
