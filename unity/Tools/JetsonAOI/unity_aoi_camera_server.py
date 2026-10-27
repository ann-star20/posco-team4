"""Upload-only camera adapter; original Jetson AOI package is not modified."""
from collections import OrderedDict
from dataclasses import replace
import hashlib
import errno
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import sys
from threading import Lock, BoundedSemaphore
import time
from uuid import UUID

MAX_BYTES = 8 * 1024 * 1024

def stop_previous_camera_server(proc_root=Path('/proc')):
    # Only our uploaded adapters, owned by this user, may be replaced.
    targets=[]
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():continue
        try:
            if entry.stat().st_uid!=os.getuid():continue
            args=(entry/'cmdline').read_bytes().split(b'\0')
            if not args or not Path(os.fsdecode(args[0])).name.startswith('python'):continue
            if not any(re.fullmatch(r'unity_aoi_camera_[0-9a-f]{12}\.py',Path(os.fsdecode(arg)).name) for arg in args[1:3]):continue
            targets.append(int(entry.name))
        except (OSError,ValueError):continue
    for pid in targets:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    if targets:
        print('Stopping previous Unity camera AOI adapter; original AOI services are not changed.',flush=True)
        for _ in range(50):
            with socket.socket() as probe:
                if probe.connect_ex(('192.168.213.167',8401))!=0:return
            time.sleep(0.1)

def validate_request(q, token):
    if not token or not hmac.compare_digest(str(q.get('api_token', '')), token):
        raise ValueError('authentication_failed')
    if q.get('type') != 'aoi.inspection.requested' or q.get('schema_version') != 1 or q.get('input_source') != 'unity_camera':
        raise ValueError('camera_request_required')
    for key in ('request_id', 'job_id', 'run_id'): UUID(q[key])
    if type(q.get('attempt')) is not int or q['attempt'] < 1: raise ValueError('invalid_attempt')
    for key in ('lot_id', 'unit_id'):
        if not isinstance(q.get(key), str) or not 1 <= len(q[key]) <= 128: raise ValueError('invalid_identity')
    meta = q.get('input_image', {})
    if meta.get('mime_type') != 'image/jpeg' or type(meta.get('byte_length')) is not int or not 4 <= meta['byte_length'] <= MAX_BYTES:
        raise ValueError('invalid_image_size')
    if not re.fullmatch('[a-fA-F0-9]{64}', str(meta.get('sha256', ''))): raise ValueError('invalid_image_hash')
    for key in ('width', 'height'):
        if type(meta.get(key)) is not int or not 1 <= meta[key] <= 4096: raise ValueError('invalid_dimensions')
    if type(meta.get('sampled_at_ms')) is not int or abs(time.time()*1000-meta['sampled_at_ms']) > 120000:
        raise ValueError('frame_time_invalid')

def validate_image(q, image):
    meta=q['input_image']
    if not isinstance(image, bytes) or len(image) != meta['byte_length'] or len(image) > MAX_BYTES or image[:2] != b'\xff\xd8' or image[-2:] != b'\xff\xd9':
        raise ValueError('image_integrity_failed')
    if not hmac.compare_digest(hashlib.sha256(image).hexdigest(), meta['sha256'].lower()): raise ValueError('image_integrity_failed')
    i=2
    while i+3 < len(image):
        if image[i] != 255: break
        while i < len(image) and image[i] == 255:i+=1
        if i >= len(image):break
        marker=image[i];i+=1
        if marker in (217,218):break
        if marker == 1 or 208 <= marker <= 215:continue
        if i+2 > len(image):break
        size=int.from_bytes(image[i:i+2],'big')
        if size < 2 or i+size > len(image):break
        if 192 <= marker <= 207 and marker not in (196,200,204):
            if size < 8:break
            height=int.from_bytes(image[i+3:i+5],'big');width=int.from_bytes(image[i+5:i+7],'big')
            if (width,height) != (meta['width'],meta['height']):raise ValueError('image_dimensions_mismatch')
            return
        i+=size
    raise ValueError('invalid_jpeg')

