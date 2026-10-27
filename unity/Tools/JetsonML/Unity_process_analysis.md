# Jetson → Unity 공정 분석 표시

합성 입력의 **저장 결과 재생**과 **Unity 요청에 따른 새 진단 계산**을 구분한다. 실제 계측·TCAD 실행·승인·레시피 적용은 포함하지 않는다.

## 현재 Jetson 재연결 (2026-10-21)

- 대상: 192.168.213.167. 모델 위치 확인 파일에는 확인한 target도 저장한다.
- `check-process-model.cmd`로 현재 장비의 모델·Python 위치를 확인한 뒤 `start-jetson-process-worker.cmd`를 실행한다.
- 이전 주소의 inventory는 재사용하지 않는다. 검증한 gp 해시 및 전체 에이전트 파일 지문을 유지하며 다른 모델로 자동 대체하지 않는다.
- `PROCESS_MODEL_VERIFIED`, `PROCESS_WORKER_CONNECTED`가 나온 창을 유지한다.
- Gateway 전기특성 예측과 기존 진단은 별도 경로다. Gateway 연동 중인 이상 검사도 같은 검사에 고정된 CSV 전기특성으로 기존 진단을 한 번 요청한다.
- Gateway 통신 상태가 LOT의 원인분석 진행·완료 표시를 덮어쓰지 않는다. 진단 결과는 TCAD 미검증·미적용 상태를 유지한다.
## 요청할 때 새로 계산하는 모드 (2026-10-19 추가)

### 동일 산화막 사례의 BV 유무 비교

`Editor/OxideBvComparison.cs`와 `OxideBvComparison.once`로 현재 HIGH 합성 사례(도즈 1, 에피 1, 산화막 1.09)를 비교했다. 동일 Vth/gm/Id, 동일 5장 가정, 동일 기준/에이전트 버전에서 BV 제공 여부만 다르게 요청했다. 실제 Jetson의 새 GP+TabPFN 계산 결과: BV 없음은 에피+산화막 40.9926%(구분 불가, 21.17초), BV 42.24754 V 제공 시 산화막 56.8705%(구분 불가, 21.24초). 최다 후보는 주입 원인인 산화막으로 바뀌었으나 70% 판정 기준에는 미달했다. 서로 다른 후보의 최다 확률이므로 같은 후보 확률이 15.88%p 증가했다고 해석하지 않는다. 입력은 GP 생성 합성값이며 독립 TCAD 검증·실측 성능 시험이 아니다. 판정 기준·모델·레시피·HOLD·AOI는 변경하지 않았다.

전체 결과와 요청 식별자는 `Tools/JetsonML/BVComparison/result.json`, 개별 결과는 `without-bv.json` / `with-bv.json`, 요약은 `comparison.md`에 저장했다. BV 미제공은 내보낸 JSON에서 null로 기록하며 실제 0 V 측정값으로 취급하지 않는다.

### 두께 이상에서 자동 요청 (LOT별 연결)

엘립소미터의 `EvaluateInspection()`에서 FAIL이면 기존 기능대로 LOT HOLD가 먼저 설정된다. 새 검사마다 독립적인 검사 ID를 발급하고, LOT ID·검사 ID·측정 3점·목표/허용 범위를 스냅샷으로 보관한다. 같은 검사에서 평가가 반복돼도 자동 분석은 한 번만 요청한다.

- 기본 `Demo: HIGH / FAIL`의 108.6 / 109.1 / 109.3 nm, 목표 100 nm, 허용 95–105 nm에만 대응하는 합성 전기특성을 `Resources/FilmAnomalyScenario.json`에 준비했다.
- 전기특성은 검증된 기본 GP의 `[도즈=1, 에피=1, 산화막=1.09]` 순방향 예측으로 생성했다. BV는 이 첫 시나리오의 진단 입력에서 제외한다. 장면의 100 nm는 시연 기준이며 실제 TCAD 소자 치수의 절대 보정값이나 실측값이 아니다.
- 해당 HIGH 데모 플래그와 측정 3점·목표·규격이 모두 일치해야 합성 데이터가 연결된다. LOW, 수정된 측정값·규격, 알려지지 않은 입력은 `HOLD · 분석 데이터 대기`이며 임의의 Vth/gm/Id/BV를 채우지 않는다.
- 준비된 요청은 Jetson 수신기 연결과 이전 분석 완료를 기다린다. 실제 전송 실패·단절·시간 초과는 실패로 표시하며 자동 재전송하지 않는다. 연결 복구 후 새 검사를 실행할 수 있다.
- 응답은 LOT·요청·입력의 기존 검증을 통과해야 해당 검사 기록에 저장된다. 새 검사가 시작되면 이전 검사는 과거 기록이 되고, 늦게 온 이전 응답이 새 검사의 결과로 표시되지 않는다.
- 공통 창은 해당 LOT의 검사/분석을 보여주는 모드와 기존 수동 시험·전체 기록 모드를 구분한다. 설비의 표시 값은 전체 기록에서 선택한 결과와 독립적이다.
- 각 설비 탭의 `설비 모니터 · 이 LOT` 버튼: 엘립소미터는 계측/HOLD/분석 상태, 산화로는 산화막 제안, 이온주입기는 같은 LOT의 도즈 제안만 표시한다. 실제 온도·시간 레시피로 변환하거나 적용하지 않는다.
- 기존 엘립소미터·이온주입기 3D 모니터의 분석 요약도 해당 설비의 LOT ID로 조회한다. OHT 공정 시작 시 산화로·엘립소미터·이온주입기에 같은 LOT ID를 지정한다.
- PASS에는 자동 분석을 요청하지 않는다. ML 진단 완료는 HOLD 해제나 PASS 승인 사유가 아니다. 이온주입 차단을 유지하며, 기존 재측정 PASS 검토 해제 기능과 레시피 승인/적용은 별개다.
- 검사 이력은 Play 세션 내 최근 64건이다. 영구 감사 기록·엔지니어 승인·실제 TCAD 재검증은 이번 범위에 포함하지 않는다.

