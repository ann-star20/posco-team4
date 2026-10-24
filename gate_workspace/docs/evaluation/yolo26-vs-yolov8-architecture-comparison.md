# YOLOv8n-seg → YOLO26n-seg 아키텍처 비교 및 성능 재해석

**대상 모델**: MOSFET 비전 검사 — 부품 탐지(Stage 1, Part), 결함 탐지(Stage 2, Defect)
**검증 환경**: Jetson Orin (192.168.10.253), `/home/jetson/project/smart_factory/aoi/models/{mosfet_defect_v5-26, mosfet_part_v5-26}/weights/best.pt`
**검증 방법**: `best.pt` 체크포인트에 포함된 `train_args`, `train_metrics`, `train_results`, `model.yaml`을 직접 로드하여 확인 (Ultralytics 8.4.118, torch 2.8.0)
**작성일**: 2026-10-23

> 이 문서는 사용자가 작성한 초안("YOLOv8n-seg 대비 YOLO26n-seg 성능 향상 원인 분석")의 핵심 주장을 Jetson에 남아있는 실제 체크포인트/로그와 대조하여, **사실로 확인된 부분**과 **근거가 부족하거나 수정이 필요한 부분**을 구분한 재해석본입니다.

---

## 1. 검증 결과 요약

| 주장 | 초안 내용 | 실측/확인 결과 | 판정 |
|---|---|---|---|
| 아키텍처가 YOLO26n-seg인가 | YOLO26n-seg 파인튜닝 | `model.yaml`에서 `yolo_file: yolo26n-seg.yaml`, `end2end: True`, 139 layers, 2,689,469 params, 9.1 GFLOPs 확인 | **사실** |
| C2PSA 모듈 존재 | 백본/넥에 C2PSA 통합 | 모듈 목록에 `C2PSA`, `PSABlock`, `Attention` 실제 존재 (백본 마지막 블록) | **사실** |
| `sem_loss`가 성능 향상의 핵심 원인 | 보조 시맨틱 손실이 백본 피처 품질을 근본적으로 개선 | `train_results['val/sem_loss']`가 Defect(200 epoch), Part(150 epoch) **전 구간에서 0.0** 으로 고정. 아키텍처 모듈 목록에도 별도 시맨틱 헤드 없음 | **근거 없음 — 수정 필요** |
| Stage 1 (Part) mAP50-95: 0.812 → 0.928 | YOLOv8n-seg 대비 +14.3%p | YOLOv8n-seg 비교 대상 모델/로그가 Jetson 어디에도 없음(검증 불가). YOLO26n-seg 자체 학습-시점 검증값은 Box 0.938 / Mask 0.901 | **베이스라인 검증 불가, YOLO26 수치는 근접하지만 불일치** |
| Stage 2 (Defect) mAP50-95: 0.541 → 0.735 | YOLOv8n-seg 대비 +35.8%p | 베이스라인 검증 불가. YOLO26n-seg 학습-시점 Mask mAP50-95 = **0.655**, Jetson 재검증(42장) Mask mAP50-95 = **0.563** — 두 실측치 모두 0.735보다 낮음 | **과대 서술 — 수정 필요** |
| `imgsz=1024` 고해상도 환경이 결함 경계 보존에 기여 | 핵심 원인으로 서술 | 학습은 실제로 `imgsz=1024`로 수행(확인됨). 그러나 Jetson 배포/벤치마크 파이프라인은 `imgsz=640`으로 export·검증됨 — **학습 해상도와 배포 해상도 불일치** | **절반만 사실 — 배포 단계 설명 보강 필요** |
| ONNX/TensorRT 변환 후 정확도 | 언급 없음 | ONNX, TensorRT FP32/FP16 엔진에서 `mAP50=0.0, mAP50-95=0.0` (NMS/디코딩 경로 문제로 추정, 실제 추론 품질 문제가 아닐 가능성) | **신규 발견 — 배포 전 반드시 재확인 필요** |

---

## 2. 확인된 아키텍처 사실

### 2.1 모델 구조 (체크포인트 `model.yaml`에서 추출)

