# 실제 Jetson 직접 진단 및 Gateway 요청 보관 시험

2026-10-22, CSV B122, 웨이퍼 1장 조건의 별도 통신 시험이다. Unity 전체 공정 런타임 검사는 IonJetsonCsvCheck.result의 오프라인 자료와 구분한다.

- 직접 진단: REQ-1cc32b2fafff450ca187d88df9d995f8
- 실제 GP+TabPFN 계산: 25.84초
- 원인 후보: 도즈+에피+산화막, 확률 47.24%, 판정 불확실
- 후보: 도즈 ×0.955 / 산화막 ×0.970 / 에피 변경 없음
- 권고: 웨이퍼 1장 → 4장
- Gateway request_id: 548d8c70-5d31-41d0-ae4a-1c87b364db3e
- Gateway job_id: 97d0fffd-ff49-4d13-b438-d99f02d6a527
- Gateway run_id: f47418b8-c034-465c-9207-b9034ac62935

request.accepted와 GET /api/v1/jobs 조회로 해당 요청 접수를 확인했다. 직접 결과 전체는 gateway.request.json의 input_payload.provenance.direct_diagnosis에 담았다. Gateway 작업 자체는 queued이며 이를 서버 diagnosis.completed 이벤트라고 기록하지 않는다.

실제 직접 응답은 direct.result.json, 송신 입력은 direct.request.json, 원문 포함 저장 요청은 gateway.request.json, 접수·조회는 gateway.accepted.json 및 gateway.status.json에 있다. 토큰·비밀번호는 저장하지 않았다.
