# Unity TCAD 후보 승인 연결

## 실행 흐름

Gateway WebSocket 진단 요청은 `type: diagnosis.requested`로 구분하며 `task_type`을 포함하지 않는다. 현재 Gateway DiagnosisRequest는 추가 필드를 거절한다. Jetson 모델 서비스로 직접 요청하는 계약의 `task_type: diagnosis`와 구분해야 하며, Gateway에서 Jetson으로 전달할 때 Worker가 이를 설정해야 한다.

1. 기존 RUN stream에서 `tcad.verification.review_required` 수신.
2. Unity가 `GET /api/v1/tcad/proposals?status=review_required`를 호출하고 RUN 및 진단 JOB이 일치하는 그룹만 표시.
3. 사용자가 후보 선택, 승인자명 입력, 관리자 승인 요청 또는 반려 선택. 별도 **관리자 승인 필요** 창에서 지정한 시연 비밀번호 확인 후에만 전송.
4. `POST /api/v1/tcad/proposals/{proposal_id}/decision` 전송. 토큰은 실행 중 입력한 값만 사용하며 파일에 저장하지 않음.
5. 승인 응답의 proposal_id와 세 공정값이 선택 후보와 일치하고, 이벤트의 실행 모드(real/live/prod)와 approval_allowed=true가 확인된 경우에만 설정 적용. fake/mock 또는 모드 미확인은 승인 API 시험으로 구분하여 설정 미적용. 두 설비 중 하나라도 동작 중이면 정지까지 대기.

TCAD 배치 완료 후에도 승인 결정 전까지 RUN stream을 유지한다. 분석 창의 **TCAD 후보 승인** 버튼으로 다시 조회할 수 있다.

## 단위 및 적용 범위

| 필드 | Gateway 단위 | Unity 반영 |
|---|---|---|
| body_dose | cm^-2 | 이온주입기 targetDose |
| epi_doping | cm^-3 | 레시피 정보 보관. 현재 장면에는 에피 액추에이터 없음 |
| oxide_thickness | µm | 산화로 targetOxideNm = 입력 × 1000 |
| gm / id_on | µS/µm / µA/µm | 결과 표시. 합격 판정에는 사용하지 않음 |

예: 0.06375 µm → 63.75 nm. 예시의 45.2를 받으면 45200 nm이며 임의로 45.2 nm로 해석하지 않는다.

적용은 시뮬레이션의 공정 설정 변경이다. 기존 CSV 측정값, 기존 검사 기록, 검사 허용 범위, HOLD를 수정하지 않는다. CSV 재생 모드의 전기특성이나 완료 주입량이 승인값에 맞게 새로 계산되는 기능은 아니다. 이후 새 측정/모델 요청/TCAD 결과와 구분한다.

## 실패 및 동기화

- 관리자 비밀번호는 Unity 로컬 시연용 확인이다. Gateway 관리자 계정/권한 인증을 추가한 것은 아니다.
- 비밀번호 입력은 마스킹하며 요청 JSON·승인 기록에 포함하지 않는다. 비교용 PBKDF2 값만 런타임 코드에 보관한다.
- 확인은 RUN·그룹·선택 후보·공정값·승인자·결정에 묶인 일회성 확인이다. 취소, 오입력, 재승인, 후보 변경 때 다시 확인한다.

- 후보 정상/불가는 서버 spec_verdict.overall만 사용한다. in_spec은 정상이고 나머지는 불가이며 Unity에서 Vth/BV로 재계산하지 않는다. 최초 검사/예측 자체의 전기특성 판정과 구분한다.
- 정상 후보가 하나 이상이면 해당 후보를 선택해 관리자 승인. 전부 불가이면 승인 버튼 비활성화 및 반려 안내. 반려도 사용자가 확인하며 자동 API 전송하지 않는다.
- 공정값 누락·비정상 수치, 후보 ID·승인 응답 값 불일치는 별도 전송/적용 검증이다. 품질 판정 값을 변경하지 않는다.
- fake/mock 후보는 시험 결과로 표시한다. 승인 API 시험 버튼은 통신 확인용이고, 성공 응답이 와도 GatewayApprovedRecipe에 전달하지 않는다. 실제 TCAD 계산 모드가 fake로 명시된 후보도 적용하지 않는다. 알 수 없는 실행 모드에서는 실제 적용하지 않는다.
- 다른 RUN·진단 JOB의 후보는 표시하지 않음.
- 반려는 공정값 미적용.
- POST 실패/응답 유실은 접수 불확실 상태로 남기며 자동 재전송/적용하지 않음.
- 원문 응답과 RUN·LOT·선택 후보 연결은 `Tools/Gateway/Approvals/`에 보관.
- 다른 클라이언트의 decided 이벤트는 선택 후보 ID·승인자·공정값이 명확히 확인될 때만 적용. 실제 decided payload 계약이 확인되지 않은 상태에서 값을 추측하지 않음.
- Play를 종료하면 실행 중 세션과 적용 상태는 초기화될 수 있음. 파일 보관은 자동 복원 기능을 뜻하지 않음.

