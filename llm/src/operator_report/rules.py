from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class Recommendation:
    action_code: str
    target_type: str
    target_id: str
    severity: str
    rule_id: str
    rule_version: str
    evidence: tuple[str, ...]
    operator_decision_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        return value


def _recommendations_for(signal: dict[str, Any]) -> list[Recommendation]:
    kind = str(signal.get("kind", ""))
    status = str(signal.get("status", "")).lower()
    target_type = str(signal.get("target_type", kind or "system"))
    target_id = str(signal.get("target_id", "unknown"))
    evidence_id = str(signal.get("evidence_id", target_id))
    evidence = (evidence_id,)

    if kind == "aoi" and status == "fail":
        return [
            Recommendation("reinspect_item", target_type, target_id, "warning", "AOI_FAIL_REINSPECT", "1.0", evidence),
            Recommendation("review_quality_hold", target_type, target_id, "warning", "AOI_FAIL_HOLD_REVIEW", "1.0", evidence),
        ]
    if kind == "aoi" and status in {"review", "image_error", "read_failed"}:
        return [Recommendation("check_camera", target_type, target_id, "warning", "AOI_INPUT_CHECK", "1.0", evidence)]
    if kind == "equipment" and status in {"down", "blocked"}:
        severity = "critical" if status == "down" else "warning"
        return [Recommendation("request_equipment_check", target_type, target_id, severity, "EQUIPMENT_UNAVAILABLE", "1.0", evidence)]
    if kind == "diagnosis" and status in {"poor_fit", "manual"}:
        return [Recommendation("escalate_process_engineer", target_type, target_id, "warning", "DIAGNOSIS_MANUAL", "1.0", evidence)]
    if kind == "tcad" and status in {"failed", "cancelled", "approval_overdue"}:
        return [Recommendation("escalate_process_engineer", target_type, target_id, "warning", "TCAD_ESCALATION", "1.0", evidence)]
    if kind == "surrogate" and status == "out_of_domain":
        ood_class = str(signal.get("ood_class", "unknown")).lower()
        if ood_class in {"input_error", "unit_error", "format_error", "unknown"}:
            return [Recommendation("check_input", target_type, target_id, "warning", "OOD_INPUT_CHECK", "1.0", evidence)]
        if ood_class == "coverage_gap_candidate" and int(signal.get("repeat_count", 1)) >= int(signal.get("repeat_threshold", 3)):
            return [Recommendation("review_training_coverage", target_type, target_id, "warning", "OOD_REPEAT_COVERAGE", "1.0", evidence)]
        if ood_class in {"coverage_gap_candidate", "extreme"}:
            return [Recommendation("escalate_process_engineer", target_type, target_id, "info", "OOD_ENGINEER_REVIEW", "1.0", evidence)]
    return []


def evaluate(signals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], Recommendation] = {}
    for signal in signals:
        for item in _recommendations_for(signal):
            key = (item.action_code, item.target_type, item.target_id)
            current = merged.get(key)
            if current is None:
                merged[key] = item
                continue
            severity = item.severity if SEVERITY_RANK[item.severity] > SEVERITY_RANK[current.severity] else current.severity
            evidence = tuple(dict.fromkeys((*current.evidence, *item.evidence)))
            merged[key] = Recommendation(
                item.action_code,
                item.target_type,
                item.target_id,
                severity,
                item.rule_id,
                item.rule_version,
                evidence,
            )
    if not merged:
        merged[("monitor_only", "report", "weekly")] = Recommendation(
            "monitor_only", "report", "weekly", "info", "NO_ACTION_SIGNAL", "1.0", tuple()
        )
    return [item.to_dict() for item in sorted(merged.values(), key=lambda row: (-SEVERITY_RANK[row.severity], row.target_type, row.target_id, row.action_code))]

