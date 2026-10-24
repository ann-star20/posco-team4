# Unity MOSFET Factory Digital Twin

MOSFET 공정·검사·물류를 표현하는 Unity 디지털 트윈 프로젝트입니다.
산화로·엘립소미터·이온주입·AOI, OHT/FOUP 이송, 스토커 HOLD 격리,
Gateway 진단 및 TCAD 보정 후보 검토 화면을 포함합니다.

## 실행

1. Unity Hub에서 이 폴더를 프로젝트로 추가합니다.
2. **Unity 6000.6.4f1**로 엽니다. HDRP **17.7.0** 등 패키지 복원이 끝날 때까지 기다립니다.
3. `Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity`를 엽니다.
4. Play를 실행합니다. 서버 연결 없이 볼 수 있는 설비 시뮬레이션과 서버 연동 기능은 구분합니다.

`Assets`, `Packages`, `ProjectSettings`는 Unity 재현에 필요한 프로젝트 원본입니다.
`Packages/com.unity.splines`는 manifest의 로컬 패키지 참조 때문에 함께 포함했습니다.
에셋의 `.meta` 파일을 삭제하거나 이름만 임의로 바꾸지 마세요.
이 복사본의 Build Settings는 현재 공장 장면을 기본 장면으로 지정했습니다.

## 주요 기능

- 산화로 로딩·보트 승강·웨이퍼 회수, 엘립소미터 두께 검사, 이온주입 애니메이션
- 개별 설비 시작 시 OHT가 이전 설비/스토커에서 FOUP를 가져오는 흐름
- 정상 LOT 자동 출고, NG/HOLD LOT 스토커 보관 및 슬롯 수동 해제
- AOI 실시간 카메라 미리보기와 Jetson 검사 결과 표시
- 공정값 → surrogate 예측 → 조건부 diagnosis → Gateway 자동 TCAD 검증
- TCAD 후보 목록·규격 판정 표시·관리자 승인 및 다음 LOT 시뮬레이션 입력값 적용

## 서버 연결

| 역할 | 현재 팀 환경 기본 주소 |
|---|---|
| Gateway 상태 | `http://192.168.212.10:8000/health/live` |
| Gateway 제어 | `ws://192.168.212.10:8000/api/v1/control` |
| Gateway 결과 스트림 | `ws://192.168.212.10:8000/api/v1/stream` |
| TCAD 후보 조회 | `http://192.168.212.10:8000/api/v1/tcad/proposals?status=review_required` |
| Jetson 카메라 미리보기 | `ws://192.168.213.167:8500/camera/preview` |
| Jetson AOI 검사 | `ws://192.168.213.167:8400/aoi` |
| CSV 시험 입력 터널 | `http://127.0.0.1:8601/api/v1/test-samples` |

위 주소는 팀 내부망 기본값입니다. 다른 환경에서는 Unity 연결 화면/해당 실행 스크립트의
주소를 바꾸고, 운영 담당자가 발급한 토큰을 입력해야 합니다.
**실제 Gateway·AOI·카메라 토큰 및 로컬 인증 파일은 이 저장소에 포함하지 않았습니다.**
공유 문서의 `REPLACE_WITH_*` 값은 실제 인증값이 아닌 자리표시자입니다.
`Tools/FabSocket/server.py`는 로컬 인증 파일이 없으면 역할별 랜덤 토큰을 생성합니다.
설정 예제의 공통 문자열을 운영 토큰으로 그대로 사용하지 마세요.

### ip웹캠

스마트폰의 IP Webcam 앱으로 카메라 영상을 MJPEG /video로 송출합니다.
스마트폰과 Jetson을 같은 네트워크에 연결하고, 앱에 표시된 http://<스마트폰 IP>:<포트>/video를 Jetson AOI의 카메라 입력 주소로 설정합니다.
Jetson이 영상을 수신해 검사하고, Unity AOI 대시보드에 실시간 영상과 검사 결과를 전달합니다.
스마트폰 IP가 변경되면 Jetson AOI의 카메라 입력 주소도 변경해야 합니다.

## TCAD 승인 범위

