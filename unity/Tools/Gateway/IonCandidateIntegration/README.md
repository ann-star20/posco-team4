# 이온 보정 후보 Gateway 실서버 확인 (2026-10-22)

Unity의 GatewayTcadProtocol.BuildIon으로 만든 후보 한 건을 실제 Gateway에 전송했다. 저장된 실제 Jetson B122 직접 진단 응답을 사용했으며 새로운 센서 측정이나 Unity 공정 버튼의 실시간 네트워크 전체 시험은 아니다.

- request_id: `fa39e01d-b768-4c81-8e30-4ae01141531a`
- run_id: `f47418b8-c034-465c-9207-b9034ac62935`
- job_id: `08a21f0d-2dbf-4f52-9074-9c6b2725c0aa`
- event_id: `cdab5a72-4f27-55f0-a2b5-a12576354243` / sequence 68
- type: surrogate.requested / stage_id: tcad_candidate_prediction
- 상태: completed. 같은 surrogate.completed 이벤트를 DB 이벤트 API에서 다시 조회했다.
- DB 재조회에서 후보 공정값과 provenance.tcad.direct_diagnosis의 원인·진단 요청 ID·보정 계수를 대조했다.
- 후보 예측: Vth 2.356173 V, BV 36.769180 V. BV 40 V 미달이므로 후보는 전기특성 규격을 충족하지 않는다. 통신 성공을 품질 합격으로 해석하지 않는다.
- TCAD 실행·승인·레시피 적용은 하지 않았다. 원인 불확실 후보이므로 검토 자료로 전달한다.

요청, 접수 응답, 수신 이벤트, DB 재조회 원문, 작업 상태는 이 폴더의 JSON 파일에 보관한다. 토큰은 보관하지 않는다. active.json은 중복 전송 방지 기록이며 시험 스크립트를 다시 실행해도 새 후보를 보내지 않는다.
