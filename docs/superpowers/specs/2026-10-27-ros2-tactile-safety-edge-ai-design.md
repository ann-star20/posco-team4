# ROS2 기반 촉각 안전 판별 Edge AI 프로젝트 기획서

작성일: 2026-10-27  
상태: 검토 대기  
프로젝트 유형: 개인 포트폴리오 / Headless Edge AI / ROS2 / Jetson

## 1. 프로젝트 소개

이 프로젝트는 실제 센서나 로봇 그리퍼가 없는 환경에서 공개 촉각·힘 센서 데이터셋을 실제 센서 스트림처럼 ROS2 토픽으로 재생하고, Jetson Orin Nano 8GB에서 접촉 상태와 미끄러짐 위험을 실시간 판별하는 Edge AI 시스템을 구축한다.

핵심 결과물은 단순 분류 모델이 아니라 다음 전체 경로다.

```text
공개 센서 데이터
  -> 데이터 검증·정규화
  -> ROS2 timestamp 기반 스트리밍 재현
  -> window 생성·특징 추출
  -> 접촉/미끄러짐 판별
  -> Jetson TensorRT 최적화
  -> 안전 이벤트 발행
  -> 결과·모델·성능 메트릭 저장
  -> 경량 운영 대시보드
```

이 프로젝트가 증명하려는 지원자 역량은 다음과 같다.

- 시계열 센서 데이터의 구조 파악, 전처리, 라벨 검증 및 재현 가능한 split 설계
- PyTorch 기반 기준 모델과 딥러닝 모델의 직접 설계·학습·평가
- ROS2 기반 데이터 계약과 실시간 추론 노드 통합
- ONNX/TensorRT 포팅, FP16/INT8 최적화 및 정확도 회귀 검증
- Jetson의 latency, memory, power, temperature를 함께 고려하는 운영 최적화
- 모델 버전, 원시 측정치, 평가 결과를 보존하는 AI Engineering 실무

## 2. 의도와 포지셔닝

사용자는 시스템 백엔드 개발 경력 5년과 ROS2 통신·Jetson·컴퓨터 비전 모델 운영 경험을 보유하고 있다. 본 프로젝트는 이 경험을 센서 시계열 AI와 TinyML/Edge AI 방향으로 확장해 다음 포지션에 대응한다.

- 로봇·그리퍼 센서 AI Engineer
- Edge AI / On-device AI Engineer
- 스마트팩토리 Applied AI Engineer
- AI 모델 서빙·MLOps Engineer

포트폴리오의 핵심 메시지는 다음과 같다.

> 공개 촉각·힘 센서 데이터를 ROS2 실시간 스트림으로 재현하고, 안전 판별 모델을 Jetson에 배포해 모델 품질과 end-to-end 지연시간, 전력 효율을 함께 최적화했다.

센서를 직접 수집하지 않았으므로 센서 하드웨어 개발이나 현장 수집 경험을 주장하지 않는다. 대신 데이터 계약, 재생 가능성, 모델링, Edge 배포, 측정 체계를 깊게 증명한다.

## 3. 목표, 비목표, 실패 조건

### 3.1 목표

1. IntelliMan 공개 데이터의 구조, 단위, sampling 특성, label 의미를 문서화한다.
2. 공개 데이터를 원본 시간 간격 또는 설정 가능한 배속으로 ROS2 토픽에 재생한다.
3. 접촉 상태와 미끄러짐 위험을 분류하는 기준 모델과 1D 딥러닝 모델을 구축한다.
4. 동일한 검증 데이터로 PyTorch FP32, ONNX, TensorRT FP16, 가능한 경우 TensorRT INT8을 비교한다.
5. 모델 품질과 추론 지연뿐 아니라 ROS2 end-to-end latency, memory, power, temperature, energy per inference를 측정한다.
6. 모델·데이터·환경의 identity와 원시 측정 결과를 함께 보존한다.
7. 데이터·모델·실험 산출물은 3GB 안팎으로 관리하고, Docker·관측성·DB cache까지 포함한 전체 프로젝트 운영 공간은 사용 가능한 10GB 안에서 최대 8GB를 목표로 하며 최소 2GB의 여유 공간을 남긴다.

### 3.2 비목표

- 실제 그리퍼 제어기나 물리 로봇암 제어
- 센서 배선, MCU 펌웨어, ADC, 하드웨어 calibration
- Unity 또는 Gazebo 기반 물리 시뮬레이션
- 대규모 Kubernetes 클러스터 구축
- 로컬 대형 LLM 운영
- Qualcomm QNN/SNPE/AIMET의 실제 실행
- 공개 데이터셋 여러 개를 센서 의미가 다른 상태로 억지로 하나의 학습셋에 병합

### 3.3 실패 조건

- 파일을 읽어 배치 평가하는 것만 구현하고 ROS2 스트리밍 경로가 없는 경우
- train/test에 같은 trial 또는 인접한 중복 window가 섞여 성능이 부풀려지는 경우
- accuracy 하나만 보고 위험 이벤트의 false negative를 측정하지 않는 경우
- Jetson 성능 수치에 warm-up, 반복 횟수, 전력 모드, 모델 hash가 없는 경우
- FP16/INT8 변환 후 정확도 동등성을 검증하지 않는 경우
- 공개 데이터 사용임을 숨기거나 센서 수집 경험으로 표현하는 경우
- 측정 근거 없이 비용 절감률을 주장하는 경우