- 신규 `GET /api/v1/tcad/proposals`, `POST /api/v1/tcad/proposals/{proposal_id}/decision` 경로를 사용합니다.
- 서버의 `spec_verdict.overall == "in_spec"` 후보를 승인 대상으로 표시합니다.
- 관리자 창의 **1234는 시연용 로컬 잠금**입니다. 운영 관리자 인증을 대체하지 않습니다.
- 실제 TCAD 확인 체크는 담당자의 수동 확인이며 서버의 출처 증명이 아닙니다.
- 승인 성공 응답의 `process_parameters`를 저장하고 다음 LOT부터 시뮬레이션 입력에 적용합니다.
- 진행 중/이미 시작한 LOT의 조건, 원본 검사 결과, 판정 규격은 덮어쓰지 않습니다.
- 산화막 입력 단위는 µm, Unity 설비 표시는 nm입니다. 도즈는 cm⁻², 에피 도핑은 cm⁻³입니다.
- 에피 도핑은 입력 웨이퍼 조건입니다. 실제 에피 설비나 PLC를 제어하는 구현은 아닙니다.

## 폴더 안내

상세 파일 안내: [docs/SOURCE_MAP.md](docs/SOURCE_MAP.md)

| 폴더 | 내용 |
|---|---|
| `Assets/MOSFETInspection` | 런타임 C#·에디터 도구·장면·자체 모델·재질·리소스 |
| `Assets/Settings` | HDRP 렌더링 설정 |
| `Packages` | Unity 패키지 설정·잠금 파일·로컬 Splines 패키지 |
| `ProjectSettings` | Unity 프로젝트 설정 |
| `Blender` | 자체 설비/FOUP 모델 원본 및 제작·내보내기 스크립트 |
| `Tools` | 연결 실행 파일의 소스·계약 검사·로컬 시험 서버·시험 데이터 |

## GitHub 업로드

이 폴더를 Git 저장소의 루트로 사용하고 포함된 `.gitignore`, `.gitattributes`를 유지하세요.
`Library`, `Temp`, `Logs`, `UserSettings`, 백업 장면, 실제 토큰, ML 가중치, 녹화 영상,
EXE 및 개인 PC 실행 기록은 업로드 대상에서 제외했습니다.
GitHub Desktop 또는 Git으로 커밋한 뒤 원하는 저장소에 올릴 수 있습니다.
이 취합 작업은 **GitHub 저장소 생성·업로드·커밋을 수행하지 않습니다.**

## 검증 및 한계

취합본은 파일/에셋 GUID 연결, 로컬 패키지 참조, 토큰 제거, Python 구문,
파일 무결성 검사를 수행했습니다. 결과는 [docs/EXPORT_REPORT.json](docs/EXPORT_REPORT.json)에 기록됩니다.
C# 소스 144개와 현재 장면은 저장된 원본과 내용이 동일하며, PowerShell 35개 구문 검사도 통과했습니다.
원본 HDRP의 구형 Diffusion Profile 목록에 있던 미해결 참조 2개는 변경하지 않고 보고서에 기록했습니다.
새 폴더를 별도의 Unity 프로젝트로 열어 재임포트/Play 또는 실제 서버 왕복 검사를 한 것은 아닙니다.
일부 검사 스크립트는 명시적인 `.once` 파일을 만들었을 때만 실행됩니다.
운영 장면을 자동 덮어쓰지 않도록 해당 실행 요청 파일은 포함하지 않았습니다.
기록 기반 고정 테스트 JSON과 CSV는 실시간 측정/TCAD 실행 완료를 의미하지 않습니다.
원격 ML/ROS/TCAD 서버 본체와 모델 가중치는 별도 팀 서버에서 관리합니다.

## 외부 구성요소

외부 공장 샘플 `Assets/UnityFactorySceneHDRP`와 Unity 시작 템플릿은 포함하지 않았습니다.
현재 공장 장면/프로젝트 설정에 필요한 자체 에셋과 패키지는 별도로 포함했습니다.
이전 다중 라인 장면용 볼륨 프로필의 외부 샘플 반사 텍스처 연결은 비웠습니다.
이 프로필은 현재 공장 장면에서 참조하지 않습니다. 과거 템플릿 기반 재생성 도구는
원래 외부 공장 샘플을 별도로 가져와야 사용할 수 있습니다.
Splines의 기존 `LICENSE.md` 등 외부 구성요소의 고지와 라이선스는 그대로 유지했습니다.
프로젝트 전체에 대한 공개 라이선스는 이 취합 과정에서 새로 지정하지 않았습니다.
