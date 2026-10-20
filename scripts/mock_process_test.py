"""One-PC real ROS/HTTP/WS + Aiven mock acceptance runner (WSL, sourced ROS)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import httpx
import psycopg
from psycopg.conninfo import make_conninfo
from websockets.sync.client import connect
from event_gateway.config import Settings, _read_dotenv
from event_gateway.migrate import apply_migrations

ROOT=Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def main():
    parser=argparse.ArgumentParser(description='전체 mock 공정: 실제 ROS/HTTP/WS 및 Aiven')
    parser.add_argument('--timeout',type=float,default=180)
    parser.add_argument('--ros-profile')
    args=parser.parse_args()
    os.chdir(ROOT)
    settings=Settings.load(ROOT/'.env')
    env=_read_dotenv(ROOT/'.env') | dict(os.environ)
    run_id=str(uuid4());prefix='fab_test_'+run_id[:8];schema='test_e2e_'+uuid4().hex
    output=ROOT/'data'/'mock-e2e'/run_id;output.mkdir(parents=True)
    db_url=settings.test_database_url or settings.database_url
    with psycopg.connect(db_url,autocommit=True) as db:db.execute(f'CREATE SCHEMA "{schema}"')
    dsn=make_conninfo(db_url,options=f'-c search_path={schema}')
    with psycopg.connect(dsn,autocommit=True) as db:apply_migrations(db,ROOT/'database/migrations')
    api_port,ml_port,tcad_port=port(),port(),port()
    token=secrets.token_urlsafe(24);approval=secrets.token_urlsafe(24)
    env.update(DATABASE_URL=dsn,TEST_DATABASE_URL=dsn,TCAD_MODE='mock',UNITY_MODE='mock',
               AOI_MODE='mock',AOI_MOCK_DEFECT='bend',CAMERA_MODE='mock',SURROGATE_MODE='mock',
               CORRECTION_TARGET='unity',GATEWAY_HOST='127.0.0.1',GATEWAY_PORT=str(api_port),
               TCAD_BIND_HOST='127.0.0.1',TCAD_BIND_PORT=str(tcad_port),TCAD_MOCK_SCENARIO='pass',
               TCAD_MOCK_URL=f'http://127.0.0.1:{tcad_port}',TCAD_POLL_INTERVAL_SECONDS='.2',
               SURROGATE_BIND_PORT=str(ml_port),SURROGATE_MOCK_URL=f'http://127.0.0.1:{ml_port}',
               SURROGATE_RUNTIME_DB=str(output/'ml.sqlite'),AOI_RUNTIME_DB=str(output/'aoi.sqlite'),
               AOI_RESULT_DIR=str(output/'aoi'),AOI_IMAGE_DIR=str(ROOT/'jetson_ws/images'),
               CAMERA_FIXTURE_PATH=str(ROOT/'jetson_ws/images/test_aoi_mosfet1.jpg'),
               TCAD_MOCK_DB_PATH=str(output/'tcad.sqlite'),UNITY_MOCK_DB_PATH=str(output/'unity.sqlite'),
               UNITY_GATEWAY_COMMAND_WS_URL=f'ws://127.0.0.1:{api_port}/api/v1/commands',
               UNITY_API_TOKEN=token,APPROVAL_TOKEN=approval,APPROVAL_OPERATOR='mock-test-operator',
               ROS_COMMAND_KEY=secrets.token_urlsafe(24),ROS_DOMAIN_ID=env.get('ROS_DOMAIN_ID','0'),
               ROS_EVENT_TOPIC=f'/{prefix}/events',ROS_EVENT_ACK_TOPIC=f'/{prefix}/acks',
               ROS_INFERENCE_REQUEST_TOPIC=f'/{prefix}/aoi',ROS_SURROGATE_REQUEST_TOPIC=f'/{prefix}/ml',
               ROS_COMMAND_TOPIC=f'/{prefix}/legacy_commands',UNITY_MOCK_DUPLICATE_ACK='true',
               PYTHONUNBUFFERED='1')
    profile=args.ros_profile or env.get('ROS_TEST_PROFILE') or env.get('FASTRTPS_DEFAULT_PROFILES_FILE')
    if profile:
        if not Path(profile).is_file():raise ValueError('ROS profile file missing')
        env['FASTRTPS_DEFAULT_PROFILES_FILE']=profile
    env['PYTHONPATH']=str(ROOT/'services/event_gateway/src')+':'+str(ROOT/'jetson_ws/src/fab_virtual_lot')+':'+os.environ.get('PYTHONPATH','')
    processes=[];handles=[]
    def start(name,arguments):
        log=(output/(name+'.log')).open('w',encoding='utf-8');handles.append(log)
        process=subprocess.Popen([sys.executable,'-u',*arguments],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        processes.append((name,process))
    def alive():
        failed=[name for name,p in processes if p.poll() is not None]
        if failed:raise RuntimeError('service stopped: '+','.join(failed))
    report={'run_id':run_id,'schema':schema,'status':'running','output_dir':str(output)}
    started=time.monotonic()
    try:
        probe_args=[sys.executable,str(ROOT/'scripts/ros_discovery_probe.py'),'--simple',
                    '--domain',env['ROS_DOMAIN_ID']]
        if profile:probe_args+=['--profile',profile]
        probe=subprocess.run(probe_args,env=env,cwd=ROOT,capture_output=True,text=True,timeout=30)
        report['ros_preflight']=json.loads(probe.stdout.strip())
        if probe.returncode==0:print('ROS preflight passed',flush=True)
        else:print('ROS preflight warning; continuing to the service-level acceptance test',flush=True)
        for name,module in [('tcad','mock_tcad.app'),('ml_service','mock_surrogate.app'),
                            ('api','event_gateway.app'),('verification','event_gateway.verification_worker'),
                            ('bridge','event_gateway.ros_adapter'),('aoi_worker','fab_virtual_lot.aoi_worker'),
                            ('ml_worker','fab_virtual_lot.surrogate_worker')]:start(name,['-m',module])
        start('unity_peer',[str(ROOT/'tools/mock_unity/peer.py'),'--run-id',run_id])
        base=f'http://127.0.0.1:{api_port}'
        with httpx.Client(timeout=15) as client:
            for _ in range(100):
                alive()
                try:
                    if client.get(base+'/health/live').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.2)
            else:raise RuntimeError('Gateway startup timeout')
            headers={'x-unity-token':token}
            common={'run_id':run_id,'lot_id':'MOCK-LOT-1','stage_attempt':1}
            requests=[('/api/v1/inspection-jobs',{**common,'request_id':str(uuid4()),'unit_id':'AOI-1',
                       'fixture_name':'test_aoi_mosfet1.jpg'})]
            for scenario in ('normal','anomaly','missing_candidate','failed'):
                requests.append(('/api/v1/surrogate-jobs',{**common,'request_id':str(uuid4()),
                    'unit_id':'ML-'+scenario,'input_payload':{'scenario':scenario},'model_contract_version':'fab-ml-v1'}))
            def submit(item):
                response=client.post(base+item[0],json=item[1],headers=headers);response.raise_for_status()
                return response.json()
            with ThreadPoolExecutor(max_workers=5) as pool:jobs=list(pool.map(submit,requests))
            assert submit(requests[1])['job_id']==jobs[1]['job_id']
            report['jobs']=jobs
            print(json.dumps({'run_id':run_id,'schema':schema,'jobs':jobs}),flush=True)
            seen=[];approved=False;applied=False;last_progress=0
            with connect(f'ws://127.0.0.1:{api_port}/api/v1/stream?run_id={run_id}',open_timeout=10) as ws:
                deadline=time.monotonic()+args.timeout
                while time.monotonic()<deadline:
                    alive()
                    try:event=json.loads(ws.recv(timeout=1))
                    except TimeoutError:
                        if time.monotonic()-last_progress>15:
                            print('waiting for ROS/DB/WS events; received='+str(len(seen)),flush=True);last_progress=time.monotonic()
                        continue
                    seen.append(event)
                    print(event['event_type'],event['sequence'],flush=True)
                    if event['event_type']=='correction.verified' and not approved:
                        # Explicit synthetic test approval, only this forced mock run.
                        response=client.post(base+'/api/v1/proposals/'+event['payload']['proposal_id']+'/approval',
                            headers={'x-approval-token':approval},json={'approved_by':'mock-test-operator','effective_from_lot':'MOCK-LOT-2'})
                        response.raise_for_status();approved=True
                    if event['event_type']=='correction.applied':applied=True
                    types=[e['event_type'] for e in seen]
                    if applied and types.count('surrogate.completed')==4 and 'aoi.inspection.completed' in types:break
                else:raise TimeoutError('full pipeline deadline exceeded; inspect service logs')
            with psycopg.connect(dsn,autocommit=True) as db:
                assert db.execute('SELECT count(*) FROM verification_jobs').fetchone()==(1,)
                assert db.execute("SELECT count(*) FROM commands WHERE status='applied' AND delivery_target='unity'").fetchone()==(1,)
                assert db.execute('SELECT count(*) FROM aoi_image_artifacts').fetchone()==(2,)
                assert db.execute('SELECT count(*) FROM surrogate_results').fetchone()==(4,)
                outcomes=db.execute('SELECT routing_status,count(*) FROM surrogate_results GROUP BY routing_status').fetchall()
                assert dict(outcomes)=={'normal':1,'verification_queued':1,'review_required':1,'failed':1}
                final_jobs=db.execute('SELECT job_id,status,result_event_id FROM inference_jobs ORDER BY created_at').fetchall()
                report['jobs']=[{'job_id':str(job),'status':status,'result_event_id':str(event)} for job,status,event in final_jobs]
            for filename,expected in [('aoi.sqlite',1),('ml.sqlite',4)]:
                for _ in range(30):
                    with sqlite3.connect(output/filename) as db:
                        count=db.execute('SELECT count(*) FROM pending WHERE delivered_sequence>0').fetchone()[0]
                    if count==expected:break
                    time.sleep(.5)
                assert count==expected,filename+' commit ACK missing'
            with sqlite3.connect(output/'unity.sqlite') as db:
                assert db.execute('SELECT count(*) FROM applied').fetchone()==(1,)
            replay=client.get(base+'/api/v1/events',params={'run_id':run_id}).json()['events']
            assert {e['event_id'] for e in seen}<={e['event_id'] for e in replay}
            report.update(status='passed',elapsed_seconds=round(time.monotonic()-started,2),
                          events=[{'type':e['event_type'],'sequence':e['sequence']} for e in seen],
                          checks=['AOI ROS/JPG/DB/ACK','ML normal/anomaly/missing/failed','TCAD HTTP exactly one job',
                                  'human approval fixture','Unity WS apply/duplicate ACK','HTTP/WS replay'])
            print(json.dumps(report,ensure_ascii=False),flush=True)
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__)
        print(json.dumps({'status':'failed','error_type':type(exc).__name__,'logs':str(output)}),flush=True)
        raise
    finally:
        for _,process in reversed(processes):
            if process.poll() is None:process.terminate()
        for _,process in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for handle in handles:handle.close()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0

if __name__=='__main__':raise SystemExit(main())