## 4. 접근 방식과 선택 이유

### 접근 A: Unity/Gazebo를 포함한 로봇 시뮬레이션

시각적인 데모와 로봇 동작 표현에는 유리하지만 디스크와 GPU 자원을 많이 사용한다. 촉각 신호의 실제 물리 분포를 재현하기도 어렵고, 목표 포지션의 핵심인 센서 데이터 처리와 Edge 추론 최적화가 흐려진다. 선택하지 않는다.

### 접근 B: 실제 저가 센서를 구매해 신규 데이터 수집

센서 수집·calibration·firmware 경험까지 증명할 수 있으나 현재 센서가 없고 프로젝트 시작이 하드웨어 조달에 종속된다. 본 MVP에서는 선택하지 않는다. 향후 MPU6050, 로드셀+HX711 또는 FSR 센서 하나를 추가하는 확장 경로로 남긴다.

### 접근 C: 공개 데이터 기반 Headless ROS2 Replay + Jetson Edge AI

작은 공개 데이터셋으로 즉시 시작할 수 있고, ROS2 계약과 추론 노드를 실제 센서 교체가 가능한 구조로 설계할 수 있다. 저장공간을 최소화하면서 모델링·포팅·최적화·운영 측정을 모두 보여줄 수 있다.

**선택:** 접근 C. 사용자가 선택한 방향이며 현재 장비·저장공간·지원 포지션에 가장 적합하다.

## 5. 사용 데이터셋

### 5.1 MVP 데이터셋: IntelliMan Contact/Slip

- 원본: https://zenodo.org/records/18759556
- DOI: `10.5281/zenodo.18759556`
- 파일: `Dataset_Contact_slippage_ICECS.zip`
- 크기: 약 76.9MB
- 입력: soft finger cap의 8채널 PVDF 촉각 신호
- reference/ground truth: 6축 force/torque 센서
- 동작: press, slide, release
- 표면: smooth, rough
- 수집 규모: 2명, 표면별 인당 150 trial로 설명됨
- 제안 task:
  - 접촉 상태 분류: no-contact / contact / release
  - 안전 판별: stable contact / slip-risk 또는 slip / non-slip
  - 선택적 보조 task: smooth / rough 분류

Zenodo 레코드의 라이선스 필드가 현재 화면에서 명시적으로 확인되지 않으므로 다운로드·학습은 가능하더라도 원본 데이터 재배포 여부는 별도 확인한다. 저장소에는 데이터 다운로드 방법과 DOI만 기록하고 원본 ZIP은 커밋하지 않는다.

### 5.2 현재 로컬 데이터 구조와 1차 구조 감사

현재 데이터는 다음 위치에 압축 해제되어 있다.

```text
data/Dataset_Contact_slippage_ICECS/
  PVDF_roughtex/
    Voltage_TXH-Texture 1-Hardness 1-T9sec-t1
    ...
    Voltage_TXH-Texture 1-Hardness 1-T9sec-t150
  PVDF_softtex/
    Voltage_TXH-Texture 2-Hardness 1-T9sec-t1
    ...
    Voltage_TXH-Texture 2-Hardness 1-T9sec-t150
```

2026-10-27 로컬 파일을 read-only로 조사한 1차 결과는 다음과 같다.

| 항목 | PVDF_roughtex | PVDF_softtex |
|---|---:|---:|
| trial 파일 수 | 150 | 150 |
| 비압축 크기 | 398.47MB | 398.11MB |
| 파일당 행 수 최소~최대 | 15,874~16,290 | 15,887~16,290 |
| 파일당 평균 행 수 | 16,194.83 | 16,179.99 |
| 열 수 | 9 | 9 |
| 구분자 | tab | tab |
| header | 없음 | 없음 |
| label 고유값 | 0, 1, 2, 3 | 0, 1, 2, 3 |
| 파일당 label 전환 수 | 3 | 3 |

관찰된 각 행은 앞의 실수형 8개 값과 마지막 label 1개로 구성된다. 파일명과 값 범위를 보면 앞 8열은 PVDF 센서 voltage channel로 추정되지만, 공식 schema를 확인하기 전까지 임시 이름 `pvdf_ch_1`~`pvdf_ch_8`을 사용하고 단위는 `unknown`으로 유지한다.

대표 trial의 label run은 대체로 다음 순서를 보였다.

```text
1: 약 5,429행 -> 2: 약 5,430행 -> 3: 약 5,221행 -> 0: 마지막 1행
```

논문은 contact onset, slippage, release 세 event를 설명하므로 `1/2/3`이 이 순서에 대응할 가능성이 있지만 아직 확정하지 않는다. 마지막 한 행의 `0`은 종료 sentinel, padding 또는 별도 class인지 확인하기 전까지 학습 대상에서 제외하지도 class로 확정하지도 않는다.

파일명의 `T9sec`를 9초 trial 길이로 해석하면 평균 sampling rate는 rough 약 1,799.43Hz, soft 약 1,797.78Hz로 추정된다. 그러나 timestamp 열이 없고 trial별 행 수가 다르므로 공식 sampling rate와 acquisition drop 여부를 원 논문·저자 설명에서 확인해야 한다. 추정 sampling rate는 탐색용으로만 사용하고 확정 metadata와 분리한다.

### 5.3 데이터 구조·단위·sampling·label 조사 항목

#### 파일과 행·열 구조

