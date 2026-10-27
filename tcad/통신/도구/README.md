# fabrx: Jetson 모델 서비스 번들

Jetson 에서 Worker 가 호출하는 **모델 서비스**(서로게이트 + 진단 에이전트)에 필요한 파일을 한곳에 모았다. 이 폴더만 Jetson 에 복사하면 된다.

## 들어 있는 것
| 위치 | 내용 |
|---|---|
| `run_service.py` | 서비스 시작 (영문 이름 진입점) |
| `check_env.py` | 환경과 파일 점검 (`--smoke` 로 실제 예측·진단 시험까지) |
| `worker_stub.py` | Worker 대역: 서비스를 계약대로 호출해 보는 시험 (Worker 개발의 참고용 `call()` 포함) |
| `install_service.sh`, `fabrx-model.service.template` | 부팅 때 자동 시작 (systemd) |
| `requirements.txt` | 필요한 패키지 |
| `manifest.json` | 모든 파일의 크기와 SHA-256 (복사가 완전한지 `check_env.py` 가 확인) |
| `통신/` | 서비스 본체 (`모델서비스.py`, `변환기.py`), 자체 시험 `시험.py`, 계약 보완 문서, 요청·응답 예 |
| `최종ML/` | 서로게이트 실행 코드와 학습된 모델 (`모델/`, 고정밀 모드용 TabPFN 가중치 44 MB 포함) |
| `진단에이전트/` | 진단 에이전트 |
| `docs/` | 모델과 Jetson 사용 설명 문서 |

## 따라 하기

### 1. 옮기고 풀기 (한글 이름이 깨지지 않게 tar 를 쓴다)
```bash
scp fabrx_jetson.tar.gz <사용자>@<Jetson 주소>:~/
ssh <사용자>@<Jetson 주소>
sudo mkdir -p /opt && sudo tar xzf ~/fabrx_jetson.tar.gz -C /opt && sudo chown -R $USER /opt/fabrx
cd /opt/fabrx
export LANG=C.UTF-8 LC_ALL=C.UTF-8
```
(USB 로 옮겨도 같다. 압축 도구는 tar 를 쓰고, Windows 의 zip 으로 다시 묶지 마세요.)

### 2. 환경과 파일 점검
```bash
python3 check_env.py
```
실패 항목마다 고치는 방법이 나온다. 필요하면 `pip3 install numpy`. 모두 통과하면 다음으로.

### 3. 자체 시험 (서비스를 켜지 않고 메모리에서 실행)
```bash
python3 check_env.py --smoke          # 불러오기, 기준값 예측, 진단 한 번 (수 초)
cd 통신 && python3 시험.py && cd ..     # 39개 항목, 마지막 줄 "전체 판정: 모두 통과"
```
이때 **diagnose 걸린 시간**을 적어 두세요 (Worker 제한 시간을 정하는 데 필요).

### 4. 서비스 켜기
```bash
python3 run_service.py                                  # 화면에 로그가 나온다 (127.0.0.1:8300)
python3 run_service.py --token 영문토큰 --log-file ./service.log    # 토큰과 로그 파일 (선택)
```
다른 터미널에서:
```bash
curl http://127.0.0.1:8300/health
python3 worker_stub.py                       # 토큰을 쓰면 --token 영문토큰
```
`worker_stub.py` 가 "모두 통과"면 계약대로 통신이 된다.

### 5. 부팅 때 자동 시작 (선택)
```bash
sudo ./install_service.sh install      # 점검 -> 등록 -> 시작
sudo ./install_service.sh status
sudo ./install_service.sh uninstall
```
토큰은 `/etc/fabrx/service.env` 에 `FAB_SERVICE_TOKEN=영문토큰` 으로 적는다. 로그는 `/var/log/fabrx/model-service.log`. **이 스크립트는 systemd 가 없는 Windows 에서 시험하지 못했으니 처음 쓸 때 결과를 확인하세요.**

## Jetson 에서 확인된 것 (사용자가 Jetson 에서 실행해 알려 준 결과)
- 장치: Python 3.10.12, NumPy 2.2.6 (이 번들은 NumPy 2.x 에서 동작한다)
- `check_env.py`: 파일 32개와 모델 파일 SHA-256 일치, 포트 사용 가능, "서비스를 켤 수 있다"
- `통신/시험.py`: **39개 항목 모두 통과** (진단 한 건 3.5 초)
- 고정밀 모드: 이 장치에는 `tabpfn` 이 없고, 설치된 `torch` 가 NumPy 1.x 용으로 만들어져 NumPy 2.2.6 과 경고를 낸다. 기본 모드에는 영향이 없고, 고정밀 요청은 사유와 함께 기본 모드로 되돌아간다
- **서비스 시작과 Worker 대역 호출**: `run_service.py` 로 켜고 `worker_stub.py` 를 돌려 10개 항목 모두 통과. 서비스는 같은 장치 안에서 surrogate 6 ms, 진단 3.8 초로 응답
- **속도(`jetson_벤치.py`)**: aarch64, CPU 6코어. 1점 예측 지연 0.86 ms, 1만 점 0.49 초, 10만 점 4.32 초 (이 PC 3.9~7.4 초와 비슷)
- `install_service.sh`: 처음 실행했을 때 서비스를 터미널에서 직접 켜 둔 상태라 8300 포트가 사용 중이어서 사전 점검에서 멈췄다 (스크립트가 의도한 안전장치). 직접 켠 서비스를 Ctrl+C 로 끈 뒤 다시 실행하면 된다. 이 경우를 더 알기 쉽게 안내하도록 스크립트를 고쳤다
- 아직 확인하지 못한 것: 실제 Worker 연동, `install_service.sh` 의 등록과 자동 시작 (위 이유로 아직 끝까지 실행되지 않았다)
- 고정밀 모드: 격리 venv(`--system-site-packages` + `tabpfn` + `numpy<2`)로 설치 후 end-to-end 확인 완료 — `refine.performed=true`, `model_mode="고정밀(GP+TabPFN)"` (아래 "고정밀 모드" 절 참고)

