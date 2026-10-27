"""Read-only inventory. Never reads environment variables, credentials or model weights."""
import importlib.util
import json
import os
import pathlib
import socket
import subprocess

home = pathlib.Path.home()
result = {'hostname': socket.gethostname(), 'addresses': [], 'listening': [], 'packages': {}, 'candidate_files': []}
for args, key in [(['hostname', '-I'], 'addresses'), (['ss', '-ltn'], 'listening')]:
    try:
        result[key] = subprocess.run(args, capture_output=True, text=True, timeout=5).stdout.splitlines()[:25]
    except Exception:
        result[key] = ['unavailable']
for name in ['ultralytics', 'cv2', 'torch', 'websockets', 'fastapi', 'aiohttp']:
    try: result['packages'][name] = importlib.util.find_spec(name) is not None
    except Exception: result['packages'][name] = False
skip = {'venv', '.venv', 'node_modules', '.git', '__pycache__', 'site-packages', '.cache', 'models', 'weights', 'datasets'}
for root in [home / 'project', home / 'projects', home / 'smart_factory', home / 'Desktop']:
    if not root.is_dir(): continue
    for directory, folders, files in os.walk(root):
        rel = pathlib.Path(directory).relative_to(root)
        folders[:] = [f for f in folders if f not in skip and not f.startswith('.') and len(rel.parts) < 5]
        for name in files:
            path = pathlib.Path(directory) / name
            if name.endswith('.py') and any(word in str(path).lower() for word in ['aoi', 'jetson_ws', 'smart_factory', 'inspect', 'detect']):
                result['candidate_files'].append(str(path))
        if len(result['candidate_files']) >= 150: break
print(json.dumps(result, ensure_ascii=False, indent=2))
