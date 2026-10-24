"""HTTP client shared by Jetson ML workers."""


class ModelHttpClient:
    def __init__(self, mode, url, endpoint, http):
        if mode not in {"mock", "prod"} or not url or not endpoint.startswith("/"):
            raise ValueError("model mode, URL and endpoint required")
        self.mode, self.url, self.endpoint, self.http = mode, url.rstrip("/"), endpoint, http

    def __call__(self, request):
        request_mode = request.get("surrogate_mode", request.get("diagnosis_mode", self.mode))
        if request_mode != self.mode:
            raise ValueError("worker mode mismatch")
        response = self.http.post(self.url + self.endpoint, json=request)
        response.raise_for_status()
        body = response.json()
        if (body.get("request_id") != request["request_id"]
                or body.get("job_id") != request["job_id"]
                or body.get("result_origin") != self.mode
                or body.get("model_contract_version") != request["model_contract_version"]
                or body.get("status") not in {"succeeded", "failed"}):
            raise ValueError("model response identity/contract/origin mismatch")
        return body
