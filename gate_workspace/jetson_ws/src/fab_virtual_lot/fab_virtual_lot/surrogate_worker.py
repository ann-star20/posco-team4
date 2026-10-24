"""Jetson ROS adapter: persistent jobs -> local model HTTP -> persistent results."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid5

import httpx
from .outbox import Outbox
from .ml_client import ModelHttpClient


class SingleFlightExecutor:
    """Run at most one background operation without blocking the caller."""

    def __init__(self, thread_name, on_error=None):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_name)
        self.on_error = on_error or (lambda _error: None)
        self.lock = Lock()
        self.future = None
        self.closed = False

    @property
    def busy(self):
        with self.lock:
            return self.future is not None and not self.future.done()

    def submit(self, operation):
        with self.lock:
            if self.closed or (self.future is not None and not self.future.done()):
                return False
            self.future = self.executor.submit(operation)
            self.future.add_done_callback(self._finished)
            return True

    def _finished(self, future):
        try:
            error = future.exception()
        except Exception as exc:
            error = exc
        if error is not None:
            self.on_error(error)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=False)


class SurrogateClient(ModelHttpClient):
    def __init__(self, mode, url, http):
        super().__init__(mode, url, '/api/v1/predict', http)


class SurrogateRuntime:
    def __init__(self, path, task_type='surrogate', event_type='surrogate.completed',
                 source='jetson.surrogate'):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.outbox = Outbox(path)
        self.lock = self.outbox.lock
        self.db = self.outbox.connection
        self.db.execute('CREATE TABLE IF NOT EXISTS ml_inbox(job_id TEXT PRIMARY KEY, body TEXT NOT NULL,status TEXT NOT NULL DEFAULT \'queued\')')
        self.db.commit()
        self.task_type, self.event_type, self.source = task_type, event_type, source

    def accept(self, request):
        for key in ('job_id','request_id','run_id'): UUID(request[key])
        if request.get('task_type') != self.task_type: raise ValueError('invalid task')
        body = json.dumps(request, sort_keys=True)
        with self.lock, self.db:
            row = self.db.execute('SELECT body FROM ml_inbox WHERE job_id=?',(request['job_id'],)).fetchone()
            if row and row[0] != body: raise ValueError('job content conflict')
            self.db.execute('INSERT OR IGNORE INTO ml_inbox(job_id,body) VALUES (?,?)',(request['job_id'],body))

    def process_next(self, infer):
        with self.lock, self.db:
            row=self.db.execute("SELECT job_id,body FROM ml_inbox WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                self.db.execute("UPDATE ml_inbox SET status='running' WHERE job_id=?",(row[0],))
        if not row: return
        job_id,body=row; request=json.loads(body)
        try:
            response=infer(request)
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500:
                # Contract-level rejection (bad request/auth/unsupported version): retrying the
                # same body forever only blocks every later job behind it in this FIFO queue.
                response={'request_id':request['request_id'],'job_id':request['job_id'],
                          'model_contract_version':request.get('model_contract_version'),
                          'result_origin':request.get('surrogate_mode',request.get('diagnosis_mode')),
                          'status':'failed','anomaly_detected':None,'result_payload':None,
                          'error_code':'CONTRACT_REJECTED',
                          'error_message':f'model service rejected request: HTTP {exc.response.status_code}'}
            else:
                with self.lock, self.db:
                    self.db.execute("UPDATE ml_inbox SET status='queued' WHERE job_id=?",(job_id,))
                raise
        except Exception:
            with self.lock, self.db:
                self.db.execute("UPDATE ml_inbox SET status='queued' WHERE job_id=?",(job_id,))
            raise
        event_id=str(uuid5(UUID(job_id),self.event_type+':'+str(request['attempt'])))
        event={'schema_version':1,'event_id':event_id,'run_id':request['run_id'],
               'event_type':self.event_type,'source':self.source,'severity':'info',
               'occurred_at':datetime.now(timezone.utc).isoformat(),
               'payload':{**request,'response':response}}
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO pending(event_id,run_id,body) VALUES (?,?,?)',
                            (event_id,request['run_id'],json.dumps(event,sort_keys=True)))
            self.db.execute("UPDATE ml_inbox SET status='completed' WHERE job_id=?",(job_id,))
        return event

    def pending_events(self):
        with self.lock:
            return self.db.execute('SELECT event_id,run_id,body FROM pending WHERE delivered_sequence IS NULL ORDER BY rowid LIMIT 100').fetchall()

    def ack(self,event_id,run_id,sequence):
        return self.outbox.ack(UUID(event_id),UUID(run_id),sequence)

    def close(self): self.outbox.close()


def main():
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    runtime=SurrogateRuntime(Path(os.environ.get('SURROGATE_RUNTIME_DB','data/surrogate.sqlite')))
    mode=os.environ.get('SURROGATE_MODE','mock')
    if mode not in {'mock','prod'}:raise ValueError('invalid SURROGATE_MODE')
    url=os.environ.get('SURROGATE_PROD_URL' if mode=='prod' else 'SURROGATE_MOCK_URL',
                       '' if mode=='prod' else 'http://127.0.0.1:8300')
    if not url:raise ValueError('model URL is required')
    # Endpoint comes from the Jetson environment, never from an untrusted ROS URL.
    client=httpx.Client(timeout=float(os.environ.get('SURROGATE_TIMEOUT_SECONDS','15')))
    infer=SurrogateClient(mode,url,client)
    rclpy.init()
    class Worker(Node):
        def __init__(self):
            super().__init__('fab_surrogate_worker')
            self.pub=self.create_publisher(String,os.environ.get('ROS_EVENT_TOPIC','/fab/events'),10)
            self.create_subscription(String,os.environ.get('ROS_SURROGATE_REQUEST_TOPIC','/fab/surrogate_requests'),self.receive,10)
            self.create_subscription(String,os.environ.get('ROS_EVENT_ACK_TOPIC','/fab/event_acks'),self.receipt,10)
            self.create_timer(1.,self.tick)
            self.runner=SingleFlightExecutor('surrogate-cpu',self.background_error)
        def background_error(self,exc):
            self.get_logger().warning(f'model unavailable or invalid response; durable request retained: {exc!r}')
        def receive(self,msg):
            try:runtime.accept(json.loads(msg.data))
            except (ValueError,KeyError,TypeError):self.get_logger().error('invalid ML request')
        def receipt(self,msg):
            try:
                ack=json.loads(msg.data)
                if ack.get('status')=='committed':runtime.ack(ack['event_id'],ack['run_id'],ack['sequence'])
                elif ack.get('status')=='dead_lettered':runtime.outbox.dead_letter(UUID(ack['event_id']),UUID(ack['run_id']))
            except (ValueError,KeyError,TypeError):self.get_logger().error('invalid ML ACK')
        def tick(self):
            self.runner.submit(lambda:runtime.process_next(infer))
            for _,_,body in runtime.pending_events():
                msg=String();msg.data=body;self.pub.publish(msg)
    node=Worker()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        node.runner.close();node.destroy_node();runtime.close();client.close()
        if rclpy.ok():rclpy.shutdown()

if __name__=='__main__':main()