- 두 폴더의 파일 수와 trial id `1~150` 완전성
- 빈 파일, 읽기 실패, 중복 파일, 중복 trial 검출
- 파일별 byte, 행 수, 열 수, delimiter, encoding 일관성
- 모든 값의 numeric parse 가능 여부와 NaN/Inf/빈 값
- 8개 입력 열과 label 열 외의 예외 행 존재 여부
- 첫 행·마지막 행, 잘린 파일, 비정상적으로 짧거나 긴 trial
- exact duplicate row와 장시간 constant run

#### 열 의미와 단위

- 8개 열이 실제로 8개 PVDF sensor channel인지 확인
- voltage의 단위가 V인지 mV인지, ADC 변환 후 값인지 확인
- channel 물리 배치와 sensor index의 의미
- gain, offset, filtering, ADC resolution, saturation range
- 폴더명의 `roughtex`, `softtex`, 파일명의 `Texture`, `Hardness`, `T9sec`, `tN` 의미
- `softtex`가 공식 설명의 smooth surface와 같은 의미인지 확인

#### sampling 특성

- 공식 nominal sampling rate
- timestamp 미포함 이유와 파일 내 sample 간격 가정
- trial별 유효 duration과 행 수 차이 원인
- sampling drop 또는 acquisition jitter 여부
- anti-alias filter와 hardware/software filtering 여부
- downsampling 가능한 최소 주파수와 aliasing 위험

#### label 의미

- label `1`, `2`, `3`, `0`의 공식 event mapping
- label 생성 주체와 생성 규칙: threshold, F/T reference, 수동 annotation 여부
- event transition 시점의 정확도와 label delay
- 마지막 `0` 한 행의 의미
- 모든 trial이 동일한 event 순서로 수집됐는지
- rough/soft가 target label인지 domain/condition metadata인지

조사 결과는 확인된 사실, 데이터로부터 계산한 값, 합리적 추정, 미확인 항목의 네 등급으로 구분한다.

### 5.4 EDA 범위

#### 데이터 품질 EDA

- trial/texture별 행 수·파일 크기 분포
- 채널별 min, max, mean, median, standard deviation, quantile
- baseline voltage, offset, drift, saturation, clipping
- 결측·무한값·이상치·constant channel 비율
- trial 내부와 trial 간 signal scale 차이
- 채널 간 correlation과 중복 센서 가능성
- texture별, label별 sample 수와 지속시간 불균형

#### 시간 영역 EDA

- 전체 trial과 event transition 주변 파형
- label 구간별 평균 waveform과 confidence band
- first difference, slope, RMS, peak-to-peak, zero crossing
- contact/slip/release 전후 peak amplitude와 response delay
- event별 duration과 transition index 분포
- trial 정규화 전후 신호 비교

#### 주파수 영역 EDA

- PSD, FFT, STFT 또는 spectrogram
- label·texture별 dominant frequency와 band energy
- slippage 구간의 주파수 특성이 contact/release와 분리되는지
- downsampling 전후 정보 손실과 aliasing 검사
- window length가 frequency resolution과 latency에 미치는 영향

#### 일반화·누수 EDA

- rough와 soft 간 feature distribution shift
- trial 단위 군집과 outlier trial
- 인접 sample/window의 자기상관
- random row/window split이 성능을 과대평가하는 정도
- trial-disjoint split과 가능하면 subject-disjoint split 비교
- 같은 event 순서와 위치 자체를 모델이 shortcut으로 학습하는지

### 5.5 분석 목적과 질문 목록

EDA 결과를 보고 다음 분석 목적 중 MVP와 확장 task를 확정한다.

1. **접촉 event 분류:** tactile-only 신호로 contact onset, slip, release를 구분할 수 있는가?
2. **미끄러짐 조기 경보:** slip label 시작 전에 위험을 예측할 수 있으며 최소 warning horizon은 얼마인가?
3. **표면 조건 일반화:** rough에서 학습한 특징이 soft에서도 유지되는가, 반대 방향은 어떤가?
4. **센서 채널 기여도:** 8개 channel 중 안전 판별에 핵심적인 channel은 무엇이며 일부 channel만으로 성능을 유지할 수 있는가?
5. **경량화 가능한 sampling:** 원 sampling rate를 얼마나 낮춰도 Safety Recall과 FNR을 유지할 수 있는가?
6. **window-latency trade-off:** window 길이와 stride가 품질, warning delay, Jetson latency에 어떤 영향을 주는가?
7. **threshold vs ML:** 원 논문의 threshold 방식과 통계 특징 모델, 1D CNN/TCN 사이의 성능·해석성·연산량 차이는 무엇인가?
8. **domain shift 탐지:** texture 또는 trial 조건 변화가 confidence와 calibration에 어떤 영향을 주는가?
9. **센서 이상 탐지:** channel 고정, drift, dropout을 감지하고 안전하게 실패할 수 있는가?
10. **Edge 최적화:** downsampling, channel pruning, FP16/INT8이 품질·latency·power에 미치는 영향은 무엇인가?

MVP의 우선 분석 목적은 `접촉 event 분류`, `미끄러짐 조기 경보`, `sampling/window trade-off`, `Edge 최적화`로 한다. texture 분류는 안전 판별을 방해하지 않는 보조 분석으로 둔다.

### 5.6 EDA 산출물

