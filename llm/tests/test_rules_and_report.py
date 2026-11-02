from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from operator_report.narrative import validate_narrative
from operator_report.render import build_report, write_bundle
from operator_report.rules import evaluate


class RuleTests(unittest.TestCase):
    def test_fail_produces_advisory_actions(self) -> None:
        rows = evaluate([{"kind": "aoi", "status": "fail", "target_type": "lot", "target_id": "L1", "evidence_id": "E1"}])
        self.assertEqual({row["action_code"] for row in rows}, {"reinspect_item", "review_quality_hold"})
        self.assertTrue(all(row["operator_decision_required"] for row in rows))

    def test_repeated_valid_ood_requests_coverage_review(self) -> None:
        rows = evaluate([{"kind": "surrogate", "status": "out_of_domain", "ood_class": "coverage_gap_candidate", "repeat_count": 3, "repeat_threshold": 3, "target_id": "x", "evidence_id": "E2"}])
        self.assertEqual(rows[0]["action_code"], "review_training_coverage")

    def test_no_signal_is_monitor_only(self) -> None:
        self.assertEqual(evaluate([])[0]["action_code"], "monitor_only")


class RenderTests(unittest.TestCase):
    def test_bundle_contains_all_required_files(self) -> None:
        snapshot = {"snapshot_id": "s1", "period": {"start": "a", "end": "b"}, "summary": {}, "data_quality": {}}
        report = build_report(snapshot, evaluate([]))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_bundle(report, [], output, {"mode": "test"})
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"report.json", "report.md", "report.html", "evidence.jsonl", "generation.json"},
            )
            self.assertTrue(json.loads((output / "report.json").read_text(encoding="utf-8"))["advisory_only"])


class NarrativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {"summary": {"검사 건": 120}, "recommendations": [], "advisory_only": True}
        self.evidence = [{"evidence_id": "E1", "value": 120}]

    def test_valid_narrative_uses_known_evidence_and_numbers(self) -> None:
        narrative = {
            "overview": "검사 건은 120건이며 모든 조치는 운영자 판단이 필요한 권고입니다.",
            "attention": ["근거 E1을 확인하십시오."],
            "evidence_ids": ["E1"],
        }
        self.assertTrue(validate_narrative(narrative, self.report, self.evidence)["valid"])

    def test_unknown_evidence_is_rejected(self) -> None:
        narrative = {
            "overview": "모든 조치는 운영자 판단이 필요한 권고입니다.",
            "attention": [],
            "evidence_ids": ["E999"],
        }
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_narrative(narrative, self.report, self.evidence)

    def test_unsupported_number_is_rejected(self) -> None:
        narrative = {
            "overview": "121건이며 운영자 판단이 필요한 권고입니다.",
            "attention": [],
            "evidence_ids": [],
        }
        with self.assertRaisesRegex(ValueError, "unsupported numbers"):
            validate_narrative(narrative, self.report, self.evidence)


if __name__ == "__main__":
    unittest.main()

