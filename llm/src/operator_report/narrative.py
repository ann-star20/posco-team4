from __future__ import annotations

import json
import re
from typing import Any
from urllib import request


SYSTEM_PROMPT = """당신은 제조 현장 운영 리포트 설명 도우미입니다.
제공된 확정 JSON만 사용하십시오. 숫자, 판정, 권고 조치, 대상, 근거 ID를 새로 만들거나 바꾸지 마십시오.
LOT 격리, 설비 정지, 공정 보정, 승인 같은 조치를 실행했다고 표현하지 마십시오.
출력은 JSON 객체 하나이며 overview, attention, evidence_ids 키만 포함합니다.
overview는 최대 2문장의 짧은 한국어 문단, attention은 최대 2개의 한국어 문자열 배열, evidence_ids는 사용한 근거 ID 배열입니다.
모든 조치는 운영자 판단이 필요한 권고임을 overview에 명시하십시오."""


def build_prompt(report: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    payload = {
        "report": report,
        "evidence": evidence,
    }
    return "다음 확정 데이터를 운영자용으로 설명하십시오.\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _numbers(value: Any) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", json.dumps(value, ensure_ascii=False)))


def validate_narrative(
    narrative: dict[str, Any], report: dict[str, Any], evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    if set(narrative) != {"overview", "attention", "evidence_ids"}:
        raise ValueError("LLM output must contain only overview, attention, evidence_ids")
    if not isinstance(narrative["overview"], str) or not narrative["overview"].strip():
        raise ValueError("overview must be a non-empty string")
    if not isinstance(narrative["attention"], list) or not all(
        isinstance(item, str) and item.strip() for item in narrative["attention"]
    ):
        raise ValueError("attention must be a string array")
    if not isinstance(narrative["evidence_ids"], list) or not all(
        isinstance(item, str) for item in narrative["evidence_ids"]
    ):
        raise ValueError("evidence_ids must be a string array")

    known_evidence = {str(item.get("evidence_id")) for item in evidence}
    unknown_evidence = sorted(set(narrative["evidence_ids"]) - known_evidence)
    if unknown_evidence:
        raise ValueError(f"LLM output references unknown evidence: {', '.join(unknown_evidence)}")

    allowed_numbers = _numbers({"report": report, "evidence": evidence})
    new_numbers = sorted(_numbers(narrative) - allowed_numbers)
    if new_numbers:
        raise ValueError(f"LLM output introduces unsupported numbers: {', '.join(new_numbers)}")

    return {
        "valid": True,
        "unknown_evidence": [],
        "unsupported_numbers": [],
    }


def generate_narrative(
    report: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    base_url: str,
    model: str,
    api_key: str,
    timeout_seconds: float = 180.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 192,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(report, evidence)},
        ],
    }
    endpoint = base_url.rstrip("/") + "/chat/completions"
    http_request = request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        response_body = json.loads(response.read().decode("utf-8"))
    content = response_body["choices"][0]["message"]["content"]
    narrative = json.loads(content)
    validator = validate_narrative(narrative, report, evidence)
    return narrative, validator