- `dataset_manifest.csv`: 파일, texture, trial id, byte, row count, duration 추정, schema 상태, hash
- `schema_report.json`: delimiter, column count, dtype, unit status, label values
- `label_mapping.md`: 공식 근거, label 의미, 미확인 사항
- `eda_summary.md`: 핵심 발견과 모델링 결정
- `eda_metrics.csv`: trial/channel/event별 통계
- EDA plot: 파형, transition overlay, 분포, correlation, PSD/STFT, outlier
- `split_manifest.csv`: trial/subject 단위 train/validation/test 배정
- 데이터 카드: 출처, 라이선스, 수집 조건, 제한사항, leakage 위험

EDA 산출물은 전체 원시 데이터를 복제하지 않고 원본에서 다시 생성 가능하도록 한다. plot은 대표 결과만 보존하고 대량 중간 이미지는 생성하지 않는다.

### 5.7 데이터 사용 원칙

- dataset hash와 다운로드 일자를 기록한다.
- label 정의, 물리 단위, sampling rate가 원자료에서 확인되지 않으면 추정하지 않고 `unknown`으로 기록한다.
- 데이터셋 설명상 6축 force/torque는 ground truth 생성에 사용됐으므로 MVP 주력 모델의 입력에서 제외한다. label 생성과 독립적이라는 근거가 확인될 때만 별도 탐색 실험에 사용한다.
- trial을 최소 독립 단위로 사용하고 동일 trial에서 생성된 window가 train과 test에 동시에 들어가지 않도록 한다.
- subject 정보가 충분하면 subject-disjoint 평가를 추가한다.
- 데이터 누수를 방지하기 위해 scaler와 feature extractor는 train split만으로 fit한다.
- 원본 시계열, 정규화 시계열, 모델 입력 window를 구분한다.

### 5.8 후속 데이터셋

MVP 완료 후 필요할 때만 다음 데이터셋을 별도 task로 추가한다.

- SLID-CH: IMU 기반 slip 판별. 대용량이므로 MVP에는 포함하지 않는다.
- RCT: 촉각 이미지·접촉력 기반 소재 분류. 데이터 의미와 모델 입력이 다르므로 IntelliMan과 합쳐 학습하지 않는다.

## 6. 기술 스택

| 영역 | 기술 |
|---|---|
| 언어 | Python 3 |
| 학습 | PyTorch, scikit-learn |
| 데이터 | NumPy, pandas 또는 Polars, SciPy |
| ROS | ROS2, `rclpy`, `rosbag2`는 짧은 fixture에 한해 선택 사용 |
| 메시지 | `std_msgs`, `geometry_msgs/WrenchStamped`, 프로젝트 전용 tactile message |
| 모델 교환 | ONNX |
| Edge 추론 | TensorRT FP16, TensorRT INT8 가능성 검증 |
| 장비 | Jetson Orin Nano 8GB |
| API | FastAPI |
| 저장소 | 로컬 개발은 SQLite, 운영 데모는 Aiven PostgreSQL 또는 기존 중앙 PostgreSQL |
| 관측성 | JSONL 원시 로그 + Prometheus; retention과 volume 상한 적용 |
| 시각화 | Grafana 기본, 리소스 부족 시 경량 HTML/Plotly fallback |
| 패키징 | Docker 또는 ROS2 package; ARM64 이미지 분리 |
| 실험 추적 | 경량 JSON/CSV manifest 우선, 디스크 여유 시 MLflow 추가 |
| 품질 | pytest, ruff, mypy 선택 적용 |

## 7. 시스템 구조

```text
[Dataset Manifest + ZIP]
          |
          v
[dataset_player_node]
  - trial 선택
  - 원본 timestamp 보존
  - real-time / accelerated replay
          |
          +--> /tactile/raw
          +--> /wrench/reference       (평가·라벨 정렬 전용)
          +--> /dataset/ground_truth   (평가 모드에서만)
          |
          v
[sensor_window_node]
  - timestamp 정렬
  - 결측/이상값 처리
  - resampling
  - fixed-size window
  - normalization
          |
          v
[edge_inference_node]
  - backend 선택: pt / onnx / engine
  - contact/slip prediction
  - model identity 기록
          |
          +--> /contact_state
          +--> /slip_probability
          +--> /safety_event
          +--> /inference_metrics
          |
          v
[metrics_collector]
  - prediction + GT join
  - latency/jitter/drop
  - tegrastats power/temp/memory
  - SQLite 또는 Aiven PostgreSQL
  - JSONL/raw CSV
  - Prometheus metrics
          |
          v
[FastAPI Dashboard]
  - 현재 상태
  - trial replay 상태
  - 모델/엔진 버전
  - 품질·성능 비교
```

### 7.1 핵심 데이터 계약

모든 메시지는 다음 공통 필드를 보존한다.

- `trial_id`
- `sequence_number`
- `source_timestamp`
- `publish_timestamp`
- `sample_rate_hz` 또는 확인 불가 시 null
- `dataset_version`
- `label`은 평가 모드에서만 별도 토픽으로 전달

추론 결과는 다음을 포함한다.

- `prediction`
- `class_probabilities`
- `window_start_timestamp`, `window_end_timestamp`
- `inference_started_at`, `inference_completed_at`
- `model_name`, `model_sha256`
- `backend`, `precision`, `device`
- `preprocess_ms`, `inference_ms`, `postprocess_ms`, `end_to_end_ms`

