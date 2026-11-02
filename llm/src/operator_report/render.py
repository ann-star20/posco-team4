from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


ACTION_LABELS = {
    "reinspect_item": "대상 재검사",
    "review_quality_hold": "LOT 품질 보류 검토",
    "check_camera": "카메라·조명·이미지 입력 점검",
    "request_equipment_check": "설비 점검 요청",
    "check_input": "입력값·단위 확인",
    "review_training_coverage": "학습 커버리지 검토 요청",
    "escalate_process_engineer": "공정 엔지니어 확인 요청",
    "monitor_only": "추가 조치 없이 모니터링",
}


def build_report(snapshot: dict[str, Any], recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_id": snapshot["snapshot_id"],
        "period": snapshot["period"],
        "timezone": snapshot.get("timezone", "Asia/Seoul"),
        "summary": snapshot.get("summary", {}),
        "sections": snapshot.get("sections", {}),
        "recommendations": recommendations,
        "data_quality": snapshot.get("data_quality", {}),
        "provenance": snapshot.get("provenance", {}),
        "advisory_only": True,
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 현장 운영자 주간 리포트",
        "",
        f"- 기간: {report['period']['start']} ~ {report['period']['end']} ({report['timezone']})",
        f"- Snapshot: `{report['report_id']}`",
        "- 본 리포트의 조치는 권고이며 최종 판단은 운영자가 수행합니다.",
        "",
        "## 이번 주 요약",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    narrative = report.get("operator_narrative")
    if narrative:
        lines.extend(["", "## 운영 설명", "", narrative["overview"]])
        for item in narrative["attention"]:
            lines.append(f"- {item}")
    lines.extend(["", "## 권고 조치", ""])
    for item in report["recommendations"]:
        evidence = ", ".join(item["evidence"]) or "정기 모니터링"
        lines.append(
            f"- **{item['severity'].upper()}** {ACTION_LABELS[item['action_code']]} "
            f"— {item['target_type']} `{item['target_id']}` (근거: {evidence})"
        )
    lines.extend(["", "## 데이터 품질", ""])
    for key, value in report["data_quality"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def write_bundle(report: dict[str, Any], evidence: list[dict[str, Any]], output_dir: Path, generation: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    markdown = _markdown(report)
    html_body = "<html><meta charset='utf-8'><body><pre>" + html.escape(markdown) + "</pre></body></html>\n"
    (output_dir / "report.json").write_text(report_json + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(markdown, encoding="utf-8")
    (output_dir / "report.html").write_text(html_body, encoding="utf-8")
    (output_dir / "evidence.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evidence), encoding="utf-8"
    )
    (output_dir / "generation.json").write_text(json.dumps(generation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

