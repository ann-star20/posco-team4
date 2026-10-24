# Fab WebSocket 서버 v1

Unity 프로젝트 밖의 별도 Python 프로그램입니다. Unity·젯슨·TCAD 역할을 연결합니다. Unity AOI에는 `AoiWebSocketClient`를 붙여 이 서버에 직접 접속합니다.

## Unity에서 사용

1. `start-server.cmd`로 서버를 켭니다.
2. Unity의 `MOSFETSmallFab_Corrected` 씬에서 Play를 누릅니다. AOI는 `unity` 역할로 자동 인증합니다.
3. AOI 패널에 **서버 연결됨**이 표시되는지 확인합니다. `AOI monitor window`는 확대 창입니다.
4. `send-scratch-to-unity.cmd`를 실행하면 실제 Unity로 **시험용** scratch/96.8% 판정 한 건을 보냅니다. 이미지 없는 시험이며 젯슨 카메라 인식이 아닙니다.
5. 5초 이내에 `Start OK / NG sort`를 누르면 NG 박스로 움직입니다. 만료되면 시험 결과를 새로 보내야 합니다.

5초 제한은 **분류 시작 전 결과의 유효성**에만 적용합니다. 시작한 제품은 이동하는 동안 OK/NG를 유지하고, 도착 후에는 `박스 도착 · 완료`와 마지막 검사 결과를 남깁니다. 완료 결과로 재분류할 수는 없습니다. 새 결과·모드 변경·연결 끊김 시 기존 표시를 갱신하거나 지웁니다.

`run-demo.cmd`는 자체 시험용 unity 역할까지 접속하므로 실제 Unity가 Play 중일 때 같이 실행하지 않습니다. 실제 Unity 시험에는 `send-scratch-to-unity.cmd`를 사용합니다.

접속 키는 Unity 컴포넌트의 `Credential File` 경로에서 읽습니다. 기본값은 프로젝트 루트의 `Tools/FabSocket/server.local.json`입니다. 키 문자열을 씬·프리팹·코드에 저장하지 않습니다. 실행 파일로 빌드할 때도 별도 로컬 설정을 배치하고 경로를 지정해야 합니다. 현재 클라이언트는 Windows Editor/데스크톱용이며 WebGL용이 아닙니다.

연결이 끊기면 이전 판정을 지우고 분류를 차단합니다. 가상 분류 중이었다면 동작을 중단하고 제품을 숨깁니다. 재접속은 2초 간격으로 시도하지만 이전 결과를 복구하거나 자동 재분류하지 않습니다. 새 검사 결과와 수동 시작이 필요합니다.

수신은 최대 4MB 텍스트 메시지를 조각 단위로 합쳐 처리하고, 화면 갱신은 Unity 메인 스레드에서 수행합니다. 대기열 초과 시 연결을 끊고 재접속합니다. AOI가 분류 중이거나 유효한 이전 제품의 분류를 기다리는 동안 새 제품 결과는 적용하지 않습니다. 연속 생산용 전달 확인·큐는 후속 단계입니다.

이번 Unity 연결은 `inspection_result` 표시·분류까지입니다. camera_frame 연속 재생과 TCAD 중앙 대시보드는 아직 구현하지 않았습니다. 검사 결과에 jpeg_base64가 있으면 동일 검사 스냅샷을 함께 표시하고, 없으면 `검사 이미지는 미수신`으로 표시합니다.

클라이언트 공식 API: https://learn.microsoft.com/en-us/dotnet/api/system.net.websockets.clientwebsocket

## 실행

이 PC에서는 **`start-server.cmd`를 더블클릭**합니다. 창을 켜둔 채 사용하고 종료는 해당 창에서 Ctrl+C입니다. `run-demo.cmd`는 별도 창에서 실행하는 통신 시험입니다.
PowerShell에서는 `Start-Server.ps1`도 사용할 수 있습니다.
서버 실행 후 별도 PowerShell에서 `./Start-Server.ps1 -Demo`로 세 역할의 **시험 클라이언트**가 메시지를 주고받는지 확인할 수 있습니다. 실제 Unity나 젯슨이 아닙니다.

다른 환경: Python 3.9 이상에서 `python -m pip install -r requirements.txt`, `python server.py`.
공식 라이브러리 websockets 15.0.1을 사용합니다. 이 PC에는 `.deps`에만 설치합니다.

기본 주소: **ws://127.0.0.1:8765/fab**. 자기 PC에서만 접속 가능합니다.
기존 IP Webcam :8080, SSH :22와 별도입니다.

## 최초 연결

서버 최초 실행 시 `server.local.json`에 역할별 접속 키를 생성합니다. 이 파일은 Git에 넣거나 채팅·로그에 출력하지 않습니다. 팀원에게는 해당 역할의 키만 별도 전달합니다.

연결 후 5초 내 첫 텍스트 메시지:

```json
{"type":"hello","role":"unity","token":"<해당 역할의 키>"}
```

역할은 `unity`, `jetson`, `tcad`. 역할당 한 연결입니다. 성공하면 `welcome`을 받습니다. 브라우저 접속은 기본 허용하지 않으며 Unity/Python 클라이언트에는 Origin 헤더를 보내지 않습니다.

## 데이터 형식

```json
{
  "version": 1,
  "type": "inspection_result",
  "message_id": "검사마다 새로운 UUID",
  "payload": {
    "result_id": "RESULT-013",
    "product_id": "MOSFET-013",
    "frame_id": "FRAME-1520",
    "label": "scratch",
    "confidence": 0.968,
    "captured_at_ms": 0
  }
}
```

`captured_at_ms`는 0이 아니라 **촬영 시각의 UTC Unix 밀리초**를 넣습니다. PC·젯슨 시계를 맞춥니다. 검사 결과는 5초 이내, 미래 시각은 2초까지만 허용합니다. ID는 1~128자 문자열입니다.

| type | 발신 → 수신 | payload 필수 내용 |
|---|---|---|
| inspection_result | jetson → unity | 위 예시. label: normal/crash/band/scratch, confidence: 0~1 |
| camera_frame | jetson → unity | frame_id, captured_at_ms, jpeg_base64(최대 2,800,000자) |
| tcad_result | tcad → unity | run_id, status(running/completed/failed), representation |
| recipe_proposal | tcad → unity | run_id, representation; 제안 데이터는 payload에 추가 |
| command | unity → 지정 역할 | 바깥에 target: jetson/tcad, payload.action |

TCAD `representation`은 `physical` 또는 `normalized_ratio`입니다. 전자는 `units` 객체, 후자는 `baseline_version` 문자열도 필수입니다. TCAD 세부 물리 변수와 단위·규격 판정은 팀원과 추가로 맞춰야 합니다. 서버는 TCAD 계산·물리 검증을 하지 않습니다.

명령: jetson에는 START_INSPECTION/PAUSE/CANCEL, tcad에는 RUN_TCAD/CANCEL. 서버는 명령을 **전달만** 하며 실행하거나 보정값을 적용하지 않습니다.

수신 메시지에는 서버가 `source`, `target`, `received_at_ms`를 붙입니다. 발신자가 source를 위조해도 인증 역할로 덮어씁니다.
이미지와 결과는 `frame_id`로 연결해야 합니다. 최신 영상에 과거 결과를 임의로 겹치지 않습니다. 이번 단계는 영상 전송 형식 준비까지이며 영상 플레이어 구현은 포함하지 않습니다.

## 처리 확인·오류

- ack / forwarded: 수신 연결로 전송했습니다. **Unity 화면 갱신·실제 장비 동작 완료를 뜻하지 않습니다.**
- ack / duplicate: 같은 역할·message_id의 동일 메시지를 다시 전송하지 않았습니다.
- error / TARGET_OFFLINE: 수신자가 없습니다. 저장·대기열 없이 거절합니다. 상대가 접속한 뒤 재시도합니다.
- error / INVALID_MESSAGE: 형식·권한·시각·숫자가 잘못됐습니다.
- error / TARGET_UNAVAILABLE: 연결이 끊기거나 전송이 지연됐습니다. 수신됐을 수도 있으므로 제품/실행 ID로 상태를 확인해야 합니다.

최근 2048개 메시지 ID를 메모리에서 중복 차단합니다. 서버 재시작 후 초기화되므로 실제 분류 클라이언트도 result_id 중복 방지를 해야 합니다. 오프라인 재전송·영속 큐·자동 재접속은 후속 단계입니다. 최대 메시지 4MB, 연결 확인 ping 20초입니다. 로그에 영상·판정값·접속 키를 저장하지 않습니다.

## 젯슨·팀원 PC에서 접속할 때

현재 기본 실행은 로컬 시험 전용입니다. 확인된 이 PC 주소는 젯슨 USB 네트워크 `192.168.55.100`, Wi-Fi `192.168.10.3`이며 변경될 수 있습니다.
다른 장치 연결은 TLS 인증서와 키를 준비한 뒤 예를 들어 `python server.py --host 0.0.0.0 --cert server.pem --key server-key.pem`으로 실행합니다. 클라이언트는 해당 인증서를 신뢰하도록 설정하고 **wss://접근가능한_PC_IP:8765/fab**로 접속합니다. 인증서의 IP/호스트 이름도 일치해야 합니다.
네트워크·Windows 방화벽 접근 확인은 별도 단계입니다. 방화벽이나 OS 보안 설정을 자동 변경하지 않습니다. 포트를 인터넷에 공개하지 않습니다.

공식 API 참고: https://websockets.readthedocs.io/en/15.0.1/reference/asyncio/server.html