ground truth를 inference input 메시지와 분리하여 모델이 label을 실수로 입력으로 사용하는 것을 방지한다.
같은 이유로 F/T reference 토픽은 MVP inference node가 구독하지 않는다.

## 8. 구현 기능 범위

### 8.1 데이터 계층

- 데이터 다운로드·무결성 확인 스크립트
- 로컬 두 texture 폴더와 300개 trial의 구조 감사
- header 없는 tab-delimited 9열 schema 검증과 schema report 생성
- 열 단위·sampling rate·label mapping의 공식 근거 추적
- trial manifest와 channel/event 통계 생성
- label 분포, transition, 누락값, 이상치, drift, saturation 리포트
- 시간·주파수 영역 EDA와 texture/domain 비교
- EDA 결과를 이용한 MVP 분석 목적과 모델 입력 결정
- trial/subject 단위 train/validation/test split
- window size와 stride를 설정 가능한 전처리기
- train-only normalization artifact 저장
- 재현 가능한 random seed와 split manifest 저장

### 8.2 ROS2 계층

- dataset player node
- tactile publisher와 평가 전용 force/torque reference publisher
- 실시간, 배속, step replay 모드
- 재생 중단·재시작·trial 전환
- timestamp 기반 sensor synchronizer
- window buffer 상한 설정
- inference node backend 교체
- safety event publisher
- 메시지 drop, queue depth, latency 계측

### 8.3 모델 계층

- 기준 모델: 통계 특징 + Logistic Regression, Random Forest 또는 XGBoost 중 하나
- 딥러닝 기준: 1D CNN
- 개선 모델: TCN 또는 경량 late-fusion network
- tactile 채널 ablation과 window/feature ablation
- F/T 입력 실험은 label 생성과 독립적이라는 근거가 확인될 때만 별도 결과로 분리
- class imbalance 처리 비교
- probability calibration과 safety threshold 선택
- false negative 중심 threshold 분석

### 8.4 Edge 배포 계층

- PyTorch checkpoint와 입력 schema 고정
- ONNX export 및 출력 동등성 검사
- TensorRT FP16 engine 생성
- calibration sample이 충분할 때만 INT8 engine 생성
- engine은 Jetson에서 생성하고 장비·TensorRT 버전을 manifest에 저장
- backend별 warm-up과 반복 벤치마크
- 장시간 soak test와 thermal throttling 관찰
- 실패 시 마지막 검증 engine으로 rollback할 수 있는 모델 선택 구조

### 8.5 운영·표현 계층

- 실험별 manifest와 raw JSON/CSV 저장
- 로컬 개발에서는 SQLite에 prediction, model, latency, device telemetry 저장
- 운영 데모에서는 Aiven PostgreSQL을 선택해 Jetson 로컬 디스크 사용량과 DB 운영 부담을 줄임
- FastAPI로 최근 이벤트와 비교 결과 제공
- Prometheus가 runtime·ROS2·Jetson 지표를 scrape하고 Grafana에서 상태와 비교 결과를 표시
- Prometheus를 사용할 수 없는 환경에서는 경량 웹 화면으로 센서 파형, slip probability, safety event, 성능 요약 표시
- README에 재현 절차, 데이터 출처, 제한사항, 결과표 게시

## 9. 모델 구성

### 9.1 기준 모델

각 tactile window에서 다음과 같은 통계·주파수 특징을 계산한다.

- mean, standard deviation, min, max, RMS
- peak-to-peak, slope, zero crossing
- 채널 간 correlation
- sampling rate가 확인된 경우 spectral energy와 dominant frequency

이 특징을 Logistic Regression 또는 tree 계열 모델에 입력해 딥러닝의 개선 폭을 검증한다.

### 9.2 1D CNN

```text
[B, channels, time]
  -> Conv1d + BatchNorm + ReLU
  -> Depthwise/Separable Conv1d blocks
  -> Global Average Pooling
  -> Contact head
  -> Slip safety head
```

작은 데이터셋과 Edge 배포를 고려해 파라미터 수와 연산량을 제한한다. 대형 Transformer는 MVP 범위에서 제외한다.

### 9.3 선택적 멀티모달 fusion

```text
8-channel tactile -> tactile encoder --+
                                       +-> fusion -> contact head
6-axis F/T       -> force encoder -----+          -> slip head
```

이 구조는 MVP 기본 경로가 아니다. IntelliMan 설명상 F/T가 contact/slip ground truth에 사용됐으므로 주력 결과는 tactile-only 모델로 산출한다. 원 논문과 데이터 schema를 조사해 F/T 입력이 label 생성과 독립적임을 입증할 수 있을 때만 late fusion을 탐색 실험으로 추가한다. 추가하더라도 tactile-only 결과를 대표 지표로 유지하고 fusion 결과에는 잠재적 leakage 여부를 명시한다.

### 9.4 모델 선택 기준

최고 accuracy만으로 모델을 선택하지 않는다. 다음 우선순위를 사용한다.

1. 위험 클래스 false negative 최소화
2. held-out trial 기준 Macro F1과 safety recall
3. Jetson P95 end-to-end latency
4. 모델 크기와 peak memory
5. energy per inference

## 10. 저장공간 절약 구성

1GB는 데이터·모델·결과물만을 위한 초기 목표였으며 Docker image, Python/ROS2 runtime, Prometheus/Grafana, DB volume까지 포함한 전체 예산으로는 지나치게 작다. 사용 가능한 약 10GB를 기준으로 **상시 사용량 8GB 이하, 안전 여유 2GB 이상**을 운영 목표로 한다. 빌드 중 임시 layer 때문에 10GB를 넘을 가능성이 있으면 build cache를 정리하거나 외부 저장소를 사용한 뒤 진행한다.

