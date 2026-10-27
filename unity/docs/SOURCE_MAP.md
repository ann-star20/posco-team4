# 소스 안내

## 장면 및 설비
- `Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity`: 현재 공장 장면
- 같은 Scenes 폴더의 `MOSFET_*Test.unity`: AOI/OHT/웨이퍼 기능 시험 장면
- `Assets/MOSFETInspection/Editor/SmallFabBuilder.cs`: 공장 장면 생성 도구
- `Assets/MOSFETInspection/Editor/InstallIntegratedOxidation.cs`: 산화로 모델 적용
- `Assets/MOSFETInspection/Editor/ApplyAmberFoup.cs`: 주황색 반투명 FOUP 외형 적용
- `Blender/restyle_existing_foup.py`: 기존 FOUP 모델 수정
- `Blender/Oxidation_System_Integrated.blend`: 산화로 모델 원본

## Gateway 및 TCAD
- `GatewayInspectionBridge.cs`, `GatewayInspectionBridge.FullCycle.cs`: 검사 전송 및 단계별 결과 처리
- `GatewayStreamClient.cs`: RUN별 이벤트 수신
- `GatewayFullCycleProtocol.cs`: 요청/이벤트 계약과 상태 전이
- `GatewayTcadApprovalView.cs`: 후보 목록 및 관리자 승인 UI
- `GatewayApprovedRecipe.cs`: 승인 응답 검증 및 설비 설정 적용
- `DemoApprovedLotRecipes.cs`: 승인 레시피 저장과 LOT 시작 시 조건 고정
- `GatewayLotConditions.cs`: LOT별 공정 입력 조건

위 파일은 `Assets/MOSFETInspection` 아래에 있습니다.

## AOI
- `AoiDirectClient.cs`: Jetson AOI 검사 요청
- `AoiCameraStream.cs`, `AoiPreviewProtocol.cs`: 카메라 영상 수신
- `AoiDashboard.cs`, `AoiDashboard.Signal.cs`: 검사 화면
- `Tools/JetsonAOI`: Jetson 실행·연결·프로토콜 검사 소스
- IP Webcam 연결: 스마트폰 `/video` → Jetson → Unity. 설정은 [SETUP.md](SETUP.md)의 IP 웹캠 연결 항목 참조
- `Tools/LaptopWebcam/webcam_sender.py`: 별도 Windows 노트북 송출용 선택 도구. 현재 IP Webcam 연결에는 사용하지 않음

## 시험 도구 및 데이터
- `Assets/MOSFETInspection/Editor/*Check*.cs`: 에디터 검사 도구
- `Tools/Gateway`: 계약 검사·서버 연결 도구·고정 테스트 JSON
- `Tools/FabSocket`: 로컬 시험용 소켓 서버 및 고정 진단 데이터
- `Tools/JetsonTestData`: CSV 시험 입력 서비스 및 시험 CSV

과거 실행 로그/요청 기록은 일반 배포 대상에서 제외했습니다.
다만 현재 검사 코드가 직접 읽는 제한된 고정 JSON은 검사 재현용으로 포함했습니다.