## 고정밀 모드 (선택)
`torch`(JetPack 용 NVIDIA 휠)와 `tabpfn==9.2.0` 이 설치되어 있고, torch 가 설치된 NumPy 버전과 맞으면 (NumPy 1.x 용 torch 는 NumPy 2.x 와 맞지 않으니 필요하면 `pip3 install 'numpy<2'`, 이 번들 코드는 NumPy 2.x 전용 함수를 쓰지 않지만 NumPy 1.x 에서의 실행 시험은 하지 못했다) `diagnose` 에 `"refine": true` 를 보냈을 때 GP + TabPFN 으로 한 번 더 확인한다. 설치되어 있지 않아도 기본 모드로 정상 동작하고 응답의 `refine.performed` 가 false 로 표시된다. 가중치 파일이 없으면 인터넷을 찾지 않고 바로 기본 모드로 되돌아간다.

Gateway 는 `diagnose` 요청마다 `input_payload.refine` 을 `true` 로 강제한다 (`gate_workspace/services/event_gateway/src/event_gateway/app.py`) — 즉 **Jetson 에 TabPFN 이 없으면 모든 진단이 조용히 기본 모드로만 돌게 된다.** "Jetson 에서 확인된 것"에 적힌 대로 시스템 torch 가 NumPy 1.x 용이라 그냥 `pip3 install tabpfn 'numpy<2'` 를 시스템 환경에 하면 ABI 가 깨져 `RuntimeError: Numpy is not available` 로 refine 요청이 실패한다. 아래처럼 **격리된 venv** 를 쓰면 기존 Jetson 빌드 torch/CUDA 는 그대로 재사용하면서 TabPFN 만 추가할 수 있다.

```bash
cd /opt/fabrx
python3 -m venv --system-site-packages .venv-highprec
source .venv-highprec/bin/activate
pip install tabpfn 'numpy<2'     # venv 안에서만 numpy<2 로 고정, 시스템 torch/CUDA 는 그대로 상속
python3 check_env.py --smoke     # 고정밀 경로까지 확인
deactivate
```
`run_service.py` 를 이 venv 의 `python3` (예: `/opt/fabrx/.venv-highprec/bin/python3`) 로 실행하도록 `fabrx-model.service.template` 의 `ExecStart` 경로만 바꿔주면 systemd 등록도 그대로 쓸 수 있다. 정상 동작 시 응답에 `refine.performed=true`, `refine.model_mode="고정밀(GP+TabPFN)"` 이 찍힌다.

## 값을 바꿔야 할 때
`통신/변환기.py` 맨 위 상수만 고친다: 기준값, 단위, Id 조건(Vgs, Vds, 온도), 이상 판정 스펙. 고친 뒤 `python3 check_env.py` 는 "번들과 내용이 다른 코드 파일"을 참고로만 알리고 통과시킨다 (모델 파일이 달라졌을 때만 실패). 새 모델이 나오면 `최종ML/모델/` 을 통째로 교체한다.

## 문제 해결
| 증상 | 확인 |
|---|---|
| `ModuleNotFoundError: 변환기` | `export LANG=C.UTF-8 LC_ALL=C.UTF-8` 후 다시 실행. `ls 통신/` 에 한글 파일 이름이 보이는지 |
| 포트 사용 중 | `ss -ltnp \| grep 8300` 으로 기존 서비스 확인, 다른 포트는 `--port` |
| 401 UNAUTHORIZED | 서비스를 `--token` 으로 켰다. 요청 헤더 `X-Fab-Token` 이 같아야 한다 (ASCII 토큰만) |
| `OUT_OF_DOMAIN` | 단위(도즈 cm⁻², 에피 cm⁻³, 산화막 μm)와 값이 기준값(7.7e12, 1.7e16, 0.06) 근처인지 |
| diagnose 가 느리다 | 사후분포가 좁은 경우 길어진다 (이 PC 3~14 초). Worker 제한 시간을 60 초 이상으로 |
| `POOR_FIT` 경고 | 측정값이 학습 영역의 어떤 상태와도 맞지 않는다. 사람이 판단해야 한다 |

## 알려진 한계
- 이 번들은 Windows PC 에서 만들고 시험했다. **Jetson 에서의 실행, Python/NumPy 버전 호환, systemd 설치는 아직 확인하지 못했다.**
- 도즈, 에피 단위와 이상 판정 스펙은 확인이 필요한 값이다 (`통신/계약_보완.md`).
- 서버에는 인증이 기본으로 없다. 127.0.0.1 에만 바인딩되어 같은 장치 안에서만 접속된다.