### 10.1 전체 저장공간 예산

| 항목 | 목표 예산 | 정책 |
|---|---:|---|
| 소스·문서 | 0.2GB | 대형 binary 금지 |
| 원본 데이터 | 0.9GB | 현재 비압축 약 797MB, Git 제외 |
| 전처리 cache·짧은 ROS fixture | 0.5GB | window on-the-fly 생성, 중복 방지 |
| 모델·ONNX·TensorRT engine | 0.7GB | best와 비교 대상만 유지 |
| benchmark·압축 로그 | 0.5GB | raw 결과 보존, 회전·압축 적용 |
| Python/ROS2 프로젝트 의존성 | 1.5GB | 기존 JetPack/ROS2 runtime 재사용 |
| 애플리케이션 Docker image·layer | 1.5GB | multi-stage build와 slim base 사용 |
| Prometheus·Grafana image/volume | 1.5GB | 짧은 retention과 volume 상한 적용 |
| 로컬 DB·기타 volume | 0.5GB | Aiven 사용 시 더 작아짐 |
| 예비 공간 | 최소 2.0GB | engine build·export 임시 파일과 장애 대응 |

표의 수치는 hard limit가 아니라 설계 예산이다. 실제 image 크기와 volume 증가량을 측정해 manifest에 기록한다.

### 10.2 배포 프로파일

| 프로파일 | 구성 | 예상 상시 사용량 | 용도 |
|---|---|---:|---|
| Lean MVP | native ROS2/JetPack + SQLite + 경량 dashboard | 3~5GB | 모델·ROS2·TensorRT 우선 검증 |
| Portfolio Demo | Lean MVP + Prometheus + Grafana + Aiven PostgreSQL | 6~8GB | 최종 데모 권장 |
| Full Local | Prometheus + Grafana + local PostgreSQL + MLflow | 8GB 초과 가능 | 현재 10GB 환경에서는 기본 비권장 |

Aiven PostgreSQL을 사용하면 로컬 PostgreSQL image와 data volume이 필요하지 않지만 네트워크 단절에 대비해 Jetson에는 bounded SQLite outbox를 유지한다. 연결 복구 후 중앙 DB로 재전송하고, local retention을 넘은 성공 전송 레코드는 삭제 또는 압축한다.

### 10.3 Jetson 컨테이너 정책

Jetson용 NVIDIA L4T/PyTorch image는 단독으로도 큰 공간을 사용할 수 있으므로 10GB 예산에서는 전체 ML runtime을 새 image에 중복 포함하지 않는 것을 기본으로 한다.

- JetPack에 포함된 CUDA/TensorRT와 기존 ROS2 환경을 우선 재사용한다.
- 학습은 PC 또는 별도 환경에서 수행하고 Jetson에는 inference artifact만 전달한다.
- Jetson에서는 inference node를 native ROS2 package로 실행하거나 host runtime을 활용하는 얇은 image를 사용한다.
- FastAPI, Prometheus, Grafana처럼 비교적 작은 운영 구성요소만 containerize한다.
- 완전한 L4T ML container가 필요하면 image 실제 크기를 먼저 확인하고 NVMe/외장 저장소 확보 또는 다른 component 제거 후 채택한다.

구체적인 정책은 다음과 같다.

- `data/raw`, `data/cache`, `artifacts/models`, benchmark raw output을 `.gitignore`에 둔다.
- 동일 원본의 중복 압축 해제본을 만들지 않는다.
- window는 가능하면 학습 시 생성하고, 고정 cache가 필요하면 split별 단일 압축 파일을 사용한다.
- 전체 rosbag를 반복 생성하지 않고 수 초 길이의 계약 테스트 fixture만 보존한다.
- Docker image, TensorRT engine, Python virtual environment를 결과물로 커밋하지 않는다.
- 대형 SLID-CH, PoseIt, 로컬 LLM은 MVP에서 다운로드하지 않는다.
- Prometheus는 기본 retention을 3일로 시작하고 maximum size 또는 volume 사용량을 관찰해 조정한다.
- Grafana는 dashboard provisioning 파일만 Git에 보존하고 runtime DB와 plugin cache는 제한한다.
- Docker build cache와 dangling image 사용량을 측정하되 자동 삭제는 명시적인 운영 절차로만 수행한다.
- MLflow와 Kubernetes는 현재 10GB 환경의 MVP 필수 의존성으로 두지 않는다.
- benchmark 원시 데이터는 보존하되 로그 회전과 압축을 적용한다.

## 11. Jetson 최적화 범위

### 11.1 이 프로젝트로 직접 증명할 수 있는 것

- Jetson에서 PyTorch/ONNX/TensorRT backend 포팅
- FP32/FP16/INT8 정확도·latency trade-off 분석
- 고정 shape, batch 1, window length에 맞춘 TensorRT engine 구성
- warm-up, CUDA synchronize, 반복 측정을 포함한 재현 가능한 benchmark
- P50/P95/P99 latency와 jitter 분석
- peak RAM/GPU memory, power, temperature 측정
- thermal throttling 및 장시간 안정성 분석
- ROS2 입력부터 안전 이벤트까지 end-to-end latency 분석
- 모델 hash·runtime·JetPack·TensorRT·전력 모드를 포함한 환경 기록
- Edge에서 판별하고 요약 이벤트만 중앙으로 전달하는 bandwidth 절감 구조

