# AOI 설비 모니터 변경 (2026-10-19)

## 백업

- 기존 AOI 코드 5개와 씬 파일: `Tools/Backups/AoiDashboardLight-20261019-160417/`.
- 변경 직전 열려 있던 씬의 추가 백업: `Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeAoiLight_20261019_161424.unity`.
- `Tools/aoi-dashboard-light-backup.txt`에서 코드 백업 경로를 확인할 수 있습니다.
- 접속 토큰·기존 FabSocket 접속 키는 백업에 포함하지 않았습니다.
- 원복할 때는 기존 코드와 씬을 함께 복원해야 합니다. 이번에 추가한 `AoiInspectionHistory.cs`, `Editor/AoiHistoryChecks.cs`, `Editor/AoiLightUpgrade.cs`는 이전 코드와 함께 빌드되지 않도록 제거해야 합니다. 저장된 이력 파일은 별개입니다.

## 변경된 화면

- 밝은 배경의 검사 화면: 대기 / 검사 중 / OK / NG / 검토.
- 검사 결과 사진, 제품·LOT·검사 ID·시각, 검출 점수, 분류 상태.
- 위치별 확대 카드 2개씩 표시, 추가 위치는 이전/다음 버튼으로 전환. 카드를 누르면 해당 부위를 크게 표시합니다.
- 전체 사진에서 서버 좌표에 번호와 테두리를 표시합니다. 위치 좌표가 없거나 범위를 벗어나면 위치를 만들어내지 않고 ‘위치 좌표 없음’을 표시합니다.
- 원본 사진 / 불량 확대 / 실시간 영상 탭. 실시간 영상은 현재 연결 대기 표시이며 검사 사진을 실시간 영상으로 표시하지 않습니다.
- 오늘 판정 완료·OK·NG·정상 비율, 최근 이력, 날짜·판정·페이지별 이력 조회.

## 유지한 기능

- `/aoi` 직접 검사 요청과 JSON → JPEG 수신, ID·해시·사진 크기 검증.
- Play 세션에서만 유지되는 숨김 토큰 입력.
- `/fab` 공정·TCAD 분석 통신과 AOI 직접 통신의 분리.
- DEMO 정상/crash/band/scratch, 설비 카메라 전환, 모니터 확대·닫기.
- 수동 OK/NG 분류 애니메이션, 신뢰도·시간 만료·중복 분류 차단.

## 기록과 집계

- 파일: `Application.persistentDataPath/InspectionHistory/aoi-inspections.json`.
- 검사 완료 때 기록합니다. 동일 출처·결과 ID는 중복 집계하지 않습니다. 불량 위치가 2개여도 제품 NG는 1건입니다.
- 오늘 정상 비율 = 오늘 OK / 오늘 (OK + NG). 검사 전은 0% 대신 ‘—’, ‘검토’는 판정 완료 집계에서 제외합니다.
- `prod`, `mock`, `demo`, 출처 미상은 분리해서 집계합니다. 화면 아래 출처를 확인합니다. `prod`는 서버 제공 출처이며 모델 정확도의 보증이 아닙니다.
- 검사 수량과 OK/NG 트레이 도착 수량은 별개로 표시합니다.
- 쓰기 실패는 화면에 표시하고 집계에 반영하지 않습니다. 손상된 기록은 덮어쓰지 않습니다.
- DB 연동 및 과거 JPG 파일의 자동 소급 집계는 하지 않습니다. 검사 이력은 메타데이터이며 Play 종료 후 과거 사진을 다시 여는 기능은 포함하지 않습니다.

## 검증

- `Tools/JetsonAOI/test-unity-protocol.ps1`: 판정·사진 검증, 좌표 변환·유효성.
- `AoiLightUpgrade.result`: Unity 자동 검사 최종 결과.
- 자동 검사는 별도 `Temp/AoiLightChecks-*` 기록만 사용하며 실제 오늘 검사 수량을 채우지 않습니다.
- 실제 카메라 영상 및 새 인증 요청은 이번 화면 변경의 자동 검사에 포함하지 않습니다.
