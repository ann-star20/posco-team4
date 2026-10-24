# 전기특성 판정 연결

- 규격 출처: 제공된 `진단에이전트.py`의 `SPEC` (28행). Vth 1.7–2.6 V, BV ≥40 V. 프로젝트 규격이며 양산 규격 인증은 아님.
- `ElectricalSpec`에서 두 경계 포함. 확인 가능한 항목이 하나라도 이탈하면 NG. Vth 통과 + BV 미수신은 대기. gm·Id 규격은 정의되지 않아 OK/NG에 사용하지 않음.
- ML 예측 판정과 두께 판정, Jetson 원인 진단(정상 후보/구분 불가)을 구분. 전기특성 OK가 두께 FAIL을 덮거나 HOLD를 자동 해제하지 않음.
- 현재 +9% 산화막 짝지어진 합성 사례는 Vth 약 2.483 V / 같은 사례 BV 약 42.248 V. BV 미포함 설정이므로 전체 전기특성 판정 대기. BV 포함 시 두 항목 OK여도 두께 FAIL 때문에 HOLD 유지.
- LOT에 값을 붙이는 수신 지점: `LotProcessAnalysis.ReceiveElectrical(source, inspectionId, input, hasBv)`. 현재 검사 ID·LOT·모델 기준이 일치하는 합성 입력만 받음. 전기특성 NG는 HOLD 및 기존 Jetson 분석 대기열로 연결. 필요한 값 누락은 HOLD/데이터 대기. 과거 검사·다른 LOT 입력 거절.
- 기존 +9% 두께 이상 시나리오는 검사 완료 시 전기특성 판정을 함께 기록. 정상 두께 데모에 전기값을 임의 생성하지 않음. 실제 TCAD 결과 수신/단위 변환이나 모델 예측 새 요청 프로토콜은 추가하지 않았음.
- 공통 분석창에는 해당 결과 입력의 전기 판정, 설비 LOT 모니터에는 해당 검사에 연결된 전기 판정을 표시. 저장 재생 결과에 입력이 없으면 판정 대기.
- 전기 NG/대기는 두께 재검사 PASS만으로 해제되지 않음. 새 유효한 전기 OK 입력이 있어도 기존 HOLD는 자동 해제하지 않음. 승인/레시피 적용은 기존과 같이 미구현.

검증: 독립 경계/누락값 검사 11건 통과. Unity Play 통합 검사 `ElectricalVerdictPlay.result`: 두께 PASS+전기 NG HOLD 및 분석 대기, BV 누락 보류, OK 자동 해제 금지, 과거 검사/다른 LOT 거절, 재검사 우회 금지 통과. 이 검사는 실제 Jetson/TCAD 실행이나 레시피 적용을 하지 않음.

## 설비 검사 시나리오 연결

- 엘립소미터 검사창 DEMO 버튼 순서: 기존 두께 PASS → 정상 + 전기 OK → 산화막 +15% → 기존 두께 +9% → 기존 LOW → 정상. 선택 후 Start scan/Remeasure 실행.
- 정상은 제공된 ProcessAnalysisSamples의 normal 전기특성을 해당 LOT/검사에 연결하고 전기 OK 표시. 원인 분석 자동 요청 없음.
- 산화막 +15%는 제공된 oxide_plus15 전기특성(Vth 약 2.630093 V, BV 미수신)과 시연용 두께 114.6/115.1/115.3 nm를 연결. Vth 규격 이탈로 NG/HOLD 후 기존 WebSocket으로 해당 LOT의 진단을 한 번 자동 요청. 두께 nm는 실제 TCAD 물리 보정값이 아닌 장면의 100 nm 기준 합성 시연값.
- 기존 +9%/LOW와 수동 TEST 시나리오는 유지. 검사 스냅샷과 선택한 시나리오/읽은 두께/기준이 다르면 HOLD/데이터 확인으로 처리.
- ElectricalScenarioLocal.result: PC 기본 GP + 실제 로컬 WebSocket/Unity 검사 애니메이션으로 정상→LOW→+15% NG→동일 LOT 새 분석 수신 통과. Jetson 재실행 및 실제 TCAD 검증은 이번 검사에 포함하지 않음.
