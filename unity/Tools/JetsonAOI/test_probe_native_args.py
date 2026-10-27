"""Verify the actual Windows PowerShell -> native -> POSIX command argument path."""
import ast
import base64
import json
import shlex
import subprocess
import sys

parts = shlex.split(sys.argv[-1])
assert len(parts) == 4 and parts[:2] == ['python3', '-c'], 'Remote Python arguments lost quoting'
ast.parse(base64.b64decode(parts[3]).decode('utf-8-sig'))
dummy = base64.b64encode(b'print("camera-probe-argument-ok")').decode()
check = subprocess.run([sys.executable, '-c', parts[2], dummy], capture_output=True, text=True, timeout=5)
assert check.returncode == 0 and check.stdout.strip() == 'camera-probe-argument-ok', 'Encoded payload treated as a variable'
print(json.dumps({'hostname': 'offline-test', 'candidate_files': []}))
