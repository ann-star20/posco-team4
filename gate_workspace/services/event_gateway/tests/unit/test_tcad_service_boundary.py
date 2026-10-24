from importlib.util import find_spec
from uuid import uuid4

from fastapi.testclient import TestClient

from mock_tcad.app import create_app


def test_mock_health_identifies_fixture_backend(tmp_path):
    with TestClient(create_app(tmp_path / 'mock.sqlite')) as client:
        response = client.get('/health/ready')
        assert response.status_code == 200
        assert response.json()['result_origin'] == 'mock'


def test_mock_request_identity_covers_process_inputs(tmp_path):
    body = {
        'request_id': str(uuid4()), 'proposal_id': str(uuid4()),
        'targets': {key: {'min': 0.9, 'max': 1.1}
                    for key in ('vth', 'gm', 'id_on', 'bv')},
        'x_candidate': {'body_dose': 1.0},
    }
    with TestClient(create_app(tmp_path / 'mock.sqlite')) as client:
        first = client.post('/api/v1/verifications', json=body)
        assert first.status_code == 202
        changed = body | {'x_candidate': {'body_dose': 1.1}}
        assert client.post('/api/v1/verifications', json=changed).status_code == 409


def test_prod_service_is_live_but_does_not_fake_calculation():
    assert find_spec('tcad_service') is not None, 'TCAD service scaffold missing'
    from tcad_service.app import create_app as create_service

    with TestClient(create_service()) as client:
        assert client.get('/health/live').status_code == 200
        assert client.get('/health/ready').status_code == 503
        response = client.post('/api/v1/verifications', json={})
        assert response.status_code == 503
        assert response.json()['detail']['code'] == 'backend_not_configured'
        assert client.get('/api/v1/verifications/unknown').status_code == 404