```
nc: 2 (defect) / 3 (part)
end2end: True        # NMS-free 추론 (YOLOv8에는 없던 구조)
reg_max: 1
backbone 마지막 블록: SPPF → C2PSA (Polarized Self-Attention)
head: Segment26 / Proto26  (YOLOv8의 Segment/Proto를 대체하는 YOLO26 전용 세그멘테이션 헤드)
scale: n (nano) — 2,689,469 params, 9.1 GFLOPs, 139 layers(fused)
```

- `C2PSA`, `PSABlock`, `Attention` 모듈이 실제 state_dict에 존재합니다. 초안에서 설명한 "국소적 CNN 필터만으로 포착하기 어려운 글로벌 공간 관계를 어텐션으로 보완한다"는 서술은 구조적으로 타당합니다.
- `end2end: True`는 YOLO26의 또 다른 핵심 차이점입니다. YOLOv8은 NMS(Non-Max Suppression) 후처리가 필요하지만 YOLO26은 디코딩 단계에서 중복 박스를 제거하도록 학습됩니다. 이는 초안에 없던 내용이므로 **보강 포인트**로 추가 권장합니다.

### 2.2 `sem_loss`에 대한 정정

초안은 "보조 시맨틱 손실(`sem_loss`)이 백본 피처 품질을 끌어올려 결함 경계 유실을 막았다"고 설명했으나, 실제 체크포인트의 `train_results['val/sem_loss']` 배열은 Defect 모델 200epoch, Part 모델 150epoch **전 구간에서 정확히 0.0**입니다. 또한 모듈 목록에 시맨틱 전용 헤드가 없으므로, 이번 파인튜닝 실행에서는 `sem_loss` 항목이 로그 필드로만 존재할 뿐 실제로 가중치 업데이트에 기여하지 않았다고 판단됩니다.

> **결론**: 이번 파인튜닝에서 Stage 2 성능 향상의 원인을 `sem_loss`로 서술하는 것은 현재 데이터로 뒷받침되지 않습니다. 성능 향상은 ① `C2PSA` 어텐션, ② `end2end` NMS-free 헤드, ③ `imgsz=1024` 학습 해상도, ④ `Segment26/Proto26` 마스크 헤드 고도화의 조합으로 설명하는 것이 더 정확합니다. `sem_loss`를 실제로 활성화하려면 Ultralytics 학습 커맨드에 해당 보조 헤드를 켜는 옵션(현재 버전 기준 별도 플래그 필요)을 확인해야 합니다.

---

## 3. 성능 지표 재해석 (실측 기준)

### 3.1 Stage 1 — Part 모델 (`mosfet_part_v5-26`)

학습 조건: `yolo26n-seg.pt` 사전학습 → 파인튜닝, epochs=150, imgsz=1024, batch=16, patience=50, data=`data_part.yaml` (classes: body, lead, tab)

| 지표 | Box | Mask |
|---|---|---|
| Precision | 0.98273 | 0.98480 |
| Recall | 0.98529 | 0.98381 |
| mAP50 | 0.99398 | 0.99299 |
| **mAP50-95** | **0.93818** | **0.90110** |

- YOLOv8n-seg 베이스라인(0.812) 비교는 Jetson/저장소 어디에도 해당 실행 기록이 없어 **검증 불가**합니다. 초안의 0.928이라는 값은 Box mAP50-95(0.938)와 근접하지만 Mask mAP50-95(0.901)와는 차이가 있어, 어떤 지표를 기준으로 작성된 수치인지 명시가 필요합니다.
- Jetson 상에서 별도로 재검증(export/benchmark 스크립트)을 시도했으나 해당 런은 export 단계에서 중단되어 **독립적인 재검증 수치는 확보되지 않았습니다**.

### 3.2 Stage 2 — Defect 모델 (`mosfet_defect_v5-26`)

학습 조건: `yolo26n-seg.pt` 사전학습 → 파인튜닝, epochs=200, imgsz=1024, batch=16, patience=0, data=`data_defect.yaml` (classes: crash, bend)

| 지표 | Box | Mask |
|---|---|---|
| Precision | 0.98400 | 0.96086 |
| Recall | 0.99231 | 0.96923 |
| mAP50 | 0.98754 | 0.96350 |
| **mAP50-95** | **0.85840** | **0.65504** |

