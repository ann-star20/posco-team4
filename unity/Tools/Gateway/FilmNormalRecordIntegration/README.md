# 산화막 정상 검사 Gateway 시험 (2026-10-22)

Unity가 생성한 B001 정상 CSV 시연 기록 한 건을 실제 Gateway에 전송했다.

- request_id: `f4db3967-3564-4a9f-8e09-a2bad34222c7`
- run_id: `023f73d3-15bf-402a-b9e9-bdec7779466f`
- job_id: `53e07162-cb23-474b-8a69-95d6158e1f7d`
- stage_id: film_inspection_record
- request.accepted / queued를 받았고 작업 조회에서도 동일 ID의 queued, result_event_id=null을 확인했다.
- 90초 동안 완료 이벤트가 오지 않았고 이벤트 API는 빈 목록이었다. 원 검사값·OK 판정의 DB 본문 재조회는 아직 확인하지 못했다.
- 요청에는 3지점 두께, 평균, 목표·허용 범위, 동일 CSV의 전기특성·단위, OK 판정, diagnosis_requested=false, correction_candidate=false가 있다. tcad 필드는 없다.
- Gateway 담당자가 이 job의 dispatch → surrogate worker 수신 → 결과 DB commit을 확인해야 한다. 같은 작업을 새로 제출하지 않는다.

Unity 오프라인 FilmGatewayFlowCheck.result는 정상/두께만 NG/전기특성만 NG/둘 다 NG와 검사·진단·후보 연결을 통과했다. 이는 현재 서버 완료의 증거가 아니다. active.json은 중복 제출을 차단한다. 토큰은 저장하지 않았다.
