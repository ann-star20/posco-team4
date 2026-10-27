"""Fetch pinned Windows build wheels and verify PyPI SHA256 before local install."""
import hashlib
import json
from pathlib import Path
import urllib.request

packages = {
    'opencv-python-headless': '4.12.0.88', 'numpy': '2.2.6', 'pyinstaller': '6.16.0',
    'altgraph': '0.17.4', 'packaging': '25.0', 'pyinstaller-hooks-contrib': '2025.9',
    'pefile': '2023.2.7', 'pywin32-ctypes': '0.2.3', 'setuptools': '80.9.0',
}
folder = Path(__file__).parent / '.wheels'
folder.mkdir(exist_ok=True)
for name, version in packages.items():
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=20) as response:
        info = json.load(response)
    wheels = [item for item in info['urls'] if item['filename'].endswith('.whl') and
              (item['filename'].endswith('none-any.whl') or
               ('win_amd64' in item['filename'] and any(tag in item['filename'] for tag in ('cp312-', 'cp37-abi3', 'py3-none'))))]
    if len(wheels) != 1:
        raise RuntimeError(f'{name}: expected one compatible wheel, got {len(wheels)}')
    wheel = wheels[0]
    target = folder / wheel['filename']
    if not target.exists():
        with urllib.request.urlopen(wheel['url'], timeout=60) as response:
            target.write_bytes(response.read())
    if hashlib.sha256(target.read_bytes()).hexdigest() != wheel['digests']['sha256']:
        raise RuntimeError(f'{name}: digest mismatch')
    print(target.name, flush=True)
