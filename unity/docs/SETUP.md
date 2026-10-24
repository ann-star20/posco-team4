# 개발 및 연결 준비

## Unity

Unity Hub로 프로젝트 폴더를 추가하고 ProjectVersion.txt의 버전으로 엽니다.
서버에 요청하기 전 연결 주소·토큰·CSV/시뮬레이션 입력의 출처를 확인합니다.
Unity 편집기 개인 창 배치는 UserSettings이므로 공유본에 포함하지 않았습니다.

## 선택 사항: 노트북 웹캠 EXE 빌드

Windows 64비트 Python 3.12와 정상 Tcl/Tk가 필요합니다.
Tools/LaptopWebcam 폴더에서 `.build-env` 가상환경을 만들고
`requirements-build.txt`를 설치합니다. build.ps1은 `.tcl/tcl8.6`, `.tcl/tk8.6`에
빌드용 Tcl/Tk 리소스를 복사해 둔 환경을 사용합니다.
원본 Python 설치의 tcl 디렉터리를 `.tcl`로 복사한 뒤 build.ps1을 실행합니다.
EXE와 ZIP은 release 및 도구 폴더에 생성되며 Git에서 제외됩니다.
카메라의 실제 촬영은 프로그램에서 송출 시작을 눌렀을 때만 시작됩니다.

## 선택 사항: 로컬 시험 도구

FabSocket의 requirements.txt를 별도 가상환경에 설치해 로컬 시험 서버를 사용할 수 있습니다.
server.local.json, process-ai.local.json은 개인 환경에만 보관합니다.
Tools/JetsonML의 이전 배포 결과 및 모델 본체는 포함하지 않았으므로 기존 배포 결과를 읽는
레거시 실행 파일은 배포 준비 없이 바로 실행되지 않을 수 있습니다.
Blender 제작 스크립트 일부는 기존 PC의 절대 경로를 사용합니다. 재제작 시 해당 경로를 수정하세요.
.NET 독립 검사 프로젝트 일부는 Unity 패키지 캐시의 DLL 경로를 참조합니다.
Unity 패키지 복원 후 실제 설치된 경로에 맞춰 참조를 조정해야 합니다.
Unity 에디터 안의 C# 검사 도구와 외부 .NET 검사 프로젝트는 구분하세요.

## 원격 연결

SSH 실행 파일은 서버 계정 비밀번호를 사용자가 직접 입력하도록 되어 있습니다.
known_hosts 파일은 공개 서버 호스트 키이며 개인 SSH 키가 아닙니다.
새 팀 서버를 쓰면 신뢰할 수 있는 경로로 호스트 키 지문을 확인하고 설정을 갱신합니다.
Jetson의 영상/검사 서버와 Gateway·ROS worker·실제 TCAD 서비스는 별도로 실행되어야 합니다.
