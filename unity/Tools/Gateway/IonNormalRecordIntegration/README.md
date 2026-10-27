# 정상 이온주입 검사 기록 DB 확인 (2026-10-22)

Unity의 전용 NormalRequest 직렬화로 만든 정상 CSV 시연 기록 한 건을 실제 Gateway에 보냈다. 주입량과 같은 CSV의 전기특성 모두 OK인 기록이다. 센서 실측이나 Unity 공정 버튼의 전체 실시간 네트워크 시험은 아니다.

- request_id: `d1c56698-2b32-49d1-af09-1baef16d19c4`
- run_id: `c47b5ee1-703b-4df2-838d-9547211ac018`
- job_id: `f6f58111-0107-4c0b-bee7-a8557281cf35`
- event_id: `a8f41961-a864-59e9-8e19-9b82552750c1` / sequence 202
- 상태: `completed`
- type: surrogate.requested / stage_id: ion_inspection_record
- DB 이벤트 API로 같은 이벤트를 다시 읽고 provenance.inspection_result 전체를 원 요청과 비교해 일치를 확인했다.
- 주입량과 목표·허용 범위, 완료 시각, Vth·gm·id_on·BV와 단위, OK 판정이 보존됐다.
- diagnosis_requested=false, correction_candidate=false. 요청 JSON에 tcad 필드가 없다. 같은 RUN의 조회 이벤트에 진단·보정·TCAD 이벤트도 없었다.
- Gateway가 현재 지원하는 예측 작업 경로를 사용하므로 서버 ML 예측은 별도로 실행됐다. 예측값은 원 검사값이나 판정을 덮어쓰지 않는다.

request.json / accepted.json / event.json / db-replayed.json / job.json / summary.json이 실제 통신 증거다. preflight-* 파일은 전송 전에 잡힌 직렬화 문제의 과거 진단 자료이며, 그 요청은 서버에 보내지 않았다. active.json이 있어 시험을 다시 실행해도 중복 제출하지 않는다. 토큰은 저장하지 않았다.
