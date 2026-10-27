"""Export diagnosis_results rows to JSONL for LLM report-generation bootstrapping."""
import argparse
import json
from pathlib import Path

import psycopg

from event_gateway.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="diagnosis_results -> JSONL dataset export")
    parser.add_argument("--out", default=str(ROOT / "data" / "diagnosis_dataset" / "raw.jsonl"))
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    args = parser.parse_args()

    settings = Settings.load(ROOT / ".env")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    query = (
        "SELECT job_id, source_event_id, response_body, top_category, top_probability, "
        "compensation_route, high_confidence, routing_status, created_at "
        "FROM diagnosis_results ORDER BY created_at"
    )
    if args.limit:
        query += " LIMIT %s"

    with psycopg.connect(settings.database_url, autocommit=True) as db:
        cursor = db.execute(query, (args.limit,) if args.limit else None)
        rows = cursor.fetchall()

    with out_path.open("w", encoding="utf-8") as handle:
        for job_id, source_event_id, response_body, top_category, top_probability, \
                compensation_route, high_confidence, routing_status, created_at in rows:
            record = {
                "job_id": str(job_id),
                "source_event_id": str(source_event_id),
                "response_body": response_body,
                "top_category": top_category,
                "top_probability": top_probability,
                "compensation_route": compensation_route,
                "high_confidence": high_confidence,
                "routing_status": routing_status,
                "created_at": created_at.isoformat(),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"exported {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    raise SystemExit(main())
