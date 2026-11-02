# 데이터셋 설명서 — MOSFET 비전 검사 (부품 탐지 / 결함 탐지)

**대상**: `mosfet_part_v5-26` 학습용 데이터셋(`dataset_part`), `mosfet_defect_v5-26` 학습용 데이터셋(`dataset_defect`)
**확인 방법**: Jetson(`192.168.213.167`) 로컬 사본(`/home/jetson/project/smart_factory/aoi/datasets/`)을 직접 스캔하여 이미지 수, 라벨 수, 클래스별 인스턴스 수, 해상도를 실측
**작성일**: 2026-10-24

> 데이터셋 원본은 Google Drive(`posco_vision/datasets/dataset_part`, `dataset_defect`)에 있으며, Jetson에는 학습·검증에 쓰인 사본이 보관되어 있습니다. 라벨링 도구, 라벨링 기준(크랙/꺾임 판정 세부 기준 등)에 대한 문서는 이번 조사 범위에서 확인되지 않았으므로 별도 확보가 필요합니다.

---

## 1. 데이터셋 개요

| 항목 | dataset_part | dataset_defect |
|---|---|---|
| 용도 | Stage 1 — 부품 영역(body/lead/tab) 분할 | Stage 2 — 결함 영역(crash/bend) 분할 |
| 라벨 포맷 | YOLO 세그멘테이션(정규화 폴리곤 좌표, `class cx1 cy1 cx2 cy2 ...`) | 동일 |
| 이미지 해상도 | 1920×1080 (확인된 샘플 전수 동일) | 1920×1080 (확인된 샘플 전수 동일) |
| 이미지 포맷 | PNG | PNG |
| 정의 파일 | `datasets/data_part.yaml` | `datasets/data_defect.yaml` |

### 클래스 정의

| 데이터셋 | class id | 이름 | 의미 |
|---|---|---|---|
| part | 0 | body | MOSFET 몸체 |
| part | 1 | lead | 리드(다리) |
| part | 2 | tab | 탭 |
| defect | 0 | crash | 크랙/스크래치 |
| defect | 1 | bend | 꺾임/휨 |

---

## 2. 이미지·라벨 수량 (실측)

| | train | val | 합계 |
|---|---|---|---|
| dataset_part | 275 | 68 | **343** |
| dataset_defect | 168 | 42 | **210** |

- 모든 라벨 파일이 최소 1개 이상의 인스턴스를 포함합니다(공란/배경 전용 라벨 없음, train+val 전체 확인).
- `dataset_defect`는 `dataset_part` 이미지의 **부분집합**입니다. part의 train 275장 중 168장이 defect train과 파일명 기준으로 완전히 일치하며, 나머지 **107장은 정상(무결함) MOSFET**(`mosfet_normal (*).png`)으로 Stage 1에만 사용되고 Stage 2 데이터셋에는 포함되지 않습니다.
- 즉 **Stage 2(결함 탐지) 모델은 학습·검증 과정에서 "결함이 전혀 없는" 이미지를 한 장도 보지 못했습니다.** 두 결함 클래스(crash/bend) 중 하나는 반드시 존재하는 이미지로만 구성되어 있습니다.

## 3. 클래스별 인스턴스 분포 (실측, train+val 합산)

| dataset_part | 인스턴스 수 | 이미지당 평균 |
|---|---|---|
| body (0) | 343 | 1.00 |
| lead (1) | 1,029 | 3.00 |
| tab (2) | 343 | 1.00 |

→ 이미지 1장당 정확히 body 1개, lead 3개, tab 1개로 구성되어 있어, part 데이터셋은 매우 규칙적이고 클래스 불균형이 없습니다.

| dataset_defect | 인스턴스 수 | 비율 |
|---|---|---|
| crash (0) | 392 | 72.8% |
| bend (1) | 146 | 27.2% |

→ `crash`가 `bend`보다 약 2.7배 많아 **클래스 불균형이 존재**합니다. 평가서의 Mask 지표는 2개 클래스 평균(mAP)이므로, 상대적으로 적은 `bend` 클래스의 개별 성능(클래스별 AP)을 평가서에 별도로 기재할 것을 권고합니다.

---

## 4. 데이터셋 구조 상 리스크 (평가서에 반영 필요)

1. **결함 탐지 모델의 Negative 샘플 부재**: Stage 2 학습·검증 데이터에 "무결함" 이미지가 전혀 없습니다. 실제 라인에서는 정상 MOSFET이 Stage 1을 통과해 Stage 2로 들어오는 경우가 당연히 발생하므로, 현재 검증 지표(mAP)만으로는 **정상품을 결함으로 오탐(False Positive)할 가능성을 평가할 수 없습니다.** 운영 전 정상 MOSFET에 대한 오탐률(FPR) 테스트를 별도로 수행해야 합니다.
2. **클래스 불균형(crash:bend ≈ 2.7:1)**: `bend` 클래스의 재현율(Recall)이 과소 추정될 위험이 있습니다. 클래스별 성능을 분리해서 확인 필요.
3. **검증 세트 규모가 작음**: defect val은 42장/92 인스턴스, part val은 68장뿐입니다. mAP50-95 같은 정밀 지표는 샘플 수가 적을수록 분산이 커지므로, 보고된 수치(예: Mask mAP50-95 0.655)의 신뢰구간이 넓을 수 있습니다.
4. **라벨링 기준 문서 부재**: "crash(크랙)"와 "bend(꺾임)"을 구분하는 정량적 기준(길이, 각도 등)이 문서화되어 있지 않습니다. 라벨러 간 일치도(IAA) 자료가 있다면 평가서에 포함을 권고합니다.

---

## 5. 데이터 출처 요약

- Jetson 로컬 경로: `/home/jetson/project/smart_factory/aoi/datasets/dataset_part/`, `dataset_defect/`
- 원본(Google Drive, Colab 학습 시 참조): `/content/drive/MyDrive/posco_vision/datasets/{dataset_part,dataset_defect}`
- 압축 원본 백업: `datasets/dataset_part-20261022T015709Z-1-001.zip`, `datasets/dataset_defect-20261022T021240Z-1-001.zip`
