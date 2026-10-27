# 설비 검사 → Gateway → 결과 자동 수신

> 2026-10-22 전체 사이클 변경: 산화막·이온주입 자동 검사는 사용자 제공 `full_cycle_probe.py`와 같은 예측 → Gateway 진단 → 조건부 TCAD 이벤트 수신을 사용한다. [현재 흐름과 시험 방법](FullCycleTest/README.md)을 우선한다. 과거 직접 진단/후보 전송 기록은 현재 자동 경로와 구분한다.

## 사용

1. Play 시작 → 공정 분석 창의 `Gateway DB 결과` → `검사 전송·결과`.
2. Gateway 주소와 요청용 토큰을 입력한다. 토큰은 메모리에서만 사용하며 씬·요청 파일에 저장하지 않는다.
3. `자동 검사 연동 시작`을 누른다.
4. 기존 설비 모니터의 `검사`를 실행한다. 정상·NG 모두 완료 후 자동 요청한다.
5. 동일한 요청의 DB 완료 이벤트를 수신하면 결과가 이 창에 표시된다.

검사값 수동 입력칸은 없다. 검사 시작 시 LOT 조건·주소·요청 ID를 고정하고, 검사 완료 시 그 검사의 3지점 두께를 가져온다.
목표 두께나 예시 두께로 대체하지 않는다. 같은 검사 완료 콜백을 여러 번 받아도 중복 전송하지 않는다.

## 서버로 보내는 값

현재 시연 기준은 산화막 60 nm(0.06 µm), 도즈 7.7e12 cm⁻², 에피 도핑 1.7e16 cm⁻³이다.
Gateway의 입력 정규화와 실제 prod 예측 응답으로 확인했다.

- CSV 시연 `body_dose`: 기준 도즈 × 해당 검사에 고정된 CSV 행의 dose_ratio.
- CSV 시연 `epi_doping`: 기준 에피 도핑 × 같은 행의 epi_ratio.
- `oxide_thickness`: 완료된 3지점 두께의 평균(nm) ÷ 1,000, µm. 예시값으로 대체하지 않는다.
- CSV를 사용하지 않는 검사는 해당 LOT의 등록 도즈·에피 조건을 사용한다.

LOT 기준은 `Assets/MOSFETInspection/Resources/GatewayLotConditions.json`에 등록한다.
다른 LOT는 별도 조건이 없으면 전송을 보류한다.
CSV 기준 두께와 LOT 모델 기준 두께가 다르면 전송을 차단한다. 이전 100 nm 기준 선택을 재사용하지 말고 새 시험 웨이퍼를 준비한다.

설비 두께 시연 판정은 기존 ±5% 규칙을 유지해 57–63 nm로 설정했다. 이는 시연용 두께 규칙이며 TCAD의 실제 생산 규격을 새로 정한 것이 아니다.
전기특성 판정은 기존 Vth 1.7–2.6 V, BV ≥40 V를 유지한다. gm·Id는 진단 관측값이다.
현재 설비 검사는 CSV/시뮬레이션 출처이며 요청 provenance에 이를 명시한다.
원본 3지점·검사 ID·CSV 배율·기준 출처를 함께 기록한다. 장비 자동계측 하드웨어 연결과는 별개다.

## 2026-10-21 정합 검증

실제 Gateway 요청 4건에서 모두 `status=succeeded`, `result_origin=prod`를 확인했다.
이는 ML 예측 성공이며 별도의 TCAD 재시뮬레이션·보정 승인 완료를 뜻하지 않는다.

| CSV | 확인 시나리오 | Vth (V) | BV (V) | RUN ID |
| --- | --- | --- | --- | --- |
| B001 | 정상 | 2.2601 | 41.1150 | 599fe14d-8199-41e0-bce8-123f4c5c4f98 |
| B132 | 두께 NG / 전기특성 OK | 1.9139 | 47.1582 | 6bc99e14-93d2-4946-8931-ef7abeacdd14 |
| B081 | 두께 PASS / Vth NG | 3.2733 | 50.4463 | 678ba9de-6d72-4573-be3e-148ce8a5b6f7 |
| B038 | BV NG | 2.2613 | 36.5446 | 47075a8d-11ff-4613-b6b8-f51fbde327e3 |

요청·접수·완료 원문: `Tools/Gateway/AlignmentChecks/`.
Unity 장면의 레시피와 요청 생성값도 이 네 실제 요청과 대조해 통과했다 (`GatewayTcadAlignmentCheck.result`).
이 Editor 점검은 서버에 새 작업을 보내지 않는다. 화면에서 새 3D 검사 전체를 직접 조작한 검증과는 구분한다.
새 Play에서는 CSV 연결 창을 유지하고 데이터를 받은 뒤 Gateway 자동 연동을 시작한다. 새 시험 웨이퍼로 기존 설비의 검사를 실행한다.

## 연결과 결과

