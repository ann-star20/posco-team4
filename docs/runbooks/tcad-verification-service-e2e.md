# TCAD 검증 서비스 E2E 실행 가이드

이 문서는 Jetson 진단 결과의 모든 보정 후보를 WSL Gateway가 Aiven PostgreSQL에
저장하고, 외부 TCAD HTTP 큐에 한 건씩 전송한 뒤 Unity 이벤트로 재생하는 절차다.
실제 토큰과 주소는 로컬 `.env`에만 둔다.

## 1. 환경변수

mock 통신 시험:

```dotenv
TCAD_MODE=mock
TCAD_MOCK_URL=http://127.0.0.1:8100
TCAD_API_TOKEN=<local-test-token>
TCAD_AUTO_SUBMIT_ENABLED=true
TCAD_MAX_CONCURRENT_JOBS=1
TCAD_CONNECT_TIMEOUT_SECONDS=5
TCAD_REQUEST_TIMEOUT_SECONDS=30
TCAD_POLL_INTERVAL_SECONDS=10
TCAD_JOB_DEADLINE_SECONDS=6000
TCAD_POLICY_VERSION=route-v1
```

실제 검증 서비스:

```dotenv
TCAD_MODE=prod
TCAD_PROD_URL=http://<tcad-workstation-ip>:<port>
TCAD_API_TOKEN=<issued-secret>
TCAD_AUTO_SUBMIT_ENABLED=true
TCAD_MAX_CONCURRENT_JOBS=1
```

prod에서는 `TCAD_PROD_URL`과 `TCAD_API_TOKEN`이 없으면 Gateway 시작을 거부한다.
토큰은 POST와 GET의 `X-Fab-Token`으로만 전송하며 DB·로그·Unity에는 저장하지 않는다.

## 2. 마이그레이션 확인

WSL에서 Gateway 가상환경을 활성화하고 마이그레이션을 실행한다.

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src"
python -m event_gateway.migrate
```

Aiven에서 적용 여부를 확인한다.

```sql
SELECT version, applied_at
FROM schema_migrations
WHERE version = '010_create_tcad_candidate_queue.sql';
```

## 3. mock TCAD와 Gateway Worker 실행

터미널 A:

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
set -a; source .env; set +a
export PYTHONPATH="$PWD/services/event_gateway/src"
fab-mock-tcad
```

터미널 B:

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
set -a; source .env; set +a
export PYTHONPATH="$PWD/services/event_gateway/src"
fab-verification-worker
```

Gateway ROS bridge와 HTTP/WebSocket 서버는 기존 ROS 스택 자동 실행 가이드에 따라
별도 터미널에서 실행한다.

## 4. 진단 결과에서 후보 생성

Unity 또는 mock Unity가 `diagnosis.requested`를 보내면 Jetson diagnosis worker가
`diagnosis.completed`를 `/fab/events`에 발행한다. 시험 응답은
`anomaly_detected=true`, `compensation.route=tcad_verify`이고 후보를 두 개 이상
포함하게 한다.

Gateway의 `/fab/event_acks`에서 `status=committed`를 확인한다. 이 ACK는
`diagnosis_results`, `tcad_proposal_groups`, 모든 `tcad_verification_candidates`가
같은 트랜잭션으로 저장된 뒤에만 발행된다.

## 5. DB 진행 상태 확인

```sql
SELECT g.proposal_id, g.status, g.candidate_count, g.terminal_count,
       c.candidate_index, c.tcad_request_id, c.status,
       c.queue_position, c.last_stage, c.last_error_code
FROM tcad_proposal_groups g
JOIN tcad_verification_candidates c USING (proposal_id)
ORDER BY g.created_at DESC, c.candidate_index;
```

`TCAD_MAX_CONCURRENT_JOBS=1`이면 후보는 모두 즉시 DB에 존재하지만 외부 상태가
`queued` 또는 `running`인 후보는 동시에 하나뿐이어야 한다. Worker를 재시작해도
같은 `tcad_request_id`로 조회를 이어간다.

## 6. Unity 재생 확인

Unity는 TCAD 서버에 직접 연결하지 않는다. Gateway WebSocket에 마지막 커서를
사용해 다시 접속한다.

```text
ws://<gateway-ip>:8000/api/v1/stream?run_id=<run-id>&after_sequence=<last-sequence>
```

후보별 queued/running/succeeded/failed/cancelled 이벤트와 마지막
`tcad.verification.batch_completed`를 확인한다. 성공 후보가 있으면
`tcad.verification.review_required`가 이어진다. 장시간 검증 동안 WebSocket을 계속
열어둘 필요는 없다.

## 7. 실제 TCAD 서비스 사전 확인

```bash
curl -sS -H "X-Fab-Token: $TCAD_API_TOKEN" \
  "$TCAD_PROD_URL/health/ready" | python3 -m json.tool
```

준비 확인 뒤 `TCAD_MODE=prod`로 Worker만 재시작한다. mock 결과를 prod로 승격하거나
실패 시 mock으로 자동 전환하지 않는다.

## 8. 실패 판별

- 401/403: 토큰 불일치이며 해당 후보는 terminal failed다.
- 400/422: 요청 계약 오류이며 자동 재시도하지 않는다.
- 5xx/네트워크 오류: 동일 `tcad_request_id`로 재시도한다.
- deadline 초과: local `expired`로 기록하며 자동으로 새 ID를 만들지 않는다.
- Unity 연결 종료: Aiven 이벤트가 보존되므로 `after_sequence`로 재생한다.

현재 신규 후보 흐름은 `review_required`까지다. TCAD 계약에 현 공정값 `x_current`가
없으므로 이를 추정해 기존 보정 명령을 만들지 않는다. 관리자 후보 선택과 실제 명령
변환은 현 공정값 계약이 확정된 뒤 연결한다.
