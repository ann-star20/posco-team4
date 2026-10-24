# Jetson 서로게이트·진단 실제 모델 E2E

## 1. 의미

다음 명령이 `status=ready`를 반환하면 Jetson의 ML HTTP 서비스와 두 모델은 이미
메모리에 로드된 상태다.

```bash
curl -sS http://127.0.0.1:8300/health/ready | python3 -m json.tool
```

이 명령은 ROS Worker나 Gateway가 실행 중이라는 뜻은 아니다. 전체 연동에는 ML
서비스, 두 Jetson Worker, Gateway API와 ROS adapter가 모두 필요하다.

## 2. Jetson 환경파일

저장소의 `config/env/jetson-ml-prod.env.example`을 다음 위치로 복사한다.

```text
/home/jetson/project/smart_factory/.env.ml-prod
```

실행 시 공통 `.env` 다음에 `.env.ml-prod`를 source하여 prod 값이 우선하게 한다.

```bash
cd /home/jetson/project/smart_factory
set -a
source .env
source .env.ml-prod
set +a
```

모델 서비스가 같은 Jetson의 8300 포트에 있으므로 두 URL은 다음과 같다.

```dotenv
SURROGATE_PROD_URL=http://127.0.0.1:8300
DIAGNOSIS_PROD_URL=http://127.0.0.1:8300
```

## 3. 모델 단독 통신

팀원이 제공한 `통신/예시/`의 요청 JSON을 사용한다.

```bash
curl -sS -X POST http://127.0.0.1:8300/api/v1/predict \
  -H 'Content-Type: application/json' \
  --data @통신/예시/<predict-request.json> | python3 -m json.tool

curl -sS -X POST http://127.0.0.1:8300/api/v1/diagnose \
  -H 'Content-Type: application/json' \
  --data @통신/예시/<diagnose-request.json> | python3 -m json.tool
```

학습 영역 중심 시험값은 `body_dose=7.7e12`, `epi_doping=1.7e16`,
`oxide_thickness=0.06`이다. 기존 문서의 `3.2e13`은 사용하지 않는다.

## 4. Jetson Worker 실행

두 터미널에서 공통 ROS와 env를 source한다.

```bash
cd /home/jetson/project/smart_factory
source /home/jetson/vision_env/bin/activate
source /opt/ros/humble/setup.bash
source jetson_ws/install_vision/setup.bash
set -a; source .env; source .env.ml-prod; set +a
export PYTHONPATH="/home/jetson/vision_env/lib/python3.10/site-packages:$PWD/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"
```

터미널 1:

```bash
/home/jetson/vision_env/bin/python3 -u -m fab_virtual_lot.surrogate_worker
```

터미널 2:

```bash
/home/jetson/vision_env/bin/python3 -u -m fab_virtual_lot.diagnosis_worker
```

`colcon build --install-base install_vision`을 다시 수행한 뒤에는 다음 명령도 가능하다.

```bash
ros2 run fab_virtual_lot fab_surrogate_worker
ros2 run fab_virtual_lot fab_diagnosis_worker
```

## 5. ROS 확인

```bash
ros2 node list --no-daemon
ros2 topic info /fab/surrogate_requests --verbose --no-daemon
ros2 topic info /fab/diagnosis_requests --verbose --no-daemon
ros2 topic info /fab/events --verbose --no-daemon
ros2 topic echo /fab/event_acks --no-daemon
```

Gateway와 Worker가 모두 실행되면 각 요청 토픽은 publisher 1, subscription 1이어야
한다. `/fab/events`에도 publisher와 subscription이 각각 1개 이상이어야 한다.

## 6. Gateway 설정

Gateway `.env`는 다음 모드를 사용하고 프로세스를 재시작한다.

```dotenv
SURROGATE_MODE=prod
DIAGNOSIS_MODE=prod
ROS_SURROGATE_REQUEST_TOPIC=/fab/surrogate_requests
ROS_DIAGNOSIS_REQUEST_TOPIC=/fab/diagnosis_requests
```

Gateway는 Jetson HTTP URL을 직접 호출하지 않는다. URL은 Jetson Worker 환경에만
필요하다.

## 7. DB 확인

```sql
SELECT job_id,task_type,status,result_event_id,created_at
FROM public.inference_jobs
WHERE task_type IN ('surrogate','diagnosis')
ORDER BY created_at DESC LIMIT 20;

SELECT job_id,top_category,compensation_route,high_confidence,routing_status,created_at
FROM public.diagnosis_results
ORDER BY created_at DESC LIMIT 20;

SELECT job_id,task_type,model_name,model_version,status,error_code,
       inference_duration_ms,service_duration_ms,stage_metrics
FROM public.ml_inference_executions
ORDER BY completed_at DESC LIMIT 20;
```

`tcad_verify` 후보의 실제 TCAD 전송은 팀원이 제공한 실제 `tcad_proposal` 샘플로
3변수 mapper 계약을 고정한 후 활성화한다. 그 전에는 안전하게
`review_required`로 저장한다.