자동 연결 검사: `LotAutoAnalysisLocal.result`와 `LotAutoAnalysisJetson.result`. 정상은 요청 없음, 데이터 없는 LOW NG는 HOLD/대기, 짝지어진 HIGH NG는 자동 요청 1건, 검사·LOT·요청 일치, 중복 방지, 다른 LOT/수동 기록 선택의 표시 오염 방지, 이온주입 차단을 검사한다. 실제 Jetson 고정밀 첫 검사에서 새 계산 21.18초, 산화막 ×0.925·도즈 ×0.985 제안, 원인 구분 불가가 관찰됐다. 원인이 확정된 것으로 표시하거나 HOLD를 해제하지 않았다. 이후 표시/백그라운드 수신 보완은 별도 최종 검사로 확인한다.

최종 반영 확인: 2026-10-19 09:55:21 런타임 / 09:55:22 에디터 컴파일 후, 09:56:28 `LOT_AUTO_ANALYSIS_JETSON_PLAY_OK`를 다시 확인했다. 최종 표시·백그라운드 수신 코드가 포함된 실행에서 새 고정밀 계산 21.15초였고, 결과 화면을 확인했다. 제어 도구에서 Unity 창을 열거하지 못한 상황과 실제 Unity 컴파일·Play 검사 실행 여부는 구분한다.

`start-jetson-process-worker.cmd`는 기존 Jetson 고정밀 가상환경에서 요청 수신기를 계속 실행한다. 비밀번호는 파일 전송과 SSH 실행 때 두 번 직접 입력하고 창을 유지한다. 패키지 설치나 원본 모델 변경은 하지 않는다. 이전 저장 결과 전송용 CMD와 동시에 실행하지 않는다(같은 process_ai 역할 사용).

Unity의 `Jetson 원인·보정안 보기` 상단에서 정상 / 산화막 +15% / 에피 −40%(BV 없음·있음)를 선택하고 `Jetson 새 분석 요청`을 누른다. 첫 연결 후 수신기 상태가 표시되기까지 최대 5초 걸릴 수 있다. 버튼은 수신기가 연결됐을 때 켜진다.

- 입력은 `Resources/ProcessAnalysisSamples.json`의 **합성 전기특성**이다. AOI 외관 판정에서 전기특성을 만들지 않는다.
- `process_request`: Unity → process_ai. `request_id`, `lot_id`, `baseline_version`, `n_wafers`, `data_source=synthetic`, `measurement={vth,gm,id4v,bv}`. BV가 없으면 null. 단위는 V / A/V/um / A/um / V.
- `process_status`: process_ai → Unity. ready(5초마다 연결 상태), running 또는 failed. running/failed는 원래 request_id와 lot_id를 포함한다.
- `process_analysis`: 기존 규격에 `delivery=computed`, `request_id`, `input`(원래 요청 전체)을 추가한다. Unity는 자신이 기다리던 요청·LOT·입력과 일치하는 응답만 수용한다. 저장 결과는 기존처럼 replay로 구별한다.
- 요청마다 별도 Python 작업에서 모델·소스 해시와 기준 버전을 확인하고 **새로 계산**한다. 모델 초기화 시간도 결과 소요 시간에 포함된다. 한 번에 한 건, 작업 제한 180초, Unity 응답 대기 210초.
- 고정밀 사용 불가/계산 오류 시 기본 GP 결과와 사유를 표시한다. 기본 GP 자체 실패·잘못된 입력·기준 불일치·시간 초과는 완료로 꾸미지 않고 실패로 표시한다.
- 고정밀은 원인 후보를 재평가한다. 보정 배율은 제공된 진단 에이전트의 **기본 GP 사후분포 기반**이다. 고정밀에서 원인 후보가 바뀌면 추가 검토 경고를 표시한다.
- TCAD는 실행하지 않는다. `tcad_status=not_run`, `applied=false`이며 승인·적용·LOT HOLD·AOI 분류를 변경하지 않는다.
- 통신 단절 시 요청 상태를 불명/실패로 표시하고 자동 재요청하지 않는다. 재실행은 새 요청 ID로 한다. 수신기의 중복 방지는 현재 실행 세션 내 최근 256건이다.

