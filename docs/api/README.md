# Virtual Fab 통신 명세 사용 안내

## 파일

- [`openapi.yaml`](openapi.yaml): Gateway, Surrogate ML, TCAD HTTP 계약
- [`asyncapi.yaml`](asyncapi.yaml): Jetson/Gateway WebSocket과 ROS 2 토픽 계약
- [`../architecture/current-system-architecture.md`](../architecture/current-system-architecture.md): 전체 구성 및 데이터 흐름

## OpenAPI 확인

`openapi.yaml`은 OpenAPI 3.1 문서다. Swagger Editor에 파일 내용을 붙여넣거나 Swagger UI에서 로컬 파일을 지정한다. 각 operation의 `servers`를 확인해야 한다.

- Gateway 예시: `http://127.0.0.1:8000`
- Mock TCAD 예시: `http://127.0.0.1:8100`
- 실제 TCAD service 기본 예시: `http://<TCAD_HOST>:8200`
- Mock Surrogate 예시: `http://127.0.0.1:8300`

실제 주소와 토큰은 문서에 기록하지 않고 `.env`로 주입한다.

## AsyncAPI 확인

`asyncapi.yaml`은 AsyncAPI 2.6 문서다. WebSocket 채널은 표준 메시지 계약으로, ROS 2 채널은 `protocol: ros2-dds`와 `x-ros2-*` 확장 필드로 표현했다.

Unity 담당자는 다음 두 서버를 구분해야 한다.

```text
카메라 Preview: ws://<JETSON_IP>:8500/camera/preview
AOI 이미지/결과: ws://<JETSON_IP>:8400/aoi
중앙 이벤트/보정: ws://<GATEWAY_IP>:8000/api/v1/...
```

Preview는 구독 승인 뒤 `camera.preview.frame` JSON과 JPEG binary가 반복된다. Unity는 화면에 표시한 `frame_id`를 AOI 요청에 넣는다. AOI 서버는 `accepted`를 먼저 보내고 추론 완료 후 `completed` JSON과 annotated JPEG binary를 보낸다. JSON의 `byte_length`와 `sha256`으로 AOI binary frame을 검증한다.

실행·연결·검증 절차는 [`../runbooks/jetson-camera-preview-aoi.md`](../runbooks/jetson-camera-preview-aoi.md)를 따른다.

## 구현 상태 표기

- `x-implementation-status: implemented`: 현재 코드 존재
- `x-implementation-status: mock`: 통신 시험용 구현
- `x-implementation-status: scaffold`: 서비스 틀만 존재
- `x-implementation-status: required-gap`: 확정 구조에 필요하지만 아직 연결되지 않음

Jetson 직접 AOI WebSocket 결과는 `AOI_ROS_PERSISTENCE_ENABLED=true`일 때 SQLite
outbox와 `/fab/events`를 통해 Gateway/Aiven 영구 저장 흐름에 연결된다.

## 공통 상관관계 필드

모든 팀은 가능한 경우 다음 필드를 로그에도 함께 남긴다.

```json
{
  "run_id": "3271e8e2-97ba-4ba8-8f93-bfabaa78414e",
  "request_id": "29925c8f-f466-43fc-914c-f81141a82354",
  "job_id": "46c682b1-f800-4fbb-8244-37953a449de0",
  "event_id": "17099e6a-df03-55dd-9723-58db842e2771",
  "attempt": 1
}
```

UUID는 샘플이며 실제 실행 때 새 값으로 교체한다. 토큰, DB URL, 비밀번호는 샘플 payload·로그·Git에 넣지 않는다.
