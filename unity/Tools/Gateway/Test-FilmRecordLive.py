"""One Unity-built normal inspection record; verify originals through DB replay."""
import asyncio,json,os,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/FabSocket/.deps'))
from websockets.asyncio.client import connect
OUT=ROOT/'Tools/Gateway/FilmNormalRecordIntegration'
BASE='http://192.168.212.10:8000'
def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def get(path,token):
    with urllib.request.urlopen(urllib.request.Request(BASE+path,headers={'X-Unity-Token':token}),timeout=10) as r:return json.load(r)
async def run():
    if (OUT/'active.json').exists():raise RuntimeError('Existing request: inspect its IDs; do not resubmit')
    token=os.environ['UNITY_GATEWAY_TEST_TOKEN']
    request=json.loads((ROOT/'Temp/FilmGateway/film-normal-live.request.json').read_text(encoding='utf-8-sig'))
    assert request['type']=='surrogate.requested' and request['stage_id']=='film_inspection_record'
    p=request['input_payload']['provenance'];record=p['inspection_result']
    assert record['purpose']=='film_inspection_record' and record['verdict']==record['thickness_verdict']==record['electrical_verdict']=='OK'
    assert not record['diagnosis_requested'] and not record['correction_candidate']
    assert not (p.get('tcad') or {}).get('purpose')
    run_id=request['run_id']
    async with connect('ws://192.168.212.10:8000/api/v1/stream?run_id='+run_id+'&after_sequence=0',proxy=None,max_size=4_000_000) as stream:
        async with connect('ws://192.168.212.10:8000/api/v1/control',proxy=None,additional_headers={'X-Unity-Token':token}) as control:
            save('active.json',dict(request_id=request['request_id'],run_id=run_id,state='before_send'))
            save('request.json',request)
            await control.send(json.dumps(request))
            ack=json.loads(await asyncio.wait_for(control.recv(),15));save('accepted.json',ack)
            assert ack.get('type')=='request.accepted' and ack['request_id']==request['request_id']
            print('NORMAL_INSPECTION_ACCEPTED '+ack['job_id'],flush=True)
        async with asyncio.timeout(90):
            while True:
                event=json.loads(await stream.recv())
                if event.get('payload',{}).get('request_id')==request['request_id']:break
        save('event.json',event)
        assert event['event_type']=='surrogate.completed' and event['payload']['job_id']==ack['job_id']
        assert event['payload']['response']['status']=='succeeded'
    events=get('/api/v1/events?run_id='+run_id+'&after_sequence=0',token)['events']
    saved=next(e for e in events if e['event_id']==event['event_id'])
    original=saved['payload']['input_payload']['provenance']['inspection_result']
    assert original==record,'DB replay changed original measurements or verdict'
    assert not any('diagnosis' in e['event_type'] or 'correction' in e['event_type'] or 'tcad' in e['event_type'] for e in events)
    save('db-replayed.json',saved)
    job=get('/api/v1/jobs/'+ack['job_id'],token);save('job.json',job)
    summary=dict(request_id=request['request_id'],run_id=run_id,job_id=ack['job_id'],event_id=event['event_id'],sequence=event['sequence'],
        original_inspection_result=original,original_values_and_ok_verdict_db_replayed=True,diagnosis_requested=False,correction_candidate=False,
        gateway_job_status=job['status'],simulation_only=True,unity_runtime_network_tested=False)
    save('summary.json',summary);save('active.json',dict(request_id=request['request_id'],run_id=run_id,state='db_replayed'))
    print('NORMAL_ORIGINAL_VALUES_AND_OK_DB_REPLAY_OK',flush=True)
if __name__=='__main__':
    try:asyncio.run(run())
    except Exception as e:
        save('failure.json',dict(error=type(e).__name__,detail=str(e)))
        print('NORMAL_INSPECTION_FAILED '+type(e).__name__+': '+str(e),flush=True)
        raise SystemExit(1)
