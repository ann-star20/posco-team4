# posco-team4 — Virtual Fab 통합 시스템

4팀. MOSFET 공정(이온주입·산화·AOI)을 Unity 디지털 트윈으로 시뮬레이션하고,
공정 이상 발생 시 ML로 원인을 추정해 TCAD(Silvaco)로 보정안을 검증한 뒤
사람이 승인하는 가상 팹 PoC입니다.

## 시연영상

[프로젝트 시연영상 보기](docs/videos/project-demo.mp4)

공정·물류 시뮬레이션과 검사·보정 승인 흐름을 담은 프로젝트 시연영상입니다.

## 구성

이 레포는 팀원별 작업 폴더로 나뉘어 있습니다.

| 폴더 | 담당 영역 | 설명 |
|---|---|---|
| [`gate_workspace/`](gate_workspace/README.md) | Gateway · Jetson 연동 | Unity↔Jetson↔TCAD 중개 서버(FastAPI), ROS2 이벤트 파이프라인, Jetson ROS2 워커 |
| [`tcad/`](tcad/) | TCAD · ML 모델 | Surrogate(전기특성 예측 GP)·진단 에이전트·TCAD(Silvaco) 시뮬레이션, 모델 서비스 |
| [`unity/`](unity/README.md) | Unity 디지털 트윈 | 공정·검사·물류 3D 시뮬레이션, Gateway 진단/TCAD 승인 화면 |

## 전체 흐름

```
Unity(노브 입력)
  → Gateway(gate_workspace) → ROS2 → Jetson Surrogate Worker
  → TCAD 모델 서비스(tcad)의 Surrogate GP → 전기특성 예측
  → (이상 시) Unity가 Diagnosis 요청 → Jetson Diagnosis Worker
  → TCAD 모델 서비스(tcad)의 진단 에이전트 → 원인·보정 후보
  → Gateway가 보정 후보를 TCAD 워크스테이션(Silvaco)에 비동기 제출
  → 결과를 규격(vth/bv, AOI4184 데이터시트) 기준으로 판정
  → Unity(unity)가 승인 대기 후보를 조회·승인
```

세 폴더는 서로 다른 프로세스/머신에서 실행됩니다 — `gate_workspace`는 WSL(Gateway)과
Jetson에, `tcad`의 모델 서비스는 Jetson(mock/prod 전환 가능)과 별도 TCAD 워크스테이션에,
`unity`는 로컬 PC(Unity Editor/빌드)에서 각각 동작합니다.

## 시작하기

각 폴더의 README를 참고하세요:
- Gateway/Jetson 스택 기동: [`gate_workspace/README.md`](gate_workspace/README.md)
- Unity 프로젝트 실행: [`unity/README.md`](unity/README.md)
- TCAD/ML 모델: [`tcad/프로젝트_개요.md`](tcad/프로젝트_개요.md)

## 아키텍처 문서

가장 상세한 전체 아키텍처·인터페이스·DB 설계는 [`gate_workspace/docs/`](gate_workspace/docs/)에 있습니다
(`current-system-architecture.md`, `interface-definition.md`, `erd.md`, `requirements-definition.md`, `wbs.md`).
