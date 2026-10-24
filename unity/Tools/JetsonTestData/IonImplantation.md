# 이온주입: CSV 전기특성 → Jetson 직접 진단 → Gateway 보정 후보 예측

## 진단·보정 요청 조건

- 완료 주입량과 같은 CSV 행의 Vth·BV를 함께 판정한다.
- 주입량 OK + 전기특성 OK: 정상 완료. 검사값·OK 판정은 Gateway로 보내고 직접 진단·보정 후보 요청만 생략한다. 전기특성 결과와 공정 이력 표시는 유지한다.
- 주입량 FAIL 또는 전기특성 NG: Jetson 직접 진단 후 원인·보정 후보를 기존 Gateway 경로로 전송한다.
- 값 누락이나 허용 범위 미설정으로 판정이 대기이면 정상으로 처리하지 않는다. 확인된 NG도 없으면 전송을 보류한다.
- 기존에 이미 전송한 검사 기록은 삭제하거나 취소하지 않는다. 새 검사부터 적용한다.

## 연결 주소 (2026-10-24 갱신)

1. Jetson CSV 창과 `Tools/JetsonML/start-jetson-process-worker.cmd` 창을 유지한다. Jetson은 `192.168.213.167`이다.
2. Unity Gateway 창에서 토큰을 입력하고 자동 검사 연동을 켠 뒤 검사를 시작한다. Gateway 주소는 `ws://192.168.212.10:8000/api/v1/stream`이다. 토큰은 Play 세션 메모리에만 유지한다.
3. 이온주입 완료 시 고정된 같은 CSV 행의 TCAD 전기특성 네 값과 판정을 즉시 표시한다. 주입량 또는 전기특성이 NG일 때 그 값으로 산화막과 같은 Jetson 직접 진단 경로를 호출한다.
4. 직접 진단 응답을 검사 ID·LOT·웨이퍼·입력과 대조한 뒤 원인, 보정 계수, 확률, 추가 측정 권고를 표시한다. Gateway 응답을 기다리느라 이 표시를 늦추지 않는다.
5. 진단의 추정 상태에 LOT 모델 기준값을 곱하고 도즈·산화막 보정 계수를 적용해 후보 공정값을 만든다. CSV 정답 배율을 보정 후보 계산에 사용하지 않는다. 에피는 진단 추정값을 유지한다.
6. 산화막과 같은 `surrogate.requested`, `stage_id=tcad_candidate_prediction` 요청으로 후보와 진단을 Gateway에 자동 제출한다. 별도 `diagnosis.requested` 보관 요청을 중복 전송하지 않는다.
7. 같은 요청의 `surrogate.completed` 결과를 수신하면 후보 예측값과 DB 이벤트 ID·sequence를 연결한다. `request.accepted`는 접수일 뿐 결과 완료가 아니다.

## 정상 검사 결과 기록

정상 검사는 기존 Gateway의 surrogate.requested 경로로 보내되 stage_id=ion_inspection_record로 구분한다. 현재 Gateway에는 이미 완료된 검사값을 보관하는 전용 API가 없어 기존 지원 경로를 사용한다. 서버 ML 예측이 함께 실행되지만 원 검사값과 OK 판정은 다음 경로에 따로 보존하며, 서버 예측값으로 덮어쓰지 않는다.

- 원 검사값·판정: input_payload.provenance.inspection_result
- purpose: normal_inspection_record
- dose_cm2, target_cm2, lower_cm2, upper_cm2, completed_at
- measurements: vth(V), gm(uS/um), id_on(uA/um), bv(V)
- verdict / dose_verdict / electrical_verdict: OK
- diagnosis_requested=false, correction_candidate=false
- provenance.tcad에 유효한 후보 목적이나 진단 결과가 없다. TCAD 전달 대상이 아니다.
- 같은 요청의 surrogate.completed를 수신한 뒤 DB 저장 확인으로 표시한다. 접수 응답만으로 결과 완료라고 표시하지 않는다.
- 정상 기록의 DB 재조회 증거는 Tools/Gateway/IonNormalRecordIntegration/에 보관한다.

## Gateway 팀원이 구분할 필드

- `type`: `surrogate.requested`
- `stage_id`: `tcad_candidate_prediction`
- `input_payload.provenance.tcad.purpose`: `tcad_candidate_prediction_for_gateway_forwarding`
- 후보: `input_payload.process_parameters`의 `body_dose`, `epi_doping`, `oxide_thickness` (cm⁻², cm⁻³, µm).
- 원인·보정 계수·추정 상태·경고: `input_payload.provenance.tcad`.
- 직접 진단 전체 원문: `input_payload.provenance.tcad.direct_diagnosis` (원문 gm/Id는 SI 단위, 원문 단위 정보를 함께 보존).
- 원 검사: `lot_id`, `unit_id`, `provenance.inspection_id`, `sample_id`, `csv_sha256`. 요청 UUID와 RUN UUID로 결과를 연결한다.
- 후보 예측: 같은 요청의 `surrogate.completed.payload.response.result_payload`. gm은 µS/µm, id_on은 µA/µm이다. 원 CSV 전기특성과 구분한다.
- TCAD 실행 조건과 스펙: `provenance.tcad.tcad_setup`, `provenance.tcad.spec`.

Gateway 팀원이 이 후보와 예측값을 TCAD 검증 서비스로 전달한다. Unity는 TCAD 서버에 직접 보내지 않는다. 원인 불확실/정상 후보는 탐색·검토 자료로 표시하며 자동 승인·레시피 적용은 하지 않는다. 이 이벤트는 TCAD 검증 완료가 아니다.

## 판정과 출처

목표 도즈 7.70E+12 cm⁻², 시연 허용 범위 7.315E+12~8.085E+12 cm⁻² (경계 포함). 주입량과 CSV 전기특성은 시뮬레이션/저장 TCAD 자료이며 센서 실측이 아니다. 전기 판정은 Vth 1.7~2.6 V, BV ≥40 V이고 gm·Id는 진단용이다. 직접 진단 입력은 CSV SI 단위를 유지하고 후보 예측 출력의 마이크로 단위와 혼동하지 않는다.

## 검증

- `IonGatewayCheck.result`: 산화막과 같은 후보 요청, 추정값×모델 기준×보정 계수, 단위·검사 연결·잘못된 입력 차단.
- `IonJetsonCsvCheck.result`: 전체 공정, 전기특성 창 자동 열기, 직접 진단 연결, 후보 전환, 중복 차단. 서버 전송 없는 오프라인 시험이다.
- `Tools/Gateway/IonCandidateIntegration/`: 저장된 실제 Jetson 진단 응답으로 Unity가 만든 후보 한 건의 실서버 전송·DB 이벤트 재조회 자료. Unity 공정 버튼의 실제 네트워크 전 과정을 시험한 자료와는 구분한다.
- 기존 `IonDirectIntegration/`의 diagnosis 요청은 과거 보관 방식이다. queued 작업을 현재 후보 완료의 증거로 사용하지 않는다.

