# 이온주입: CSV 전기특성 → Jetson 직접 진단 → Gateway 보정 후보 예측



> 아래는 이전 직접 워커 연동 기록이다. 2026-10-22 이후 Gateway 자동 연동 검사는 [전체 사이클](FullCycleTest/README.md)을 사용한다. 완료 공정값 예측 → 예측값으로 Gateway 진단 → route=tcad_verify일 때 Gateway 자동 TCAD 접수. 직접 진단·별도 후보 예측을 중복 요청하지 않는다.



## 진단·보정 요청 조건



- 완료 주입량과 같은 CSV 행의 Vth·BV를 함께 판정한다.

- 주입량 OK + 전기특성 OK: 정상 완료. 검사값·OK 판정은 Gateway로 보내고 직접 진단·보정 후보 요청만 생략한다. 전기특성 결과와 공정 이력 표시는 유지한다.

- 주입량 FAIL 또는 전기특성 NG: Jetson 직접 진단 후 원인·보정 후보를 기존 Gateway 경로로 전송한다.

- 값 누락이나 허용 범위 미설정으로 판정이 대기이면 정상으로 처리하지 않는다. 확인된 NG도 없으면 전송을 보류한다.

- 기존에 이미 전송한 검사 기록은 삭제하거나 취소하지 않는다. 새 검사부터 적용한다.



## 현재 연결 (2026-10-22)



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



## 이전 구현 기록 (아래는 과거 경로 자료)



# 이온주입 완료 → CSV TCAD 전기특성 표시 → Gateway 진단



## Unity 사용



Gateway 기본 주소: `ws://192.168.212.10:8000/api/v1/stream`.

Gateway 창에서 요청 토큰을 입력하고 **자동 검사 연동 시작**을 한 뒤 이온주입을 시작한다. 토큰은 기존과 같이 해당 Play 세션 메모리에만 유지한다.



1. 검사 시작 시 검사 ID·LOT·웨이퍼와 Jetson CSV 행을 고정한다. 이온주입은 TCAD 출처만 사용한다.

2. 검사 완료 시 같은 행의 TCAD Vth·gm·Id4V·BV를 대시보드에 즉시 표시한다. gm과 Id4V는 CSV의 SI 단위를 마이크로 단위로 정확히 한 번 환산한다. 서버의 새로운 서로게이트 예측을 기다리지 않는다.

3. Gateway 자동 검사 연동이 켜져 있으면 `diagnosis.requested`를 한 건만 전송한다. `surrogate.requested`는 이온주입 경로에서 생성하지 않는다.

4. 요청은 고유 request_id/run_id, 동일 검사 ID·LOT·웨이퍼·CSV ID·SHA-256으로 연결한다. measurements 단위는 V, µS/µm, µA/µm, V이며 n_wafers=1, refine=false이다.

5. 출처는 `jetson_csv_test / tcad_csv_not_measurement`로 명시한다. CSV의 공정 정답 배율이나 새 예측값을 진단 입력으로 섞지 않는다.

6. `diagnosis.completed`의 원인과 `compensation.target_process_parameters`를 표시하고 모든 TCAD 후보를 포함한 응답 원문을 보존한다. 전송 실패나 대기 상태도 CSV 전기특성은 계속 표시한다.



중단·인터록 검사는 전송하지 않는다. TCAD 값이 없는 CSV 행은 PC 예측값이나 0으로 대체하지 않는다. 연결이 끊겨 접수 여부가 불분명하면 자동 재전송하지 않는다. 자동 연동은 토큰 입력 후 켜야 하며 CSV 전기특성 표시는 이 연결과 독립적이다.



## 시연과 실측 구분



- 목표 도즈: **7.70E+12 cm⁻²**. 시연 허용 범위는 **7.315E+12~8.085E+12 cm⁻²**, 경계 포함. ±5%는 사용자가 선택한 시연 판정 기준이며 양산 승인 규격이 아니다.

- 도즈는 LOT 기준 × CSV 배율의 시뮬레이션 누적값이다. 전기특성은 같은 CSV 행에 저장된 TCAD 시험값이다. 둘 다 센서 실측값이 아니다.

