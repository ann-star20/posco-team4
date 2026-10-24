"""HTTP fixture model, deployed beside the Jetson inference adapter in mock mode."""
from uuid import UUID, uuid5
from fastapi import FastAPI, HTTPException


def predict(request: dict) -> dict:
    if request.get('model_contract_version') != 'fab-ml-v1':
        raise ValueError('unsupported model contract')
    scenario = request['input_payload'].get('scenario', 'normal')
    if scenario not in {'normal', 'anomaly', 'missing_candidate', 'failed'}:
        raise ValueError('unknown fixture scenario')
    anomaly = scenario in {'anomaly','missing_candidate'}
    response = {
        'request_id': request['request_id'], 'job_id': request['job_id'],
        'model_contract_version': 'fab-ml-v1', 'model_version': 'mock-gp-v1',
        'result_origin': 'mock', 'status': 'failed' if scenario == 'failed' else 'succeeded',
        'anomaly_detected': anomaly,
        'result_payload': {'vth': 1.2 if anomaly else 1., 'gm': 1., 'id': 1., 'bv': 1.},
        'metadata': {'representation': 'synthetic_normalized_fixture',
                     'id_conditions': {'vgs_v': 4, 'vds_v': 1, 'temperature_c': 25},
                     'note': '통신 시험용 고정값. 물리 모델 예측 아님.'},
        'tcad_proposal': None,
    }
    if scenario == 'anomaly':
        current = {key: 1. for key in ('oxide_thickness','body_dose','diffusion_time','epi_doping')}
        delta = {key: 0. for key in current}; delta['body_dose'] = .01
        response['tcad_proposal'] = {
            'proposal_id': str(uuid5(UUID(request['job_id']), 'candidate-v1')),
            'run_id': request['run_id'], 'representation': 'normalized_ratio',
            'baseline_version': 'demo-v1', 'x_current': current, 'delta_x': delta,
            'x_candidate': {key: current[key]+delta[key] for key in current},
            'y_observed': {key: 1. for key in ('vth','gm','id_on','bv')},
            'targets': {key: {'min': .9,'max': 1.1} for key in ('vth','gm','id_on','bv')},
        }
    return response


app = FastAPI(title='Jetson ML mock contract')

@app.get('/health/ready')
def ready():
    return {'status':'ready','result_origin':'mock'}

@app.post('/api/v1/predict')
def infer(request: dict):
    try:
        return predict(request)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(422, 'invalid model request') from exc


def main():
    import os, uvicorn
    uvicorn.run(app, host=os.environ.get('SURROGATE_BIND_HOST','127.0.0.1'),
                port=int(os.environ.get('SURROGATE_BIND_PORT','8300')))

if __name__ == '__main__':
    main()