def resolve_model_paths(env, roots):
    keys={'AOI_PART_MODEL_FILE':('part','component','부품'), 'AOI_DEFECT_MODEL_FILE':('defect','damage','crash','불량')}
    missing=[key for key in keys if not env.get(key) or not Path(env[key]).is_file()]
    if missing:
        files=set();skip={'.git','.cache','.local','site-packages','node_modules','venv','.venv','build','install','log','result','results'}
        for root in roots:
            if not root.is_dir():continue
            for directory,folders,names in os.walk(root):
                depth=len(Path(directory).relative_to(root).parts)
                folders[:]=[name for name in folders if name not in skip and not name.startswith('.') and depth<7]
                for name in names:
                    if name.lower().endswith('.pt'):files.add((Path(directory)/name).resolve())
        candidates={key:sorted(str(path) for path in files if any(word in str(path).lower() for word in words)) for key,words in keys.items()}
        if any(len(candidates[key])!=1 for key in missing):
            print('AOI_MODEL_CANDIDATES '+json.dumps({'by_role':candidates,'all_weights':sorted(str(p) for p in files)[:80]},ensure_ascii=False),flush=True)
            raise RuntimeError('Model configuration missing: '+','.join(missing))
        for key in missing:env[key]=candidates[key][0]
    if Path(env['AOI_PART_MODEL_FILE']).resolve()==Path(env['AOI_DEFECT_MODEL_FILE']).resolve():raise RuntimeError('Model roles must use different files')
    for key in keys:env[key]=str(Path(env[key]).resolve())

def configure(root, model_paths=None):
    # Parse only AOI settings; never source shell files or print credentials.
    for folder in (root.parent,root):
        for name in ('.env','.env.jetson','.env.local'):
            path=folder/name
            if not path.is_file():continue
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                line=line.strip().removeprefix('export ')
                if not line or line.startswith('#') or '=' not in line:continue
                key,value=line.split('=',1);key=key.strip()
                if not key.startswith('AOI_') and key!='JETSON_PROJECT_PATH':continue
                try:fields=shlex.split(value,comments=True)
                except ValueError:continue
                if len(fields)==1:os.environ[key]=fields[0]
    if model_paths is not None:
        allowed={'AOI_PART_MODEL_FILE','AOI_DEFECT_MODEL_FILE'}
        if not isinstance(model_paths,dict) or set(model_paths)-allowed:
            raise RuntimeError('Model path settings invalid')
        for key,value in model_paths.items():
            if not isinstance(value,str) or not value.strip():raise RuntimeError('Model path settings invalid')
            if not Path(value).is_file():raise RuntimeError('Model selected file missing: '+key)
            os.environ[key]=value
    for key in ('AOI_PART_MODEL_FILE','AOI_DEFECT_MODEL_FILE'):
        value=os.environ.get(key,'')
        path=Path(os.path.expandvars(value)).expanduser()
        if value and not path.is_absolute():path=root/path
        if value:os.environ[key]=str(path.resolve())
    home=Path.home()
    resolve_model_paths(os.environ,[root.parent,home/'models',home/'Desktop',home/'Downloads',home/'Documents'])
    os.environ['AOI_MODE']='prod'

