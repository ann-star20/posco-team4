import hashlib
import time
import unittest
import tempfile
import os
from unittest.mock import patch
import json
import sys
from pathlib import Path
from threading import Thread
from uuid import uuid4

from unity_aoi_camera_server import validate_request, validate_image, make_handler, resolve_model_paths, configure, stop_previous_camera_server

JPEG = bytes([255,216,255,192,0,17,8,0,16,0,32,3,1,17,0,2,17,0,3,17,0,255,217])
def request():
    return dict(type='aoi.inspection.requested', schema_version=1, input_source='unity_camera',
                request_id=str(uuid4()), job_id=str(uuid4()), run_id=str(uuid4()), lot_id='LOT-CAMERA',
                unit_id='MOSFET-CAMERA', attempt=1, api_token='dummy-test-token', fixture_name='unity-camera.jpg',
                input_image=dict(mime_type='image/jpeg', byte_length=len(JPEG), width=32, height=16,
                                 sha256=hashlib.sha256(JPEG).hexdigest(), sampled_at_ms=int(time.time()*1000)))
class LiveTests(unittest.TestCase):
    def test_replace_only_uploaded_python_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for pid,command in ((101,b'python3\0/home/jetson/unity_aoi_camera_123456abcdef.py\0'),(102,b'python3\0aoi_worker.py\0'),(103,b'bash\0unity_aoi_camera_123456abcdef.py\0'),(104,b'python3\0unity_aoi_camera_wrong.py\0')):
                folder=root/str(pid);folder.mkdir();(folder/'cmdline').write_bytes(command)
            with patch('unity_aoi_camera_server.os.getuid',return_value=root.stat().st_uid,create=True), patch('unity_aoi_camera_server.os.getpid',return_value=9999), patch('unity_aoi_camera_server.os.kill') as kill, patch('unity_aoi_camera_server.socket.socket') as sock:
                sock.return_value.__enter__.return_value.connect_ex.return_value=1
                stop_previous_camera_server(root)
                self.assertEqual(kill.call_count,1)
                self.assertEqual(kill.call_args.args[0],101)
    def test_startup_paths_override_env_with_best_and_last_present(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            root=Path(directory)/'jetson_ws';root.mkdir()
            selected={}
            for role in ('PART','DEFECT'):
                folder=root.parent/'aoi/models'/role.lower()/'weights';folder.mkdir(parents=True)
                for name in ('best.pt','last.pt'):(folder/name).touch()
                selected['AOI_'+role+'_MODEL_FILE']=str(folder/'best.pt')
            (root/'.env').write_text('AOI_PART_MODEL_FILE=wrong.pt\nAOI_DEFECT_MODEL_FILE=wrong.pt\n')
            with patch('unity_aoi_camera_server.Path.home',return_value=root.parent):configure(root,selected)
            for key,value in selected.items():self.assertEqual(os.environ[key],str(Path(value).resolve()))
            with self.assertRaises(RuntimeError):configure(root,{'AOI_PART_MODEL_FILE':str(root/'absent.pt')})
    def test_model_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);part=root/'models/part/best.pt';defect=root/'models/defect/best.pt'
            for path in (part,defect):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test-placeholder')
            env={};resolve_model_paths(env,[root])
            self.assertEqual(env['AOI_PART_MODEL_FILE'],str(part.resolve()))
            self.assertEqual(env['AOI_DEFECT_MODEL_FILE'],str(defect.resolve()))
            extra=root/'models/old_part.pt';extra.write_bytes(b'test-placeholder')
            with self.assertRaises(RuntimeError):resolve_model_paths({},[root])
    def test_explicit_model_configuration_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);one=root/'one.pt';two=root/'two.pt'
            one.touch();two.touch();env={'AOI_PART_MODEL_FILE':str(one),'AOI_DEFECT_MODEL_FILE':str(two)}
            resolve_model_paths(env,[root]);self.assertEqual(env['AOI_PART_MODEL_FILE'],str(one.resolve()))
    def test_websocket_transport(self):
        sys.path.insert(0,str(Path(__file__).parents[1]/'FabSocket/.deps'))
        from websockets.sync.server import serve
        from websockets.sync.client import connect
        decoded=type('Frame',(),{'shape':(16,32,3)})()
        class Service:
            def inspect(self,q):return {'type':'aoi.inspection.completed','verdict':'review','request_id':q['request_id']},JPEG
        handler=make_handler('dummy-test-token',lambda frame:Service(),lambda data:decoded)
        with serve(handler,'127.0.0.1',0,max_size=8*1024*1024) as server:
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with connect('ws://127.0.0.1:%s/aoi'%server.socket.getsockname()[1]) as client:
                    q=request();client.send(json.dumps(q));client.send(JPEG)
                    result=json.loads(client.recv(timeout=5));photo=client.recv(timeout=5)
                    self.assertEqual(result['request_id'],q['request_id']);self.assertEqual(photo,JPEG)
                    self.assertEqual(result['input_image_sha256'],hashlib.sha256(JPEG).hexdigest())
            finally:server.shutdown();thread.join(timeout=5)
    def test_wire(self):
        q=request();seen=[]
        class Socket:
            request=type('Request',(),{'path':'/aoi'})()
            def __init__(self):self.frames=[__import__('json').dumps(q),JPEG];self.sent=[]
            def recv(self,timeout):return self.frames.pop(0)
            def send(self,value):self.sent.append(value)
        class Service:
            def inspect(self,wire):
                self_seen=wire['job_id'];seen.append(self_seen)
                return {'type':'aoi.inspection.completed','verdict':'review'},JPEG
        decoded=type('Frame',(),{'shape':(16,32,3)})()
        socket=Socket()
        make_handler('dummy-test-token',lambda frame:Service(),lambda data:decoded)(socket)
        result=__import__('json').loads(socket.sent[0])
        self.assertEqual(seen,[q['job_id']]);self.assertEqual(socket.sent[1],JPEG)
        self.assertEqual(result['input_image_sha256'],q['input_image']['sha256'])
        self.assertEqual(result['input_source'],'unity_camera')
        self.assertNotIn('dummy-test-token',socket.sent[0])
    def test_current_frame(self):
        q=request();validate_request(q,'dummy-test-token');validate_image(q,JPEG)
    def test_auth_before_image(self):
        with self.assertRaises(ValueError):validate_request(request(),'wrong-token')
    def test_no_fixture_fallback(self):
        q=request();q['input_source']='fixture'
        with self.assertRaises(ValueError):validate_request(q,'dummy-test-token')
    def test_integrity(self):
        with self.assertRaises(ValueError):validate_image(request(),JPEG[:-1]+b'x')
    def test_dimensions(self):
        q=request();q['input_image']['width']=4000
        with self.assertRaises(ValueError):validate_image(q,JPEG)
    def test_size(self):
        q=request();q['input_image']['byte_length']=100000000
        with self.assertRaises(ValueError):validate_request(q,'dummy-test-token')
    def test_old_frame(self):
        q=request();q['input_image']['sampled_at_ms']-=600000
        with self.assertRaises(ValueError):validate_request(q,'dummy-test-token')
    def test_schema_and_attempt(self):
        q=request();q['schema_version']=2
        with self.assertRaises(ValueError):validate_request(q,'dummy-test-token')
        q=request();q['attempt']=0
        with self.assertRaises(ValueError):validate_request(q,'dummy-test-token')
if __name__=='__main__':unittest.main()
