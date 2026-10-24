# TCAD·Unity prod 전환 체크리스트

`TCAD_MODE`와 `UNITY_MODE`는 독립 플래그다. prod는 실제 서비스가 준비된 경우에만 켠다. 플래그만 변경해도 실제 연동이 검증된 것으로 간주하지 않는다.

1. TCAD 워크스테이션의 HTTP 주소, 인증 방식, `request_id` 멱등성, `job_id` 조회 API, X/Y 단위 및 기준값을 합의한다. `TCAD_PROD_URL`을 `.env`에 설정하고 `TCAD_MODE=prod`로 전환한다. 기존 작업은 DB의 `tcad_mode`와 `endpoint_url`이 고정되어 새 모드로 소급 전환되지 않는다.
   Jetson 데모 발행기는 run ID를 프로젝트 로컬 파일에 유지한다. 모드를 바꿀 때는 `FAB_RUN_ID`에 새 UUID를 지정해 새 run을 시작한다. 기존 발신함에 남은 이벤트는 과거 run의 모드로 재시도한다. 과거 run에 prod URL이 필요하면 기존 주소도 계속 설정해 둔다.
2. Unity 클라이언트가 Gateway의 `GET /api/v1/events`와 `WS /api/v1/stream` 계약, 커서 저장, 재접속, 보정값의 `current/delta/recommended`를 구현했는지 확인한다. `UNITY_MODE=prod`는 모의 Unity 자동 시작만 막으며 Gateway 경로는 동일하다.
3. `result_origin=mock`인 검증 결과는 prod Unity 승인에서 거부된다. 현재 승인 API는 단일 운영자 토큰을 검사하고 ROS 명령·적용 영수증은 공유키로 서명하는 폐쇄된 개발 네트워크의 데모용이다. 실제 운영에는 개별 사용자 인증·인가, TLS, ROS 2 DDS 보안, 키 배포·회전 및 감사 정책이 추가로 필요하며 현재 구현을 외부망에 노출하지 않는다.
4. 실제 Jetson/TCAD/Unity E2E, 재시작·단절 복구, DB 백업/복원, 지연·오류 로그를 확인한 뒤에만 실연동 완료로 표시한다.