- 전기 합격 기준은 프로젝트의 Vth 1.7~2.6 V, BV ≥40 V이며 gm·Id는 진단 관측값이다. 도즈 OK와 전기특성 OK는 별개다.



## Gateway / TCAD 책임



진단 결과와 보정 후보는 Gateway의 완료 이벤트가 DB에 커밋되어 돌아오는 것으로 확인한다. Unity가 별도 레거시 보정 후보 surrogate 요청을 중복 생성하거나 TCAD 서버에 직접 보내지 않는다. Gateway가 `tcad_proposal`과 해당 정책에 따라 TCAD 작업을 관리한다. `route=apply`여도 Unity는 레시피를 자동 적용하거나 승인하지 않는다. 정상 진단에는 보정값을 만들어 넣지 않는다.



최신 확인한 Gateway OpenAPI는 요청 최상위의 `task_type`을 허용하지 않는다. Unity → Gateway는 `type=diagnosis.requested`, Worker → 모델 서비스는 `task_type=diagnosis`로 변환되어야 한다. 모델 서비스가 최상위 task_type 없이 호출되면 서로게이트로 해석할 수 있으므로 서버 담당자가 해당 매핑을 확인해야 한다.



## 검증 증거 (2026-10-22)



현재 CSV 직접 진단 경로는 `IonGatewayCheck.result`와 `IonJetsonCsvCheck.result`에서 검사한다. 아래 실서버 예측→진단 시험은 이전 경로의 기록이며 현재 CSV 요청의 완료 증거가 아니다.





- `IonGatewayCheck.result`: 주입 완료값/단위/검사 식별/예측→진단 형식/원인·보정안 파싱과 후보 원문 보존에 대한 오프라인 검사.

- `GatewayRequestCheck.result`, `GatewaySnapshotCheck.result`: 기존 산화막 요청·단위 환산 회귀 검사.

- 기존 비동기 TCAD 계약 및 로컬 WebSocket 인증·분할 수신·재접속 시험도 통과했다. 로컬 모의 시험은 실제 서버의 진단 완료를 증명하지 않는다.

- `IonIntegration/summary.json`: 실제 Gateway에 보낸 **별도 통신 시연 한 건**의 결과. Unity에서 공정 버튼을 눌러 수행한 실측/런타임 사이클 시험으로 기록하지 않는다.



실서버 시연:



| 항목 | 값 |

|---|---|

| RUN | `9c6137ea-5a91-4f20-8a03-2e14602b9434` |

| 예측 request_id | `b72ffebb-5fa6-4256-9576-79bc4f86883f` |

| 예측 job_id | `b596a4bc-87e7-44cb-94a7-cb812fea08f5` |

| 예측 결과 이벤트 | `919fe538-c9b3-596e-a846-9661759f9742` / sequence 60 |

| 결과 | Vth 2.2600605 V / gm 4.599146 uS/um / id_on 5.207199 uA/um / BV 41.115015 V |

| DB 확인 | 같은 이벤트가 GET /api/v1/events에서 다시 조회됨 |

| 진단 request_id | `52ca0832-3b9a-4155-be5f-7f541ecb7bb3` |

| 진단 job_id | `fe6f68a9-e61a-4efe-80a1-173d634331d2` |

| 진단 상태 | 마지막 조회 `queued`, `result_event_id=null`. 완료 이벤트 미수신. |



Gateway 담당자에게는 위 진단 job의 **dispatch → ROS → diagnosis Worker 수신 → task_type 매핑 → 모델 응답 → 결과 이벤트 DB commit**을 확인해 달라고 전달한다. Unity 요청은 이미 접수되었으므로 같은 작업을 다시 만들지 않는다.



재생·요청·접수·DB 조회 자료는 `IonIntegration/`에 보관한다. `Test-IonIntegration.ps1`은 완료된 기존 시험을 중복 제출하지 않도록 active.json이 있으면 새 전송을 거절한다. `-ReplayOnly`는 진단 완료 파일이 확보된 뒤 결과만 다시 구독한다. 토큰은 프로세스 환경변수 `UNITY_GATEWAY_TEST_TOKEN`으로만 전달하며 파일에 저장하지 않는다.