PC 서버를 업데이트한 뒤에는 서버를 재시작해야 새 요청 규격을 받는다. 현재 작업에서는 실행 중이던 관리 서버를 새 코드로 재시작했다.

### 요청 모드 검증 기록

- Python 서버: 요청·진행·응답 라우팅, 권한, 입력·단위 검증, 중복 ID 충돌, 오프라인 오류의 요청 ID, 기존 AOI 병행 검사 통과.
- `ProcessRequestLocal.result`: Unity Play에서 PC 기본 GP **새 계산 4건**과 요청·입력·LOT 일치, 무관한 응답 거부, 기존 공정 상태 보존 검사 통과. Jetson 실행 증거와 구별한다.
- `ProcessRequestJetson.once`: Jetson 수신기 연결까지 기다린 후 같은 4건을 실제 Jetson으로 요청. 결과는 `ProcessRequestJetson.result`, 상세 시간은 `.status`에 저장한다.
- 화면: `ProcessRequest_Local_Unity.png`, 실제 Jetson 확인 후 `ProcessRequest_Jetson_Unity.png`.

2026-10-19 실제 Jetson 요청 모드 검사: `PROCESS_REQUEST_JETSON_PLAY_OK`. Unity에서 보낸 4개 요청 모두 `gp_tabpfn`으로 새 계산되고, 입력·LOT·요청 ID 일치와 무관한 응답 거부 검사를 통과했다. 정상 34.30초, 산화막 +15% 21.21초, 에피 −40%(BV 없음) 21.04초, 에피 −40%(BV 있음) 21.12초. 초기화가 포함된 이 실행의 관찰값이며 지속 성능 보장은 아니다. 판정은 각각 정상 / 구분 불가 / 구분 불가 / 에피(84.1%). TCAD 실행·승인·레시피·HOLD·AOI 상태 변화는 없었다.

## 통신

- 기존 로컬 서버: `ws://127.0.0.1:8765/fab`.
- 별도 `process_ai` 인증 역할이 `process_analysis`와 `process_status`를 Unity로 보낸다. 기존 `jetson` AOI 역할과 동시에 접속 가능하다.
- Jetson의 `127.0.0.1:18765`를 SSH 역방향 포워딩으로 PC 서버에 연결한다. 전송 작업이 끝나면 터널도 종료한다. 공개 LAN 포트를 열지 않는다.
- 접속 키는 PC의 `process-ai.local.json`에만 저장하며 씬·로그·소스에 넣지 않는다. SSH 표준 입력으로 전달하고 Jetson에는 키 파일을 저장하지 않는다.
- LOT·실행·제안·기준 모델 ID를 전달한다. 최종 원인 확률은 고정밀 확인 결과이며, 내부 8개 후보 확률은 기본 GP 결과로 별도 구분한다.
- 보정값은 추정 공정 상태에 곱하는 배율이다. 장비의 현재 설정값이나 온도·시간 명령으로 해석하지 않는다.
- 저장 결과는 `synthetic/replay`, 새 요청 결과는 `synthetic/computed`로 구분한다. `tcad_status=not_run`, `applied=false`를 유지한다. 실제 계측 연결은 별도 계약과 검증이 필요하다.

## 기존 저장 결과 재생 실행·화면

1. PC에서 `Tools/FabSocket/start-server.cmd` 실행. 이미 실행 중인 구버전 서버는 먼저 종료한 뒤 다시 실행한다.
2. Unity Play 후 로딩·산화로 / 엘립소미터 / 이온주입기 중 선택.
3. `Tools/JetsonML/publish-jetson-process-results.cmd` 실행 후 SSH 비밀번호 입력.
4. `Jetson 원인·보정안 보기`로 분석 창을 연다. 이전/다음으로 시험 LOT 4건을 확인한다.

엘립소미터·이온주입기 모니터 하단에도 분석 요약을 표시한다. 분석 LOT은 기존 애니메이션 LOT과 독립된 `JETSON-TEST-*`이며, 실제 설비 LOT과 자동 매칭하거나 HOLD를 해제하지 않는다.

서버 연결이 끊겨도 마지막 결과는 남고 연결 끊김으로 표시한다. 분석 메시지 때문에 AOI 분류를 시작하거나 중지하지 않는다.

## 검증

- Python: `python -m unittest test_process_analysis -v` (Tools/FabSocket).
- Unity: `ProcessAnalysisPlay.once`는 PC에서 보내는 저장 결과로 실제 Play 수신·표시·동작 불변 검사를 수행한다.
- `ProcessAnalysisJetson.once`는 실제 Jetson 송신 작업을 기다려 같은 검사를 수행한다. 통과 후 Play를 유지해 검토할 수 있다.
- 결과: `ProcessAnalysisPlay.result`, `ProcessAnalysisJetson.result`, `Tools/JetsonML/process-publish-result.json`.
