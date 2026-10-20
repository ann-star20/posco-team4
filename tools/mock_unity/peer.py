"""Durable mock Unity application peer. No automatic human approval."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed


def apply(path, command):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    body=json.dumps(command,sort_keys=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS applied(command_id TEXT PRIMARY KEY,body TEXT NOT NULL)')
        row=db.execute('SELECT body FROM applied WHERE command_id=?',(command['command_id'],)).fetchone()
        if row and row[0]!=body:raise ValueError('command content conflict')
        db.execute('INSERT OR IGNORE INTO applied VALUES (?,?)',(command['command_id'],body))
    return {'type':'correction.applied','command_id':command['command_id'],
            'run_id':command['run_id'],'effective_from_lot':command['effective_from_lot'],
            'x_applied':command['x_candidate']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    from event_gateway.config import _read_dotenv
    env=_read_dotenv(Path('.env')) | dict(os.environ)
    if env.get('UNITY_MODE','mock')!='mock':raise ValueError('mock peer requires UNITY_MODE=mock')
    base=env.get('UNITY_GATEWAY_COMMAND_WS_URL','ws://127.0.0.1:8000/api/v1/commands')
    token=env.get('UNITY_API_TOKEN','')
    if not token:raise ValueError('UNITY_API_TOKEN required')
    path=env.get('UNITY_MOCK_DB_PATH','data/mock-unity.sqlite')
    while True:
        try:
            with connect(base+'?run_id='+args.run_id,additional_headers={'x-unity-token':token}) as ws:
                for raw in ws:
                    body=json.loads(raw)
                    if body.get('type')=='correction.command':
                        ack=json.dumps(apply(path,body));ws.send(ack)
                        if env.get('UNITY_MOCK_DUPLICATE_ACK')=='true':ws.send(ack)
                    elif body.get('type')=='application.ack':print(json.dumps(body),flush=True)
        except (OSError,TimeoutError,ConnectionClosed):time.sleep(1)

if __name__=='__main__':main()
