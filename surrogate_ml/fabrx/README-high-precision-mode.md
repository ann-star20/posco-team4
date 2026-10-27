# 고정밀 모드(GP+TabPFN) 배포 — Jetson venv 구성

`fabrx-model` 서비스(`/api/v1/diagnose`)는 `input_payload.refine: true`를 받으면
2단 GP(기본 모드) 결과 중 상위 100개 후보를 TabPFN으로 다시 확인하는
**고정밀 모드**를 수행한다. 이 로직(`TwoStagePipeline.__init__`의
`high_precision="auto"` 분기, `통신/모델서비스.py`의 `_ensure_pipe`)은 이미
존재했지만, Jetson 배포 환경에 `torch`/`tabpfn`이 없으면 조용히 기본 모드로
폴백하도록 방어적으로 짜여 있었다. 지금까지는 Jetson에 TabPFN이 설치돼 있지
않아 **항상 기본 모드로만 동작**했다.

## 무엇을 했나

1. 서비스 전용 가상환경을 `--system-site-packages`로 만들어, 이미 설치된
   Jetson 전용 torch(JetPack 빌드, CUDA 인식)를 재사용하면서 TabPFN만 격리
   설치했다. 시스템 전역 scipy/pandas 등(다른 서비스가 쓰는 버전)은 건드리지
   않는다.

   ```bash
   cd /home/jetson/project/surrogate_ml/fabrx
   python3 -m venv --system-site-packages .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install tabpfn
   ```

2. `torch`가 NumPy 1.x ABI로 빌드돼 있어 시스템 NumPy 2.2.6과 충돌
   (`RuntimeError: Numpy is not available`, `/diagnose refine:true` 요청이
   500으로 실패)하는 문제를, venv 안에만 NumPy를 1.x대로 내려서 해결했다.
   시스템 NumPy(다른 서비스가 쓰는 버전)는 그대로 둔다.

   ```bash
   .venv/bin/pip install "numpy<2"
   ```

3. systemd 유닛(`fabrx-model.service`, 이 디렉터리에 동봉)의 `ExecStart`를
   시스템 `python3` 대신 이 venv의 파이썬으로 가리키도록 바꿨다.

   ```bash
   sudo cp fabrx-model.service /etc/systemd/system/fabrx-model.service
   sudo systemctl daemon-reload
   sudo systemctl restart fabrx-model
   ```

## 검증

재배포 후 실제 `/api/v1/diagnose` 요청(`refine: true`)에 대해 고정밀 모드가
끝까지 수행되는 것을 확인했다 (`model-service.log`, 응답 바디 발췌):

```json
"refine": {
  "requested": true,
  "performed": true,
  "model_mode": "고정밀(GP+TabPFN)",
  "decision_changed": false,
  "reason": null
}
```

처리 시간 내역(`timing_ms`): `diagnosis` 1.1s, `compensation_search` 2.0s,
`refine` 7.0s, 총 `service_total` 약 19.5s. 이 중 약 9.4초는 서비스 재시작
후 **첫 refine 요청에서만** 발생하는 TabPFN 1회성 로딩 비용이며(해당
파이프라인은 프로세스 생애주기 동안 캐시됨), 이후 요청은 더 짧아진다.

## 범위에서 제외한 것

- `.venv/` 디렉터리 자체(설치된 패키지 수백 개)는 git에 올리지 않는다.
  위 설치 절차를 그대로 재현하면 된다.
- `통신/모델서비스.py`, `최종ML/ml_파이프라인.py` 등 모델 서비스 소스 코드는
  이번 작업에서 **수정하지 않았다** — 이미 `refine`/`high_precision="auto"`
  처리 로직을 갖추고 있었고, 누락된 건 배포 환경(TabPFN 설치) 쪽이었다.
