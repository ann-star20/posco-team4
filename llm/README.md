# 현장 운영자 주간 리포트

AOI, surrogate, TCAD의 확정된 근거를 주간 운영 리포트로 만드는 독립 모듈입니다. 규칙 엔진은 권고 코드만 만들며 LOT 상태 변경, 설비 정지, 공정 보정 또는 승인을 실행하지 않습니다.

## 빠른 실행

Windows PowerShell:

```powershell
cd llm
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\operator-report.exe --snapshot examples\sample_snapshot.json --output reports\sample
```

Linux/WSL:

```bash
cd llm
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/operator-report --snapshot examples/sample_snapshot.json --output reports/sample
```

생성물은 `report.json`, `report.md`, `report.html`, `evidence.jsonl`, `generation.json`입니다. 실제 DB 연결 전에는 `examples/sample_snapshot.json`으로 동작을 확인하십시오.

Qwen을 OpenAI 호환 `llama-server`로 실행한 뒤 설명문을 추가하려면 `--llm`을 사용합니다.

```powershell
$env:LLM_BASE_URL = "http://127.0.0.1:8080/v1"
$env:LLM_MODEL = "qwen3-1.7b-q4"
.\.venv\Scripts\operator-report.exe --snapshot examples\sample_snapshot.json --output reports\sample-llm --llm
```

LLM 출력은 알려진 근거 ID만 참조하고 원본에 없는 숫자를 추가하지 못하도록 검증됩니다. 검증 실패나 서버 오류 시 리포트 생성은 실패하며, 검증되지 않은 설명문으로 자동 대체하지 않습니다.

## 안전 경계

- 숫자와 판정은 SQL snapshot과 결정적 규칙에서 가져옵니다.
- LLM은 설명 문장 생성에만 사용하며 조치 코드를 만들거나 서비스를 호출하지 않습니다.
- 모든 권고는 `operator_decision_required=true`입니다.
- `.env`, 운영 데이터, 리포트, 모델 가중치와 GGUF는 Git에서 제외합니다.
- `config/glossary.json`의 `draft-review-required` 용어는 공정 엔지니어 검수 후 사용합니다.

## 다음 연결 단계

1. Aiven 읽기 전용 schema 조사와 immutable snapshot 추출기를 추가합니다.
2. 실제 이벤트 계약에 맞춰 metric registry와 SQL을 고정합니다.
3. SMTP 설정은 `.env`에서 주입하며, 발송 전 shadow 리포트를 최소 4주 검수합니다.