Jetson 재검증 (`benchmark/run.log`, PyTorch 네이티브, held-out 42장/92 instances, **imgsz=640**):

| 지표 | Box | Mask |
|---|---|---|
| Precision | 0.960 | 0.945 |
| Recall | 0.984 | 0.969 |
| mAP50 | 0.983 | 0.952 |
| **mAP50-95** | **0.804** | **0.563** |

- 초안이 제시한 "YOLOv8n-seg 0.541 → YOLO26n-seg 0.735"에서 0.735는 **학습 시점 값(0.655)과 Jetson 재검증 값(0.563) 중 어느 것과도 일치하지 않으며, 둘 다 0.735보다 낮습니다.** 이 수치는 현재 근거가 확인되지 않으므로 보고서에서 삭제하거나 "추정치"로 명확히 구분해야 합니다.
- 학습 시점(0.655, imgsz=1024)과 Jetson 재검증(0.563, imgsz=640) 사이의 약 9%p 격차는, 초안이 성능 향상의 근거로 든 "1024×1024 고해상도 환경"이 실제 배포 파이프라인에는 적용되지 않고 있음을 보여줍니다. 즉 운영 환경에서는 고해상도 효과가 온전히 재현되지 않을 가능성이 있습니다.
- ONNX·TensorRT(FP32/FP16) export 버전은 동일 벤치마크에서 `mAP50=0.0`을 기록했습니다. 추론 자체(`yolo predict`)는 정상 동작하는 것으로 보이므로, 이는 모델 품질 문제가 아니라 **벤치마크 스크립트의 검증(val) 경로가 export 포맷의 출력 포맷(End2End 디코딩)과 맞지 않아 발생한 것으로 추정**됩니다. 실제 배포에 사용되는 `best_fp16.engine`의 정확도는 현재 **신뢰 가능한 수치가 없는 상태**이므로 평가서에 "미검증"으로 명시하고 별도 검증이 선행되어야 합니다.

---

## 4. 핵심 개념 설명 (초안 유지 — 구조적으로 타당함)

아래 개념 설명은 Ultralytics YOLO26 아키텍처 문서 및 체크포인트에서 확인된 구조와 부합하므로 그대로 유지합니다.

- **셀프 어텐션 / 글로벌 공간 관계**: CNN 로컬 필터 대비 어텐션이 원거리 피처 간 관계를 직접 참조한다는 설명은 타당합니다.
- **C2PSA**: CSP 구조에 Polarized Self-Attention을 결합해 고해상도에서도 연산 효율을 유지한다는 설명은 실제 모듈 구성과 일치합니다.
- **마스크 프로토타입(YOLACT 방식)**: `Proto26` 모듈이 이 역할을 수행하며, 설명은 타당합니다.
- **mAP50-95 / IoU 임계값**: 지표 정의 자체는 정확합니다. 다만 위에서 지적한 것처럼 Stage 2 실제 수치(0.655 또는 0.563)가 초안의 0.735보다 낮으므로, "폭발적 성장"이라는 표현은 실측 기준으로 완화해야 합니다.

---

## 5. 보고서 작성 시 권고사항

1. **YOLOv8n-seg 베이스라인 수치의 출처를 명시**하세요. Colab 학습 기록(results.csv, args.yaml 등)이 남아있다면 해당 파일을 근거 자료로 첨부해야 합니다. 현재 Jetson에는 해당 자료가 전혀 없습니다.
2. **`sem_loss` 관련 서술을 삭제하거나 "본 파인튜닝 실행에서는 비활성 상태였음"으로 정정**하세요.
3. **Stage 2 mAP50-95 수치를 0.655(학습 시점) 또는 0.563(Jetson 재검증, 640px)으로 교체**하고, 두 값의 차이(해상도 불일치)를 명시하세요.
4. **ONNX/TensorRT export 정확도 미검증 이슈를 리스크 항목으로 추가**하고, 벤치마크 스크립트의 검증 경로를 수정한 뒤 재측정할 것을 권고사항에 포함하세요.
5. **학습(`imgsz=1024`)과 배포(`imgsz=640`) 해상도 불일치**를 아키텍처 비교와 별도로 "배포 파이프라인 이슈"로 분리 기술하세요.
