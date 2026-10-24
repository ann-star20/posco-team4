"""Real HTTP/WebSocket checks; never inserts synthetic events into Gateway DB."""

import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import httpx
from websockets.sync.client import connect

from .config import _read_dotenv
from .tcad_client import TcadClient


def check_tcad_mock(base_url: str, timeout: float = 10) -> dict:
    """Submit a fixture only after verifying the endpoint identifies as mock."""
    with httpx.Client(base_url=base_url, timeout=timeout) as http:
        response = http.get('/health/ready')
        response.raise_for_status()
        if response.json().get('result_origin') != 'mock':
            raise ValueError('fixture submission requires a mock endpoint')
        current = {k: 1.0 for k in (
            'oxide_thickness', 'body_dose', 'diffusion_time', 'epi_doping')}
        body = {
            'request_id': str(uuid4()), 'proposal_id': str(uuid4()),
            'run_id': str(uuid4()), 'representation': 'normalized_ratio',
            'baseline_version': 'demo-v1', 'x_current': current,
            'delta_x': {k: 0.0 for k in current}, 'x_candidate': current,
            'y_observed': {k: 1.0 for k in ('vth', 'gm', 'id_on', 'bv')},
            'targets': {k: {'min': 0.9, 'max': 1.1}
                        for k in ('vth', 'gm', 'id_on', 'bv')},
        }
        client = TcadClient(http)
        accepted = client.submit(body)
        if client.submit(body).job_id != accepted.job_id:
            raise ValueError('request idempotency failed')
        deadline = time.monotonic() + timeout
        while True:
            result = client.poll(accepted.job_id)
            if result['status'] == 'succeeded':
                if (result['request_id'] != body['request_id']
                        or result['job_id'] != accepted.job_id
                        or result['result_origin'] != 'mock'):
                    raise ValueError('result identity or origin mismatch')
                return result
            if result['status'] == 'failed':
                raise ValueError('TCAD job failed')
            if time.monotonic() >= deadline:
                raise TimeoutError('TCAD job did not complete')
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))


def check_gateway(http_url: str, ws_url: str, run_id: UUID, timeout: float = 10) -> dict:
    """Compare a stored HTTP replay event with the actual WebSocket stream."""
    with httpx.Client(base_url=http_url, timeout=timeout) as http:
        http.get('/health/live').raise_for_status()
        response = http.get('/api/v1/events', params={
            'run_id': str(run_id), 'after_sequence': 0, 'limit': 1})
        response.raise_for_status()
        rows = response.json()['events']
    if not rows:
        raise ValueError('run has no committed events; publish a ROS event first')
    expected = rows[0]
    parts = urlsplit(ws_url)
    query = dict(parse_qsl(parts.query)) | {
        'run_id': str(run_id), 'after_sequence': str(expected['sequence'] - 1)}
    target = urlunsplit(parts._replace(query=urlencode(query)))
    with connect(target, open_timeout=timeout, close_timeout=2) as socket:
        actual = json.loads(socket.recv(timeout=timeout))
    if actual != expected:
        raise ValueError('HTTP replay and WebSocket event differ')
    return {'event_id': actual['event_id'], 'run_id': actual['run_id'],
            'sequence': actual['sequence'], 'status': 'matched'}


def main() -> None:
    parser = argparse.ArgumentParser(description='HTTP/WebSocket 실제 통신 점검')
    parser.add_argument('target', choices=['tcad-mock', 'tcad-readiness', 'gateway'])
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--run-id', type=UUID)
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    try:
        values = _read_dotenv(args.env_file) | dict(os.environ)
        if args.target == 'tcad-mock':
            if values.get('TCAD_MODE', 'mock') != 'mock':
                raise ValueError('TCAD_MODE must be mock for fixture submission')
            result = check_tcad_mock(values.get('TCAD_MOCK_URL',
                                               'http://127.0.0.1:8100'), args.timeout)
        elif args.target == 'tcad-readiness':
            mode = values.get('TCAD_MODE', 'mock')
            if mode not in {'mock', 'prod'}:
                raise ValueError('invalid TCAD_MODE')
            url = values.get('TCAD_PROD_URL') if mode == 'prod' else values.get(
                'TCAD_MOCK_URL', 'http://127.0.0.1:8100')
            if not url:
                raise ValueError('TCAD URL is required')
            with httpx.Client(base_url=url, timeout=args.timeout) as http:
                http.get('/health/live').raise_for_status()
                ready = http.get('/health/ready')
                if ready.status_code == 503:
                    print(json.dumps({'reachable': True, 'ready': False}))
                    raise SystemExit(2)
                ready.raise_for_status()
                result = {'reachable': True, 'ready': True}
        else:
            run_id = args.run_id or UUID(values['FAB_RUN_ID'])
            result = check_gateway(
                values.get('UNITY_GATEWAY_HTTP_URL', 'http://127.0.0.1:8000'),
                values.get('UNITY_GATEWAY_WS_URL', 'ws://127.0.0.1:8000/api/v1/stream'),
                run_id, args.timeout)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        # Network exception strings may contain URLs with credentials.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
                          'hint': '모드·URL·run_id·서비스 실행 상태를 확인하세요'},
                         ensure_ascii=False))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