def make_handler(token, factory, decode):
    model_lock=Lock();slots=BoundedSemaphore(2);jobs=OrderedDict()
    def handle(socket):
        if not slots.acquire(blocking=False):socket.close(1013,'Server busy');return
        try:
            if socket.request.path != '/aoi':socket.close(1008,'Invalid path');return
            raw=socket.recv(timeout=15)
            if not isinstance(raw,str) or len(raw)>16384:raise ValueError('invalid_request')
            q=json.loads(raw);validate_request(q,token)
            image=socket.recv(timeout=15);validate_image(q,image)
            frame=decode(image)
            if frame is None or frame.shape[:2] != (q['input_image']['height'],q['input_image']['width']):raise ValueError('image_decode_failed')
            with model_lock:
                job=(q['job_id'],q['attempt']);digest=q['input_image']['sha256']
                if job in jobs and jobs[job]!=digest:raise ValueError('job_image_conflict')
                jobs[job]=digest
                while len(jobs)>1024:jobs.popitem(last=False)
                q['fixture_name']='unity-camera.jpg'
                metadata,annotated=factory(frame).inspect(q)
            metadata['input_source']='unity_camera';metadata['input_image_sha256']=digest
            socket.send(json.dumps(metadata,ensure_ascii=False,separators=(',',':')));socket.send(annotated)
        except Exception as error:
            # External exception text and request bodies may contain secrets.
            allowed={'authentication_failed','frame_time_invalid','job_image_conflict','image_integrity_failed','image_decode_failed'}
            code=str(error) if isinstance(error,ValueError) and str(error) in allowed else 'camera_inspection_failed'
            try:socket.send(json.dumps({'type':'aoi.inspection.failed','schema_version':1,'error_code':code}))
            except Exception:pass
        finally:slots.release()
    return handle

def main():
    if '--replace-existing' in sys.argv:stop_previous_camera_server()
    root=Path.home()/'project/smart_factory/jetson_ws'
    sys.path.insert(0,str(root/'src/fab_virtual_lot'))
    settings=json.loads(sys.stdin.readline())
    token=settings.get('token','')
    if not isinstance(token,str) or len(token)<32:raise RuntimeError('Session token missing')
    configure(root,settings.get('model_paths'))
    import cv2
    import numpy as np
    from websockets.sync.server import serve
    from fab_virtual_lot.aoi_pipeline import AoiConfig
    from fab_virtual_lot.aoi_unity import AoiUnityService
    from fab_virtual_lot.aoi_worker import make_models
    config=replace(AoiConfig.from_env(),result_dir=Path.home()/'unity-aoi-camera-results',mode='prod')
    models=make_models(config)
    expected=({0:'body',1:'lead',2:'tab'},{0:'crash',1:'bend'})
    for model,labels in zip(models,expected):
        names=model.model.names
        items=names.items() if isinstance(names,dict) else enumerate(names)
        if not names or any(labels.get(int(key))!=str(value).lower() for key,value in items):
            raise RuntimeError('Model class mismatch; engineer model selection required')
    print('AOI real model class mappings checked',flush=True)
    def service_for(frame):
        def capture(q):
            if (config.result_dir/str(UUID(q['job_id']))/str(q['attempt'])/'result.json').exists():raise ValueError('job_image_conflict')
            return frame
        return AoiUnityService(config,capture,*models,token=token,max_image_bytes=MAX_BYTES)
    handler=make_handler(token,service_for,
                         lambda data:cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR))
    with serve(handler,'192.168.213.167',8401,max_size=MAX_BYTES,compression=None,open_timeout=10,close_timeout=3) as server:
        print('UNITY_CAMERA_AOI_READY ws://192.168.213.167:8401/aoi | real models | ROS publishing disabled',flush=True)
        server.serve_forever()

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception as error:
        # Only configuration key names are safe to expose here.
        if isinstance(error,OSError) and error.errno==errno.EADDRINUSE:
            print('Camera AOI port 8401 already in use. Stop the previous camera AOI server with Ctrl+C, then run this launcher again.',flush=True)
        elif isinstance(error,OSError) and error.errno==errno.EADDRNOTAVAIL:
            print('Camera AOI USB address 192.168.213.167 unavailable. Check the Jetson USB network connection.',flush=True)
        elif isinstance(error,RuntimeError) and str(error).startswith('Model '):print(str(error),flush=True)
        else:print('Camera AOI startup failed; check model configuration and dependencies.',flush=True)
        sys.exit(1)
