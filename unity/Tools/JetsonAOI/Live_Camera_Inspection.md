# 현재 카메라 화면 → Jetson 검사

## 실행

1. `start-live-camera-aoi.cmd` 실행. Jetson 로그인 비밀번호는 전송·실행 단계에 각각 한 번씩 입력합니다.
2. 파일 전송 후 이번 실행의 AOI 검사 토큰을 PC 클립보드에 복사합니다. 로그나 설정 파일에는 저장하지 않습니다.
3. `UNITY_CAMERA_AOI_READY`가 나올 때까지 기다린 뒤 이 창을 켜둡니다.
4. Unity Play를 종료하고 Ctrl+R로 가져온 뒤 다시 Play. 휴대폰 카메라를 연결합니다.
5. AOI 모니터 상단 `토큰 (숨김)`에 Ctrl+V로 붙여넣고 **현재 화면 검사**를 누릅니다. `현재 카메라 검사` 체크는 켜둡니다.

## 구분

- 카메라 영상은 휴대폰→Unity. 선택한 최신 JPEG 한 장만 Unity→Jetson으로 전송합니다. 휴대폰 계정은 Jetson에 보내지 않습니다.
- 새 서버 주소는 USB 연결 `ws://192.168.55.1:8401/aoi`. 기존 8400 시험 사진 서버와 별개이며 원본 AOI Python 파일은 수정하지 않습니다.
- 기존 `fab_virtual_lot.aoi_pipeline`과 실제 YOLO 모델을 재사용합니다. 모의 모델로 자동 대체하지 않습니다.
- 모델 경로는 기존 프로젝트의 `.env`, `.env.jetson`, `.env.local`에서 `AOI_PART_MODEL_FILE`·`AOI_DEFECT_MODEL_FILE`을 읽습니다. 없으면 프로젝트·모델·바탕화면·다운로드·문서 폴더에서 역할명이 붙은 `.pt`를 찾습니다. 각 역할에 후보가 정확히 하나씩 있을 때만 연결하며, 모호하면 후보 경로만 표시하고 중단합니다. 로드 후 모델의 실제 클래스 번호·이름도 원본 파이프라인의 부품/불량 매핑과 대조합니다. 패키지는 설치하지 않습니다.
- 결과 JPG·모델 분석 manifest는 Jetson `~/unity-aoi-camera-results`에 저장됩니다. ROS 이벤트 발행과 팀 DB 연결은 이번 어댑터에서 활성화하지 않았습니다. Unity 검사 이력은 기존 로컬 저장 기능을 사용합니다.
- 제품이 없으면 서버의 `review`를 ‘검토’로 표시하며 OK/NG 분류를 막습니다. 검출 점수는 검증된 정확도가 아닙니다.
- 현재 실행 화면은 계속 보이고, 우측 판정·불량 위치 사진은 마지막으로 요청한 정지 화면 결과입니다.

## 전송 규격

기존 schema 1 요청에 `input_source: unity_camera`, `input_image`를 추가합니다. input_image는 JPEG byte_length·sha256·width·height·sampled_at_ms를 포함합니다. JSON 직후 하나의 WebSocket binary 메시지로 JPEG를 보냅니다. fixture_name은 기존 검사 함수 호환용 `unity-camera.jpg`이며 파일을 읽지 않습니다.

서버가 요청 토큰·ID·길이·해시·JPEG 인코딩 크기를 확인한 뒤 실제 모델로 검사합니다. 기존 결과 JSON과 annotated JPEG에 `input_source`·`input_image_sha256`를 더해 돌려줍니다. Unity가 보낸 JPEG와 같은 해시인지 확인합니다. 입력 최대 8 MiB·4096×4096, 연결마다 인증, 리디렉션·외부 URL 입력 없음. 동시에 수신 연결 2개까지, 모델 추론은 순차 처리.

서버 모델 실행 전 단계는 로컬 모의 서비스로 검사했습니다. 실제 Jetson 모델 실행·Unity 결과 수신은 서버를 실행하고 토큰을 붙여넣은 뒤 별도 확인해야 합니다.

## 복원

`Tools/aoi-live-inspection-backup.txt`에 C# 변경 전 파일 위치를 기록했습니다. 서버 어댑터는 원본 패키지와 분리된 사용자 홈 파일이며 창을 닫으면 SSH로 시작한 실행이 종료됩니다. 재시작하면 새 검사 토큰이 필요합니다.
