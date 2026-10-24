# 모델평가서 — MOSFET 비전 검사 모델 (부품 탐지 / 결함 탐지)

| 항목 | 내용 |
|---|---|
| 모델명 | `mosfet_part_v5-26` (부품 탐지), `mosfet_defect_v5-26` (결함 탐지) |
| 모델 아키텍처 | YOLO26n-seg (Ultralytics, Instance Segmentation) |
| 적용 공정 | AOI(자동 외관 검사) — MOSFET 부품/결함 2단계 파이프라인 |
| 배포 위치 | Jetson Orin (192.168.10.253), `/home/jetson/project/smart_factory/aoi/models/` |
| 평가서 작성일 | 2026-10-23 |
| 평가 수행 환경 | Jetson 로컬 체크포인트(`best.pt`) 메타데이터 직접 추출, Ultralytics 8.4.118 / torch 2.8.0 |

> **중요**: 본 평가서의 수치는 Jetson 상의 `best.pt` 체크포인트에 내장된 `train_args`/`train_metrics`/`train_results`와 `benchmark/run.log`를 직접 로드하여 확인한 값입니다. 학습이 수행된 Google Colab 측의 원본 학습 로그(`results.csv`, `args.yaml` 등)는 Jetson에 전달되지 않았으므로, 이 문서에서 "검증 불가"로 표시한 항목은 추가 자료 확보가 필요합니다.

---

## 1. 평가 개요 (Executive Summary)

- 기존 YOLOv8n-seg 모델을 YOLO26n-seg로 교체 파인튜닝하였으며, Part(부품) / Defect(결함) 두 개의 독립 모델로 구성된 2단계(Cascade) 세그멘테이션 파이프라인입니다.
- 두 모델 모두 사전학습 가중치(`yolo26n-seg.pt`)에서 시작한 파인튜닝이며, 학습 해상도는 **imgsz=1024**, 각각 150epoch(Part) / 200epoch(Defect) 학습되었습니다.
- 학습 시점 검증 지표는 매우 높은 수준(Mask mAP50-95: Part 0.901, Defect 0.655)이나, **①YOLOv8n-seg 베이스라인 비교 자료가 Jetson 환경에 부재, ②배포 시 해상도가 학습 해상도(1024)와 다른 640으로 축소, ③ONNX/TensorRT 변환 후 정확도가 벤치마크 스크립트 상 0.0으로 측정**되는 등 운영 반영 전 확인이 필요한 리스크가 다수 발견되었습니다.
- 결론적으로 **PyTorch(.pt) 포맷 기준으로는 두 모델 모두 production-ready 수준의 정밀도**를 보이나, **실제 Jetson 배포 포맷(TensorRT FP16 엔진)에 대한 정확도 검증이 완료되지 않아 현 상태로 최종 승인하기는 어렵습니다.**

---

## 2. 평가 대상 및 목적

| 구분 | 내용 |
|---|---|
| Stage 1 (Part) | 부품 영역(body, lead, tab) 분할 — 결함 탐지 전처리 단계로 ROI를 정의 |
| Stage 2 (Defect) | Stage 1에서 산출된 부품 영역 내 결함(crash: 크랙, bend: 꺾임) 분할 |
| 평가 목적 | 신규 아키텍처(YOLO26n-seg) 파인튜닝 결과가 기존 모델(YOLOv8n-seg) 대비 운영 투입 가능한 수준인지 판단 |

---

## 3. 모델 및 아키텍처 정의

### 3.1 공통 사양 (체크포인트에서 직접 확인)

| 항목 | Part 모델 | Defect 모델 |
|---|---|---|
| 베이스 가중치 | `yolo26n-seg.pt` (사전학습) | `yolo26n-seg.pt` (사전학습) |
| 파라미터 수 | 2,689,469 | 2,689,469 |
| GFLOPs | 9.1 | 9.1 |
| 레이어 수(fused) | 139 | 139 |
| Task | segment | segment |
| end2end (NMS-free) | True | True |
| 클래스 수 | 3 (body, lead, tab) | 2 (crash, bend) |

### 3.2 아키텍처 구조 (model.yaml 기반)

