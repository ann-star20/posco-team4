from uuid import uuid4
import httpx
import pytest
from fab_virtual_lot.surrogate_worker import SurrogateClient


@pytest.mark.parametrize('mode', ['mock','prod'])
def test_same_http_contract_preserves_model_metadata(mode):
    request={'request_id':str(uuid4()),'job_id':str(uuid4()),'model_contract_version':'fab-ml-v1'}
    response={**request,'result_origin':mode,'status':'succeeded',
              'result_payload':{'id':.71},'metadata':{'id_conditions':{'vgs':4}}}
    def serve(http_request):
        assert str(http_request.url)=='http://model-host:8300/api/v1/predict'
        return httpx.Response(200,json=response)
    with httpx.Client(transport=httpx.MockTransport(serve)) as http:
        assert SurrogateClient(mode,'http://model-host:8300',http)(request)==response


def test_prod_rejects_mock_result_and_http_failure_is_not_faked():
    request={'request_id':str(uuid4()),'job_id':str(uuid4()),'model_contract_version':'fab-ml-v1'}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={**request,'result_origin':'mock'}))) as http:
        with pytest.raises(ValueError):SurrogateClient('prod','http://model',http)(request)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as http:
        with pytest.raises(httpx.HTTPStatusError):SurrogateClient('prod','http://model',http)(request)