### 11.2 별도 보완해야 하는 것

- 실제 센서 calibration, drift, noise, 고장 모드
- MCU/serial/CAN/EtherCAT 등 물리 통신
- 실제 그리퍼 제어 loop의 hard real-time 보장
- 여러 Jetson 장비의 fleet 운영
- 대규모 GPU 서버와 Kubernetes cluster 운영
- 네트워크 단절·OTA 배포·현장 rollback의 실제 장비 검증
- Qualcomm QNN/SNPE/AIMET 실제 포팅 결과
- 실제 사용자 또는 현장 데이터에 대한 domain shift 검증

## 12. 반드시 측정할 지표

### 12.1 모델 품질

안전 판별에서는 전체 accuracy보다 위험 사건을 놓치지 않는 것이 중요하다.

- Macro F1
- 클래스별 Precision, Recall, F1
- slip/safety Recall
- slip/safety False Negative Rate
- False Positive Rate
- AUROC, PR-AUC
- confusion matrix
- threshold별 precision-recall trade-off
- probability calibration: ECE 또는 Brier score
- trial/subject 단위 bootstrap confidence interval
- tactile channel/window/feature ablation
- 독립성이 확인된 경우에만 tactile-only / force-only / fusion 탐색 결과

### 12.2 추론 및 시스템 성능

- preprocess P50/P95/P99
- inference P50/P95/P99
- postprocess P50/P95/P99
- source timestamp부터 safety event까지 end-to-end P50/P95/P99
- latency jitter
- 처리 window/second
- ROS2 message drop rate
- queue depth와 backpressure 발생 횟수
- cold-start 및 warm-start latency
- peak RAM/GPU memory
- 평균/최대 전력
- 평균/최대 온도
- throttling 발생 여부
- energy per inference
- throughput per watt

### 12.3 벤치마크 측정 규칙

- 동일 test split, 동일 window, 동일 stride, 동일 batch 1을 사용한다.
- Jetson 전력 모드와 clock 상태를 기록한다.
- backend별 독립 process에서 측정한다.
- 최소 warm-up 20회 후 200회 이상 측정한다.
- GPU 비동기 실행 전후를 동기화한다.
- 평균만 쓰지 않고 P50/P95/P99와 raw sample을 보존한다.
- 모델·데이터·코드 commit·환경 manifest를 결과에 연결한다.
- 정확도와 latency 측정을 같은 engine hash에 대해 수행한다.

### 12.4 최적화 비교표

최종 README와 보고서에는 다음 표를 사용한다.

| Backend | Precision | Macro F1 | Safety Recall | FNR | P50 infer | P95 infer | P95 E2E | Peak RAM | Power | Energy/infer | Model size |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PyTorch FP32 | FP32 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ONNX | FP32 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| TensorRT | FP32 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| TensorRT | FP16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| TensorRT | INT8 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

INT8이 Jetson/모델/연산자 조건에서 지원되지 않거나 정확도 허용 범위를 넘으면 실패를 숨기지 않고 미채택 결과로 기록한다.

### 12.5 제안 합격 기준

실제 데이터 조사 후 수정할 수 있는 초기 기준이다.

- Safety Recall: 기준 모델 이상이며 우선 목표 0.95
- FNR: 우선 목표 0.05 이하
- TensorRT FP16 품질 손실: PyTorch 대비 Macro F1 0.01 이내
- Jetson P95 inference latency: 입력 sampling/window 주기보다 충분히 낮을 것
- ROS2 end-to-end P95: 제품 요구가 없으므로 실측 후 합리적인 SLO를 확정
- 30분 soak test 중 crash, unbounded queue, 지속적 throttling 없음

목표치는 실측 없이 달성했다고 주장하지 않는다.

## 13. 비용 효율화 표현법

Jetson 한 대의 결과를 근거로 클라우드 비용을 실제로 절감했다고 단정하지 않는다. 다음 실측값과 명시된 가정을 분리한다.

### 실측

- Jetson 평균·최대 전력
- 초당 처리 window 수
- event-only payload 크기
- 원시 스트림 payload 크기
- energy per inference
- throughput per watt

### 가정 기반 시나리오

- 장비 수
- 하루 가동 시간
- 원시 센서 sampling rate와 업로드량
- 클라우드 추론 단가와 네트워크 단가
- Jetson 장비 가격과 감가 기간

### 권장 표현

> 원시 센서 데이터를 지속적으로 중앙 전송하는 대신 Jetson에서 실시간 판별하고 안전 이벤트와 요약 메트릭만 전송하는 구조를 구현했다. 실측 전력·처리량·전송량과 공개 클라우드 가격을 분리해 워크로드별 비용 손익분기점을 분석했다.

피해야 할 표현은 다음과 같다.

- 근거 없는 `비용 80% 절감`
- Jetson을 `GPU 서버 클러스터 운영`으로 표현
- 네트워크 비용이나 장비 감가를 제외한 비교
- 서로 다른 품질 수준의 모델을 비용만으로 비교

## 14. Qualcomm 요구사항 대응

Jetson에서는 Qualcomm QNN, SNPE, AIMET을 직접 실행할 수 없다. 프로젝트에서는 이를 사용했다고 주장하지 않는다. 대신 다음 이식 가능한 역량을 결과물에 드러낸다.