## 확인 결과 (2026-10-23)

- 런타임/에디터 컴파일 성공.
- 실제 Unity JsonUtility와 비활성 시험 설비를 사용한 `GatewayApprovedRecipeCheck.result`: APPROVED_RECIPE_CORE_OK.
- µm 변환, 동작 중 적용 대기, 원 검사값/규격 유지, 다른 RUN 차단, NG/BV 미확인 후보 차단, 후보와 승인 응답의 값 비교, 반려 요청 형식, 중복 적용 방지 점검 통과.
- 별도 .NET 프로토콜 검사 FULL_CYCLE_CONTRACT_OK. 배치 완료 후 승인 수신까지 stream 유지 조건 포함. 이 검사는 실제 Unity 송수신 시험과 구분.
- 실제 Gateway `192.168.11.237:8000`: health 200, 검토 후보 조회 200, proposals=[] 확인.
- 실제 서버에 승인/반려 POST를 전송하지 않았으므로 실제 후보의 승인부터 적용까지는 미검증.

## 진단 접수 오류 복구 (2026-10-23)

- 기존 요청 38ff737a-5178-4902-b1d0-e20fb28d7262에 task_type이 포함되어 실제 WS 응답 request.rejected / invalid_request 재현.
- 같은 요청 ID와 검사값에서 task_type만 제외한 요청은 request.accepted 반환. JOB 7c9f13a4-91af-40f0-beee-4911d97283f3.
- DB 작업 조회 status=completed, 같은 RUN의 diagnosis.completed와 compensation.route=tcad_verify 확인.
- 이벤트의 unity_mode=mock, approval_allowed=false도 확인. 실제 승인 가능 여부는 Gateway 운영 설정 확인 필요. TCAD 완료 또는 보정 승인 성공을 뜻하지 않는다.
- 원문 증거: Tools/Gateway/DiagnosisRecovery/. Unity는 이후 새 요청의 ACK를 *.ack.json에 보관하며 거절 코드가 있으면 화면에 표시한다.

## 정상 검사에 진단이 붙던 분기 수정 (2026-10-23)

- 확인 기록: surrogate request b96a51f4-a584-48b4-a1c6-4395f823c7a1 / RUN 032ff867-1fcf-4bba-a052-331cf97fb7b0.
- 두께 60 nm, 예측 Vth 2.260060537596672 V, BV 41.11501514951402 V로 정상. 기존 CSV 전기특성이 없어 원본 electrical_verdict는 Pending이었다.
- 이전 코드가 Pending을 OK가 아니라는 이유로 NG와 동일하게 취급해 불필요한 diagnosis.requested를 생성했다.
- 원본 전기특성의 확인 여부를 별도로 전달하여 수정. Pending은 NG로 단정하지 않으며, 예측 수신 전에는 정상 완료/스토커 자동 출고도 허용하지 않는다.
- 설비 검사 OK + 예측 전기특성 OK + 원본에 확인된 NG 없음이면 진단·후보 생성 생략. 설비 NG, 확인된 원본 전기특성 NG, 예측 NG/BV 미확인은 기존 진단 흐름 유지.
- 이미 서버에 생성된 진단·TCAD 후보 기록은 삭제하거나 정상 기록으로 덮어쓰지 않는다. 새 검사부터 수정된 분기를 사용한다.
