# 산화막 검사: 원 검사 기록과 NG 진단·보정 후보

> 2026-10-22 이후 현재 자동 흐름은 [전체 사이클](FullCycleTest/README.md)이다. 기존 원 검사 기록을 보존하면서 예측 → Gateway 진단 → 조건부 TCAD 이벤트 수신으로 연결한다. 아래의 직접 진단·별도 후보 전송은 이전 구현 기록이다.

## 흐름

1. 완료한 검사에 고정된 3지점 두께와 같은 CSV 전기특성을 판정한다.
2. 원 검사값·판정은 항상 Gateway로 보낸다. 둘 다 OK면 진단·보정 후보는 생략한다.
3. 두께 FAIL 또는 전기특성 NG이면 기존 Jetson 직접 진단을 요청하고, 실제 진단 응답의 보정 후보를 별도로 Gateway에 보낸다. 원 검사와 후보는 같은 RUN/검사 ID로 연결한다.
4. 필수 전기특성이 누락되면 정상으로 간주하지 않는다. 기존 HOLD는 OK나 진단 완료만으로 자동 해제하지 않는다.

## Gateway 구분

- 원 검사: type=surrogate.requested, stage_id=film_inspection_record
- 원 검사값·판정: input_payload.provenance.inspection_result
- purpose=film_inspection_record, verdict=OK/NG/PENDING
- thickness_points_nm, thickness_mean_nm, target_nm, lower_nm, upper_nm
- electrical: vth_v, gm_us_per_um, id4v_ua_per_um, bv_v, has_bv. gm/Id는 CSV SI 값에서 정확히 한 번 마이크로 단위로 변환한다. current_quantity=id4v를 보존한다.
- diagnosis_requested는 원 검사 NG 진단 요청 대상 여부이며 진단 완료를 뜻하지 않는다. correction_candidate=false.
- 원 검사 요청에는 tcad 필드가 없다. Unity가 null 중첩 클래스를 기본 내용으로 직렬화하는 문제를 피하려고 별도 wire 타입을 사용한다.
- 보정 후보는 기존 stage_id=tcad_candidate_prediction, provenance.tcad.purpose=tcad_candidate_prediction_for_gateway_forwarding으로 구분한다. 정상 검사에서는 생성·수동 전송 모두 차단한다.

현재 Gateway에는 결과 보관 전용 API가 없어 기존 surrogate 요청 경로를 사용한다. 서버 ML 예측은 원 검사값·판정과 별도이며 원본을 덮어쓰지 않는다. 요청 접수만으로 완료라고 표시하지 않고 같은 요청의 완료 이벤트를 확인한다. TCAD 검증·엔지니어 승인·레시피 적용은 별도이다.

## 검증

FilmGatewayFlowCheck.result는 정상/두께만 NG/전기특성만 NG/둘 다 NG의 오프라인 검사와 직접 응답 fixture 연결 결과이다. 실제 서버 요청을 보내지 않는다.
Temp/FilmGateway/film-normal-live.request.json은 Unity가 만든 정상 시험 요청이다. Test-FilmRecordLive.py로 한 건만 전송해 FilmNormalRecordIntegration/에 접수·결과·DB 재조회 증거를 보관한다. active.json은 중복 전송을 막는다. 센서 실측이나 Unity 버튼에서 실제 서버까지의 전체 실시간 시험과 구분한다.
