"""Unity-facing committed event representation."""


def format_unity_event(row: dict, unity_mode: str) -> dict:
    payload = row.get("payload") or {}
    formatted = dict(row)
    if row["event_type"].startswith("correction."):
        current = payload.get("x_current") or {}
        delta = payload.get("delta_x") or {}
        candidate = payload.get("x_candidate") or {}
        formatted["correction"] = {
            key: {"current": current.get(key), "delta": delta.get(key),
                  "recommended": candidate.get(key)}
            for key in candidate
        }
    formatted["approval_allowed"] = (
        row["event_type"] == "correction.verified"
        and (payload.get("result_origin") == "prod" or unity_mode == "mock")
    )
    return formatted
