set -e
cd /home/jetson/project/smart_factory
# Load ROS before Python/environment configuration; do not overwrite any saved files.
if [ -f /opt/ros/humble/setup.bash ]; then . /opt/ros/humble/setup.bash; fi
if [ -f jetson_ws/install/setup.bash ]; then . jetson_ws/install/setup.bash; fi
set -a
if [ -f .env.aoi-unity ]; then . ./.env.aoi-unity; fi
if [ ! -f .env.camera-prod ]; then
  echo 'AOI_START_FAILED: existing .env.camera-prod is missing. Ask the Jetson operator for the real camera configuration.'
  exit 1
fi
. ./.env.camera-prod
set +a
# Session-only camera IP override; existing credentials and server files are preserved.
export AOI_CAMERA_HOST_OVERRIDE=192.168.10.123
export PYTHONPATH="/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"
python3 -u - <<'PY'
import ast
import importlib.util
import re
import signal
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from ipaddress import IPv4Address

def stop(message):
    print('AOI_START_FAILED: '+message, flush=True)
    raise SystemExit(1)

def opened(port):
    # Inspect listeners without opening an unauthenticated WebSocket connection.
    result=subprocess.run(['ss','-H','-ltn','sport = :'+str(port)],capture_output=True,text=True,timeout=5)
    if result.returncode!=0:stop('Cannot inspect listening ports with ss.')
    return bool(result.stdout.strip())

active=[p for p in (8500,8400) if opened(p)]
if active and os.environ.get('AOI_RESTART_EXISTING')!='1':
    print('ALREADY_LISTENING: '+','.join(map(str,active))+'. Use restart-aoi-8500-8400.cmd to apply the new camera IP.',flush=True)
    raise SystemExit(0)
if os.environ.get('CAMERA_MODE')!='prod':stop('CAMERA_MODE must be prod in the existing camera environment.')
for key in ('CAMERA_PREVIEW_TOKEN','AOI_UNITY_TOKEN'):
    if not os.environ.get(key):stop(key+' is missing from the existing environment. Values are not printed.')
if not os.environ.get('CAMERA_SOURCE_URL'):stop('CAMERA_SOURCE_URL is missing.')

def camera_url_for_host(value,host):
    host=str(IPv4Address(host))
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https','rtsp') or not parsed.hostname:
        raise ValueError('Existing camera source is not a network URL.')
    credentials=parsed.netloc.rsplit('@',1)[0]+'@' if '@' in parsed.netloc else ''
    netloc=credentials+host+(':'+str(parsed.port) if parsed.port else '')
    return urlunsplit((parsed.scheme,netloc,parsed.path,parsed.query,parsed.fragment))

try:
    if os.environ.get('AOI_LAPTOP_CAMERA_HOST'):
        host=str(IPv4Address(os.environ['AOI_LAPTOP_CAMERA_HOST']))
        os.environ['CAMERA_SOURCE_URL']='http://'+host+':8080/video'
        print('AOI_LAPTOP_CAMERA: http://'+host+':8080/video (session only)',flush=True)
    else:
        os.environ['CAMERA_SOURCE_URL']=camera_url_for_host(os.environ['CAMERA_SOURCE_URL'],os.environ['AOI_CAMERA_HOST_OVERRIDE'])
except ValueError:
    stop('Camera host override failed. Check the existing camera URL configuration.')
if not os.environ.get('AOI_LAPTOP_CAMERA_HOST'):
    print('AOI_CAMERA_HOST: '+os.environ['AOI_CAMERA_HOST_OVERRIDE']+' (existing protocol, path and credentials preserved)',flush=True)

source=Path('jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py')
if not source.is_file():stop('Existing fab_virtual_lot/aoi_unity.py was not found.')
text=source.read_text()
tree=ast.parse(text)
if not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='main' for n in tree.body):stop('Existing aoi_unity main entry point was not found.')
if 'camera_preview' not in text and 'CameraPreview' not in text:
    stop('Existing aoi_unity.py does not reference the camera preview service. This launcher will not start an old inspection-only server.')
os.environ['AOI_UNITY_WS_HOST']='0.0.0.0'
os.environ['AOI_UNITY_WS_PORT']='8400'
base=Path.cwd()
candidates=[]
# Prefer the existing isolated runtime used by the older working AOI launcher.
for parent in (Path.home(),Path.home()/'project/surrogate_ml_bak',Path.home()/'project/surrogate_ml'):
    for folder in sorted(parent.glob('VirtualFabML_*')):
        candidates.append(folder/'.venv-tabpfn-9.2/bin/python')
if os.environ.get('VIRTUAL_ENV'):candidates.append(Path(os.environ['VIRTUAL_ENV'])/'bin/python')
for parent in (base,base/'jetson_ws',base.parent):
    for folder in sorted(parent.glob('*venv*')):
        candidates.append(folder/'bin/python')
