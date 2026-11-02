from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .narrative import generate_narrative
from .render import build_report, write_bundle
from .rules import evaluate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an evidence-grounded operator weekly report")
    parser.add_argument("--snapshot", required=True, type=Path, help="Immutable snapshot JSON")
    parser.add_argument("--output", required=True, type=Path, help="Output bundle directory")
    parser.add_argument("--llm", action="store_true", help="Generate a validated narrative with an OpenAI-compatible server")
    parser.add_argument("--llm-base-url", default=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1"))
    parser.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "qwen3-1.7b-q4"))
    parser.add_argument("--llm-api-key", default=os.getenv("LLM_API_KEY", "local"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    required = {"snapshot_id", "period", "signals"}
    missing = sorted(required - snapshot.keys())
    if missing:
        raise SystemExit(f"snapshot missing required fields: {', '.join(missing)}")
    recommendations = evaluate(snapshot["signals"])
    report = build_report(snapshot, recommendations)
    evidence = snapshot.get("evidence", [])
    known = {str(item.get("evidence_id")) for item in evidence}
    referenced = {value for item in recommendations for value in item["evidence"]}
    unknown = sorted(referenced - known)
    if unknown:
        raise SystemExit(f"recommendations reference unknown evidence: {', '.join(unknown)}")
    generation: dict[str, object] = {
        "mode": "deterministic-template",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": snapshot["snapshot_id"],
        "validator": {"valid": True, "unknown_evidence": []},
    }
    if args.llm:
        narrative, validator = generate_narrative(
            report,
            evidence,
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
        )
        report["operator_narrative"] = narrative
        generation.update(
            {
                "mode": "llm-assisted",
                "provider": "openai-compatible",
                "model": args.llm_model,
                "base_url": args.llm_base_url,
                "validator": validator,
            }
        )
    write_bundle(report, evidence, args.output, generation)
    print(args.output)


if __name__ == "__main__":
    main()

