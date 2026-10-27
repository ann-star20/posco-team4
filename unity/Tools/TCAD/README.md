# 보정 후보 → Gateway DB → Gateway 팀원 → TCAD 서버

## 사용

1. Jetson CSV 터널과 기존 진단 워커 연결 창을 유지한다.
2. Unity의 Gateway DB 결과 → 검사 전송·결과에서 현재 Gateway 주소와 요청 토큰을 입력하고 자동 검사 연동을 시작한다.
3. 새 CSV 검사를 실행한다. 검사 완료 후 기존 별도 진단 워커가 원인·보정 후보를 계산한다.
4. 진단 완료 시 보정 후보가 Gateway로 자동 전송된다. 연동을 나중에 켰다면 TCAD 전달 탭에서 Gateway에 보정 후보 보내기를 누른다.
5. DB 완료 이벤트까지 수신하면 보정 후보·예측값 DB 저장 확인으로 표시한다. queued는 접수이며 예측 완료가 아니다.
6. Gateway 팀원이 DB 이벤트를 읽어 TCAD 서버로 전달한다. Unity는 TCAD 서버에 직접 접속하지 않는다.

같은 검사에서 버튼을 반복해서 눌러도 새 후보 요청을 만들지 않는다. 연결 종료·타임아웃 후 자동 재전송은 하지 않는다. 기록된 요청 ID로 접수 여부부터 확인한다.

## Gateway에 저장하는 구조

현재 확인된 API/WS 기능을 사용한다. 새 TCAD API나 이벤트 이름을 만들어 전송하지 않는다.

- 요청: WebSocket /api/v1/control, X-Unity-Token, type=surrogate.requested.
- stage_id=tcad_candidate_prediction, 고유 request_id UUID. 연결된 원검사 RUN이 있으면 동일 run_id를 사용한다.
- input_payload.process_parameters: 보정 후 후보의 body_dose / epi_doping / oxide_thickness.
- input_payload.provenance.tcad: Gateway 팀원 전달 목적, 별도 진단 워커 출처, 진단 요청·제안 ID, 원인 불확실성, 경고, 추정 보정 전 상태, 보정계수, 확정된 TCAD setup, double 정밀도 규격 및 1e-6 여유.
- 출력은 서버가 해당 후보에서 새로 계산한다. DB의 surrogate.completed 이벤트에 input_payload와 response.result_payload가 함께 저장된다.
- CSV의 정답 배율은 모델 요청으로 직렬화하지 않는다. 후보 요청에는 CSV 행·해시·정답 배율·원시 진단 블록을 포함하지 않는다.

진단 출처는 separate_legacy_diagnostic_worker / gp_tabpfn이다. 현재 팀원 서비스가 직접 생성한 top_category/route/high_confidence 응답으로 가장하지 않는다.
예측값 출처는 Gateway의 실제 prod 서로게이트 결과다. 예측값은 TCAD 계산값이 아니다.

## Gateway 팀원이 TCAD 요청을 구성하는 위치

완료 이벤트의 payload를 e라고 하면:

| TCAD 요청 필드 | DB 이벤트에서 가져올 값 |
| --- | --- |
| request_id | e.request_id (후보마다 고유 UUID) |
| process_parameters | e.input_payload.process_parameters |
| predicted_outputs | e.response.result_payload |
| requested_outputs | e.input_payload.requested_outputs |
| tcad_setup | e.input_payload.provenance.tcad.tcad_setup |
| 규격·여유 | e.input_payload.provenance.tcad.spec |
| 연결 ID | e.run_id / e.job_id, 바깥 event_id / sequence |
| 진단·불확실성 | e.input_payload.provenance.tcad |

TCAD의 반환 결과에도 후보 request_id와 제안/원검사 연결 ID를 유지한다. Gateway가 다른 TCAD 요청 ID를 새로 발급하면 이 원 요청 ID를 correlation로 보존한다.
모든 후보는 미승인·미적용이며, exploratory_only인 후보가 규격을 만족해도 원인 확정이나 보정 타당성 검증 완료로 해석하지 않는다.

## 실제 DB 검증 (2026-10-21)

현재 B081의 보정 후보를 Gateway에 접수하고, 완료 이벤트를 REST로 다시 읽어 DB 저장을 확인했다.

- request_id: 54c4524c-324e-4a69-aaa7-3b52453c406f
- run_id: 143044db-4784-4d10-a9b0-3180a0ee1c65
- job_id: 81fcbd36-a1b2-4089-a531-fe2c1dfcd7d2
- event_id: c4481f40-37c5-5b8b-997d-90664a18bcbe, sequence 49
- prod 예측: Vth 2.460263 V / gm 4.528899 uS/um / id_on 4.577667 uA/um / BV 47.960363 V

증거: Tools/Gateway/TcadChecks/. 이 확인은 후보 DB 저장·모델 예측까지이며 TCAD 실행·승인은 포함하지 않는다.
기존 Outbox JSON은 이전 로컬 검토 파일이며 현재 전송 경로가 아니다.
Unity 코드의 컴파일은 통과했다. GatewayTcadCheck.once는 Play 종료·새로고침 후 wire 형식과 출처/단위/정답 제외를 점검한다.