candidates.append(Path(sys.executable))
# Importing ultralytics alone can defer the Matplotlib ABI failure until model loading.
check="import numpy as np;import matplotlib.transforms;import matplotlib._path;import cv2,ultralytics,torch,torchvision;from websockets.sync.server import serve;from fab_virtual_lot.aoi_worker import make_models;import fab_virtual_lot.aoi_unity;torch.from_numpy(np.zeros((1,),dtype=np.float32))"

def select_python(paths,runner):
    for candidate in dict.fromkeys(paths):
        if not candidate.is_file():continue
        print('AOI_PYTHON_CHECK: '+str(candidate),flush=True)
        try:
            probe=runner([str(candidate),'-c',check],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
        except (OSError,subprocess.TimeoutExpired):
            print('AOI_PYTHON_SKIPPED: unavailable or timed out',flush=True);continue
        if probe.returncode==0:return str(candidate)
        print('AOI_PYTHON_SKIPPED: NumPy/Matplotlib/model imports incompatible',flush=True)
    return None

python=select_python(candidates,subprocess.run)
if python is None:stop('No compatible existing NumPy/Matplotlib/AOI runtime found. Send the AOI_PYTHON_CHECK lines; no packages were installed.')
def process_start_stamp(proc):
    # /proc stat field 22; split after the final ')' because process names may contain spaces.
    return proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]

def same_aoi_instance(args,cwd,uid,current_stamp,original_stamp):
    return current_stamp==original_stamp and is_existing_aoi(args,cwd,uid)

def is_existing_aoi(args,cwd,uid):
    return uid==os.getuid() and cwd==base.resolve() and any(args[i:i+2]==['-m','fab_virtual_lot.aoi_unity'] for i in range(len(args)-1))

if active:
    owners=set()
    for port in active:
        result=subprocess.run(['ss','-H','-ltnp','sport = :'+str(port)],capture_output=True,text=True,timeout=5)
        pids=set(map(int,re.findall(r'pid=(\d+)',result.stdout)))
        if result.returncode or len(pids)!=1:stop('Cannot identify one owner of AOI port '+str(port)+'. No process stopped.')
        owners.update(pids)
    if len(owners)!=1:stop('AOI ports have different owners. No process stopped.')
    pid=owners.pop();proc=Path('/proc')/str(pid)
    try:
        args=proc.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0')
        cwd=proc.joinpath('cwd').resolve();uid=proc.stat().st_uid
        if not is_existing_aoi(args,cwd,uid):stop('Port owner is not the expected current-user AOI module. No process stopped.')
        original_stamp=process_start_stamp(proc)
        print('AOI_RESTART: gracefully stopping verified AOI PID '+str(pid),flush=True)
        os.kill(pid,signal.SIGTERM)
    except (OSError,UnicodeError):stop('Cannot verify/stop the existing AOI process.')
    for i in range(30):
        if not any(opened(port) for port in (8500,8400)):break
        time.sleep(.5)
    else:
        # Escalate only for the exact same owned AOI instance, never a reused PID or another service.
        try:
            args=proc.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0')
            if not same_aoi_instance(args,proc.joinpath('cwd').resolve(),proc.stat().st_uid,process_start_stamp(proc),original_stamp):
                stop('AOI process identity changed. No force kill performed.')
            for port in (8500,8400):
                result=subprocess.run(['ss','-H','-ltnp','sport = :'+str(port)],capture_output=True,text=True,timeout=5)
                current=set(map(int,re.findall(r'pid=(\d+)',result.stdout)))
                if result.returncode or result.stdout.strip() and current!={pid}:
                    stop('Port owner changed. No force kill performed.')
            print('AOI_RESTART: previous AOI did not exit; stopping the same verified PID '+str(pid)+' with SIGKILL',flush=True)
            os.kill(pid,signal.SIGKILL)
        except (OSError,UnicodeError,IndexError):stop('Cannot reverify the original AOI instance. No further process stopped.')
        for i in range(20):
            if not any(opened(port) for port in (8500,8400)):break
            time.sleep(.5)
        else:stop('AOI ports remain occupied after the verified process stopped. Check for a supervisor restarting it.')

print('AOI_PYTHON: '+python,flush=True)
print('Starting the existing AOI entry point; model loading may take time.',flush=True)
process=subprocess.Popen([python,'-u','-m','fab_virtual_lot.aoi_unity'])
try:
    ready=False
    for i in range(180):
        if process.poll() is not None:stop('AOI entry point exited; see its output above.')
        if opened(8500) and opened(8400):
            print('AOI_8500_8400_READY',flush=True)
            print('Ports are ready. Camera frames are separate: captured=0/connected=false means the camera source is unavailable.',flush=True)
            print('Unity preview: ws://192.168.213.167:8500/camera/preview',flush=True)
            print('Unity inspection: ws://192.168.213.167:8400/aoi',flush=True)
            print('Use the existing CAMERA_PREVIEW_TOKEN and AOI_UNITY_TOKEN in Unity. Keep this window open.',flush=True)
            ready=True;break
        time.sleep(1)
    if not ready:stop('Both ports did not become ready within 180 seconds. Check the server configuration/output.')
    raise SystemExit(process.wait())
finally:
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
PY
