"""Unity-facing committed event representation."""


_SENSITIVE_TRANSPORT_FIELDS = {
    "api_token", "tcad_api_token", "x_fab_token", "endpoint_url", "tcad_prod_url",
}


def _without_transport_secrets(value):
    if isinstance(value, dict):
        return {
            key: _without_transport_secrets(item)
            for key, item in value.items()
            if key.lower() not in _SENSITIVE_TRANSPORT_FIELDS
        }
    if isinstance(value, list):
        return [_without_transport_secrets(item) for item in value]
    return value


def format_unity_event(row: dict, unity_mode: str) -> dict:
    payload = row.get("payload") or {}
    formatted = dict(row)
    if row["event_type"].startswith("tcad.verification."):
        payload = _without_transport_secrets(payload)
        formatted["payload"] = payload
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
