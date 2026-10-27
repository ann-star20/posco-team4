# Unity Gateway 전체 사이클

기준: 사용자가 제공한 `C:/Users/Administrator/Desktop/full_cycle_probe.py`.
실행 대상은 산화막·이온주입 검사의 Gateway 자동 연동이다. 실제 서버 시험 결과와 로컬 fixture 결과를 구분한다.

## 현재 요청 순서

1. 완료된 검사 공정값으로 `/api/v1/control`에 `surrogate.requested`를 한 번 보낸다.
   - 도즈 cm^-2, 에피 cm^-3, 산화막 µm. 산화막 화면의 nm는 기존 완료 검사 변환에서 1000으로 나눈다.
   - 기존 검사 원본·판정은 `input_payload.provenance.inspection_result`에 보존한다. 이 값과 새 ML 예측은 서로 덮어쓰지 않는다.
   - 요청 접수 ACK는 완료가 아니다. 같은 RUN의 `surrogate.completed`를 기다린다.
2. 설비 검사와 새 전기특성 예측이 OK이고 기존 전기특성에 확인된 NG가 없으면 결과만 남기고 진단·후보를 생략한다. 기존 CSV 전기특성이 없는 Pending은 NG가 아니며, 서버 예측이 완료될 때까지 정상 판정을 보류한다.
   어느 하나가 NG거나 예측 BV가 미확인인 경우 새 예측값을 `measurements`에 그대로 넣어 `diagnosis.requested`를 한 번 보낸다.
   - `gm` µS/µm, `id_on` µA/µm. 이미 마이크로 단위인 예측에 1e6을 곱하지 않는다.
   - `n_wafers=1`, `refine=false`. 한 번의 예측을 CSV 25/100장 평균으로 가장하지 않는다.
   - 같은 `run_id`, 새 `request_id`, 같은 LOT/unit. `stage_id=diagnosis`.
   - 제공된 Gateway probe와 동일하게 Unity 요청에는 `task_type`을 추가하지 않는다. Worker가 모델 서비스에 `task_type=diagnosis`를 전달할 책임을 갖는다.
3. `diagnosis.completed`의 `result_payload.compensation.route`를 그대로 따른다.
   - `tcad_verify`: Gateway가 자동 접수한 TCAD 이벤트를 수신한다. Unity가 별도의 후보 surrogate 요청이나 TCAD HTTP 요청을 만들지 않는다.
   - `apply`: 보정안 표시, 담당자 승인 대기. Unity 자동 적용 없음.
   - `no_action`: 추가 보정 없음.
   - `manual`: 담당자 검토.

기존 직접 Jetson 진단 워커는 이 Gateway 관리 검사의 자동 경로에서 제외된다. Gateway 자동 연동을 켜지 않은 기존 수동 시험 경로는 유지된다.

## 결과와 장시간 대기

- `/api/v1/stream?run_id=<RUN>&after_sequence=<sequence>`를 RUN별로 유지한다.
- TCAD 예상 시간은 약 20–30분. 90분 이후에도 늦은 이벤트 수신은 유지하며 응답 지연으로 표시한다.
- 후보별 `tcad_request_id`, `proposal_id`, `candidate_index`를 보존한다. 개별 성공을 배치 완료로 표시하지 않는다.
- `tcad.verification.candidate_queued/running/succeeded/failed/cancelled`, `batch_completed`, `review_required`를 처리한다.
- `batch_completed`는 배치 종료이며 모든 후보 성공·규격 합격·승인·레시피 적용을 뜻하지 않는다.
- 요청 실패/ACK 유실 시 무조건 재전송하지 않는다. 재접속은 마지막 sequence 이후 결과 수신만 재개한다.
- TCAD 대기 중에도 다른 검사의 독립 RUN을 처리한다. 미완료 작업 제한은 기존과 같은 8건이다.
- Unity Play가 유지되는 동안 재접속·이벤트 커서를 유지한다. Play 종료/앱 종료 시 수신은 종료된다. 다시 켰다면 저장된 RUN ID로 Gateway 기록을 재조회해야 한다.

## 확인 방법

로컬 계약 검사:
```powershell
$env:DOTNET_CLI_HOME = Join-Path (Get-Location) 'Temp/DotnetHome'
& 'C:/Program Files/Unity/Hub/Editor/6000.6.4f1/Editor/Data/DotNetSdk/dotnet.exe' build Tools/Gateway/FullCycleTest/Checks.csproj --ignore-failed-sources -p:UseAppHost=false -o Temp/Gateway/FullCycleChecks
& 'C:/Program Files/Unity/Hub/Editor/6000.6.4f1/Editor/Data/DotNetSdk/dotnet.exe' Temp/Gateway/FullCycleChecks/Checks.dll
```

Unity 실제 serializer/런타임 로컬 송수신 시험은 Play를 끈 상태에서 `GatewayFullCycleCheck.once` 파일을 만든다.
`GatewayFullCycleCheck.result`에서 `FULL_CYCLE_UNITY_JSON_OK`와 `FULL_CYCLE_RUNTIME_SOCKET_OK`를 확인한다.
이 시험은 별도 loopback fixture를 띄우며, 실제 GatewayInspectionBridge/GatewayStreamClient가 두 번 요청하고 sequence 3에서 연결이 끊긴 뒤 sequence 4부터 복구해 배치 완료를 받는지 검사한다. 실제 Gateway, DB, 모델, Silvaco를 실행한 증거는 아니다.

장면 검사: `FilmGatewayFlowCheck.once`, `IonNormalWireCheck.once`는 순서대로 실행한다. 두 테스트 모두 네트워크 sender를 비활성화한 뒤 실제 완료 검사 DTO와 분기를 확인한다.

원문 감사 기록은 `Tools/Gateway/Requests/<예측 request_id>.events.jsonl`에 남는다. 토큰은 저장하지 않는다.