- framework 모델의 ONNX export
- 입력 shape, dtype, normalization 계약 고정
- unsupported operator 식별과 대체 가능성 분석
- static INT8 calibration dataset 선정
- per-tensor/per-channel quantization 개념과 정확도 회귀 분석
- FP32/FP16/INT8 backend별 출력 동등성 검증
- 모델 graph, memory, latency 병목 분석
- device-specific binary를 target 장비에서 생성·관리
- 배포 전 validation gate와 rollback 기준

문서에는 TensorRT 과정과 Qualcomm의 대응 개념을 다음처럼 매핑한다.

| 본 프로젝트 | Qualcomm 환경에서 대응되는 개념 |
|---|---|
| ONNX export/graph 검사 | QNN/SNPE 변환 전 모델 준비 |
| TensorRT unsupported op 확인 | QNN op package 또는 graph 수정 검토 |
| TensorRT INT8 calibration | AIMET/QNN quantization calibration |
| engine별 정확도 회귀 | DLC/QNN binary 출력 동등성 검증 |
| Jetson profiling | Snapdragon CPU/GPU/HTP backend profiling |
| engine/runtime manifest | SoC/SDK/backend별 artifact 관리 |

권장 이력서 표현은 다음과 같다.

> TensorRT 기반 Edge AI 포팅과 FP16/INT8 최적화를 수행하고, ONNX graph·연산자 호환성·calibration·정확도 회귀 검증 체계를 구축했습니다. 동일한 포팅 방법론을 QNN/SNPE/AIMET 환경으로 확장할 수 있도록 backend 독립 데이터·모델 계약을 설계했습니다.

## 15. 검증 전략

### 15.1 데이터 검증

- 파일 schema와 채널 수 검증
- timestamp 단조 증가 검증
- trial 간 중복과 label 누수 검사
- split manifest 재현성 검사
- window가 trial 경계를 넘지 않는지 검사

### 15.2 모델 검증

- 작은 synthetic fixture로 shape·normalization 테스트
- 기준 모델 재현성 테스트
- PyTorch/ONNX/TensorRT 동일 입력 출력 비교
- threshold와 safety event 변환 테스트
- class imbalance 및 빈 클래스 처리 테스트

### 15.3 ROS2 검증

- replay rate와 timestamp 보존 테스트
- out-of-order/missing sample 처리
- bounded buffer와 backpressure 테스트
- inference node restart 후 복구
- ground truth가 inference input으로 섞이지 않는 계약 테스트
- F/T reference 토픽이 MVP inference node 입력에 연결되지 않는 계약 테스트

### 15.4 Jetson 검증

- cold/warm benchmark 분리
- power mode 및 environment capture
- 30분 soak test
- high temperature에서 latency 변화 측정
- engine load 실패 시 명확한 실패와 rollback 확인

## 16. 결과물

- 공개 Git 저장소와 재현 가능한 README
- 데이터 출처·라이선스·hash manifest
- 데이터 schema와 label 정의 문서
- 모델 카드
- ROS2 topic/interface 문서
- 시스템 아키텍처 다이어그램
- 학습·평가 스크립트
- PyTorch/ONNX/TensorRT 비교 보고서
- raw benchmark JSON/CSV와 요약 표
- Jetson 운영 runbook
- 3~5분 데모 영상
- 이력서용 한 문단과 면접용 문제 해결 사례

## 17. 구현 단계의 기본 순서

이 문서 승인 후 별도 구현 계획에서 파일과 테스트 단위로 세분화한다. 큰 순서는 다음과 같다.

1. 데이터 라이선스·schema 조사와 dataset manifest
2. 누수 없는 split·window·기준 모델
3. ROS2 dataset replay와 inference contract
4. 1D CNN/TCN 및 fusion 비교
5. ONNX/TensorRT FP16/INT8 포팅
6. Jetson 성능·전력 benchmark
7. 결과 저장·경량 dashboard
8. 보고서·데모·포트폴리오 문구 정리

## 18. 남은 결정과 빌더 재량

### 사용자 승인이 필요한 핵심 결정

- 본 기획서의 MVP 범위와 성공 기준 승인

### 구현자가 조사 후 결정할 항목

- 실제 파일 schema에 맞는 ROS2 tactile message 세부 필드
- 데이터의 sampling rate가 제공되지 않을 때 replay 기준
- IntelliMan의 정확한 label schema에 따른 최종 class 정의
- Logistic Regression/Random Forest/XGBoost 중 기준 모델 하나
- 1D CNN과 TCN의 세부 채널 수와 receptive field
- SQLite 단독 또는 기존 PostgreSQL 연동 여부
- INT8 지원성과 calibration sample 수
- 경량 dashboard 구현 방식

이 항목들은 데이터 탐색 결과와 저장공간 제약 안에서 결정하되, 결정 근거를 문서화한다.

## 19. 제한사항 공개 문구

> 본 프로젝트는 공개된 촉각·힘 센서 데이터셋을 이용한 재현 프로젝트이며 실제 센서 하드웨어 수집·calibration은 포함하지 않습니다. ROS2 publisher로 원본 시계열과 timestamp를 재생해 실제 센서 노드와 동일한 downstream 계약을 검증했으며, Jetson 배포·추론 최적화·시스템 성능 측정에 초점을 맞췄습니다.