```
backbone: Conv → Conv → C3k2 → Conv → C3k2 → Conv → C3k2 → Conv → C3k2 → SPPF → C2PSA
head:     Upsample/Concat/C3k2 반복(FPN 유사 구조) → Segment26(Proto26 마스크 프로토타입 헤드)
```

- YOLOv8n-seg와의 구조적 차이: 백본 종단에 **C2PSA(Polarized Self-Attention)** 블록 추가, 세그멘테이션 헤드가 `Segment`/`Proto` → **`Segment26`/`Proto26`**으로 교체, **`end2end=True`**(NMS-free 디코딩) 적용.
- 보조 시맨틱 손실(`sem_loss`)은 학습 로그 상 **전 구간 0.0**으로, 이번 파인튜닝에서는 비활성 상태였습니다 (상세: §6.3).

---

## 4. 데이터셋

| 항목 | Part | Defect |
|---|---|---|
| 정의 파일 | `datasets/data_part.yaml` | `datasets/data_defect.yaml` |
| 클래스 | body, lead, tab (3) | crash, bend (2) |
| 원본 경로 | `dataset_part/` (Jetson 로컬 사본, 원본은 Google Drive `posco_vision/datasets/dataset_part`) | `dataset_defect/` (동일 구조) |
| 분할 구조 | `images/train`, `images/val` | `images/train`, `images/val` |
| 학습 시 참조 경로 | `/content/drive/MyDrive/posco_vision/datasets/data_part.yaml` (Colab) | `/content/drive/MyDrive/posco_vision/datasets/data_defect.yaml` (Colab) |

> 학습/검증 세트의 정확한 이미지 수, 클래스별 분포, 라벨링 기준(크랙·꺾임 판정 기준 등)은 이번 조사에서 확인되지 않았습니다. 평가서 최종본에는 데이터셋 통계(이미지 수, 클래스 분포, train/val 비율)를 Colab 측 원본 또는 `dataset_*` 폴더를 직접 스캔하여 추가하는 것을 권고합니다.

---

## 5. 학습 설정 (체크포인트 `train_args`에서 추출)

| 항목 | Part | Defect |
|---|---|---|
| epochs | 150 | 200 |
| imgsz | 1024 | 1024 |
| batch | 16 | 16 |
| optimizer | auto | auto |
| lr0 | 0.01 | 0.01 |
| patience (early stopping) | 50 | 0 (미사용) |
| device | GPU 0 (Colab) | GPU 0 (Colab) |
| pretrained | True | True |
| 학습 완료 일시(체크포인트 기준) | 2026-10-02T14:38 UTC | 2026-10-02T15:29 UTC |

---

## 6. 평가 결과

### 6.1 학습 시점 검증 지표 (체크포인트 내장 `train_metrics`, best epoch 기준)

**Part 모델**

| | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Box | 0.98273 | 0.98529 | 0.99398 | 0.93818 |
| Mask | 0.98480 | 0.98381 | 0.99299 | **0.90110** |

**Defect 모델**

| | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Box | 0.98400 | 0.99231 | 0.98754 | 0.85840 |
| Mask | 0.96086 | 0.96923 | 0.96350 | **0.65504** |

### 6.2 Jetson 독립 재검증 (`benchmark/run.log`, PyTorch 네이티브, imgsz=640, held-out 42장/92 instances) — **Defect 모델만 완료**

| | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Box | 0.960 | 0.984 | 0.983 | 0.804 |
| Mask | 0.945 | 0.969 | 0.952 | **0.563** |

- Part 모델은 export 단계에서 벤치마크 스크립트가 중단되어 **Jetson 상 독립 재검증 수치가 확보되지 않았습니다.**
- Defect 모델의 경우 학습 시점(0.655)과 Jetson 재검증(0.563) 사이 약 9%p 차이가 존재하며, 주된 원인은 **검증 해상도 차이(학습 1024 vs 재검증 640)**로 추정됩니다.

### 6.3 배포 포맷별 정확도 (ONNX / TensorRT)