- 요청: 같은 Gateway 호스트의 `/api/v1/control`, `X-Unity-Token` 헤더.
- 결과: `/api/v1/stream?run_id=<현재 요청의 RUN UUID>&after_sequence=<처리 순번>`.
- 요청 형식: `surrogate.requested`, `fab-ml-v1`, process_parameters와 requested_outputs.
- 각 검사마다 request_id와 run_id를 생성한다. 결과 수신 연결을 먼저 연 다음 요청한다.
- `request.accepted / queued`는 접수이며 분석 완료가 아니다.
- run_id·request_id·LOT·job_id, 제공되면 unit_id까지 맞는 완료 이벤트만 사용한다.
- 결과 Vth/BV는 V, gm은 µS/µm, id_on은 µA/µm로 표시한다. 서버의 마이크로 단위 값에 10⁶을 다시 곱하지 않는다.
- 이전 `id` 필드는 id_on으로 자동 대응하지 않으며 단위 미확인으로 표시한다.
- mock은 시험값으로 표시한다. 기존 LOT 판정·HOLD 해제·TCAD 승인·레시피를 자동 변경하지 않는다.
- Gateway는 공정조건으로 전기특성을 예측한다. 기존 진단 워커는 같은 검사에 고정된 CSV 전기특성으로 원인·보정안을 별도 계산한다. 이상 검사당 진단 요청은 한 번만 전송하며, Gateway 상태는 LOT 진단 표시를 덮어쓰지 않는다.

실제 ML 원본은 비율 입력 및 A 단위 출력이다. Gateway/Worker의 물리값↔모델 변환은 서버 측 계약에 맞아야 한다.
Unity는 사용자가 전달한 외부 통신 단위를 사용한다. 모델 지원 영역 밖이라고 임의로 측정값을 바꾸지 않는다.

## 기록과 점검

요청: `Tools/Gateway/Requests/<request_id>.json`.
수신 결과 또는 종료 상태: `<request_id>.result.json`.
토큰은 이 파일들에 포함하지 않는다.

연결 오류/응답 유실 때 새 ID로 자동 재전송하지 않는다. 180초 후 미확정으로 종료하며 저장된 ID로 서버 기록을 확인한다.
Play 종료 이후의 미완료 요청도 서버 기록 확인이 필요하다.
최대 8개 검사를 순서대로 처리하며, 기록은 이번 Play에서 최대 32개 보관한다.

`GatewaySnapshotCheck.once`는 다음 가져오기 후 오프라인 자동 점검을 실행한다.
결과: `GatewaySnapshotCheck.result`. 측정 평균 사용, 단위 환산, 데이터 고정, LOT 격리, 미등록 LOT 차단을 검사한다.
이 오프라인 점검은 팀원 서버에 요청을 보내지 않는다.
이전 읽기 전용 시험 RUN의 sequence 39는 mock 고정값이며 실제 모델 결과가 아니다.

## 분석 실패·결과 없음

2026-10-21 실제 자동 요청 `e71dc350-bb13-440a-9565-08be15a0faed`의 왕복을 확인했다.
RUN `8eacb6a1-f651-4e96-864c-047cf7df3d8c`, sequence 42에서 서버는
`status=failed`, `error_code=OUT_OF_DOMAIN`, `result_payload=null`을 반환했다.
측정 평균 98.619995 nm → 0.098619995 µm 환산은 맞으며,
서버 정규화 결과는 dose=1, epi=1, tox=1.643667이었다. 따라서 모델의 입력 범위 검사를 통과하지 못했다.

이 응답은 전기특성 0 또는 제품 NG라는 뜻이 아니다. 예측값이 없는 서버 실패다.
Unity JsonUtility가 null 객체를 0으로 채우던 문제를 보완해, 실패/누락/빈 결과는 예측값으로 사용하지 않는다.
부분 결과의 누락 필드는 `—`로 표시한다. 정상 응답에 명시적으로 포함된 숫자 0은 그대로 보존한다.
오류 코드·메시지·서버 입력 배율을 결과 기록과 UI에 표시한다.
`GatewayNullResultCheck.once` → `GatewayNullResultCheck.result`는 실제 실패 응답을 오프라인 재생해 검증한다.
모델 범위 문제는 설비 시연 기준과 서버 모델 기준을 정합해야 해결되며, Unity가 측정값을 임의로 잘라내거나 바꿔 통과시키지 않는다.

## 보정 후보 Gateway 전달

진단 완료 후 후보를 같은 Gateway에 추가 접수하고, 그 후보의 prod 예측 결과가 담긴 DB 이벤트를 확인한다. 전달 조건과 Gateway 팀원용 필드 매핑은 Tools/TCAD/README.md를 따른다. 이전 Outbox 파일 전달 방식은 현재 주 경로가 아니다. Unity에서 TCAD 서버 직접 호출은 하지 않는다.
