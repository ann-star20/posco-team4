"""Run real subprocesses to catch ignored .env bind settings and CLI regressions."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.parametrize('module,mode,target,expected_code', [
    ('mock_tcad.app', 'mock', 'tcad-mock', 0),
    ('tcad_service.app', 'prod', 'tcad-readiness', 2),
])
def test_service_and_probe_use_env_and_real_http(tmp_path, module, mode, target, expected_code):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    (tmp_path / '.env').write_text(
        f'TCAD_BIND_HOST=127.0.0.1\nTCAD_BIND_PORT={port}\n'
        f'TCAD_MODE={mode}\nTCAD_MOCK_URL={base}\nTCAD_PROD_URL={base}\n',
        encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if not k.startswith('TCAD_')}
    env['PYTHONPATH'] = str(Path(__file__).parents[2] / 'src')
    proc = subprocess.Popen([sys.executable, '-m', module], cwd=tmp_path, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        with httpx.Client(timeout=0.3) as http:
            while time.monotonic() < deadline:
                assert proc.poll() is None, 'service exited before becoming reachable'
                try:
                    if http.get(base + '/health/live').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            else:
                pytest.fail('service did not bind to configured port')
        checked = subprocess.run(
            [sys.executable, '-m', 'event_gateway.communication_check', target,
             '--timeout', '3'], cwd=tmp_path, env=env, capture_output=True, text=True,
            timeout=15)
        assert checked.returncode == expected_code, checked.stdout
        result = json.loads(checked.stdout)
        if mode == 'mock':
            assert result['status'] == 'succeeded'
            assert result['result_origin'] == 'mock'
        else:
            assert result == {'reachable': True, 'ready': False}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