| 포맷 | mAP50 | mAP50-95 | 추론 속도(FPS) | 비고 |
|---|---|---|---|---|
| PyTorch (.pt) | 0.983 | 0.804 (Box) | 3.68 | 기준값 |
| ONNX | 0.0 | 0.0 | 1.81 | 검증 경로 오류로 추정, 실 추론 자체는 동작 |
| TensorRT FP32 | 0.0 | 0.0 | 3.87 | 동일 |
| TensorRT FP16 | 0.0 | 0.0 | 4.09 | **실제 배포 포맷** — 정확도 미검증 상태 |

> **리스크**: 실제 Jetson 운영에 사용되는 포맷은 `best_fp16.engine`입니다. 벤치마크 스크립트에서 이 포맷의 mAP가 0.0으로 측정된 것이 실제 정확도 저하가 아니라 **검증 스크립트의 후처리(NMS/디코딩)가 End2End export 출력 포맷과 맞지 않아 발생한 측정 오류**인지 먼저 확인해야 합니다. 이 리스크가 해소되지 않으면, 운영 환경에서 실제로 보장되는 정확도는 **현재 수치로 증명되지 않은 상태**입니다.

### 6.4 `sem_loss`(보조 시맨틱 손실) 활성화 여부

- Part 모델: 150 epoch 전 구간 `val/sem_loss = 0.0`
- Defect 모델: 200 epoch 전 구간 `val/sem_loss = 0.0`
- 아키텍처 모듈 목록에도 별도 시맨틱 헤드가 존재하지 않음 → 이번 파인튜닝에서는 `sem_loss`가 성능에 기여하지 않았습니다. (상세 분석: [`yolo26-vs-yolov8-architecture-comparison.md`](./yolo26-vs-yolov8-architecture-comparison.md))

### 6.5 YOLOv8n-seg 대비 비교

- Jetson 환경 및 저장소 전체(`database/migrations`, `docs/`, `scripts/` 등)에서 YOLOv8n-seg 관련 가중치, 학습 로그, 평가 기록을 탐색하였으나 **발견되지 않았습니다.**
- 따라서 "기존 모델 대비 X%p 향상"이라는 비교 서술은 **현재 근거 자료 없이는 평가서에 포함할 수 없습니다.** Colab 측에 YOLOv8n-seg 학습 기록이 남아있다면 해당 `results.csv`를 확보하여 본 평가서에 별첨하는 것을 권고합니다.

---

## 7. 종합 결론

| 항목 | 판정 |
|---|---|
| 모델 자체 정밀도(PyTorch, 학습 조건) | 우수 (Mask mAP50-95: Part 0.901 / Defect 0.655~0.804) |
| 기존 모델(YOLOv8n-seg) 대비 개선 입증 | **미입증** — 비교 대상 자료 부재 |
| 실 배포 포맷(TensorRT FP16) 정확도 | **미검증** — 벤치마크 스크립트 수정 후 재측정 필요 |
| 학습-배포 해상도 일치 여부 | **불일치** (학습 1024 / 배포·벤치마크 640) |
| 데이터셋 규모·분포 문서화 | **불충분** — 통계 보강 필요 |

**권고**: 운영 전 다음 3가지를 반드시 해소할 것을 권고합니다.
1. 벤치마크 스크립트의 ONNX/TensorRT 검증 경로를 수정하여 `best_fp16.engine`의 실제 mAP를 측정.
2. 배포 추론 해상도를 학습 해상도(1024)와 일치시키거나, 640 해상도로 재학습/재검증.
3. YOLOv8n-seg 베이스라인 학습 기록을 Colab에서 회수하여 정량 비교표를 완성.

---

## 8. 부록 — 원자료 출처

- 체크포인트: `/home/jetson/project/smart_factory/aoi/models/mosfet_{part,defect}_v5-26/weights/best.pt`
- 벤치마크 로그: `/home/jetson/project/smart_factory/aoi/benchmark/run.log`
- 데이터셋 정의: `/home/jetson/project/smart_factory/aoi/datasets/data_{part,defect}.yaml`
- 아키텍처 비교 상세: [`yolo26-vs-yolov8-architecture-comparison.md`](./yolo26-vs-yolov8-architecture-comparison.md)
