"""Local configuration. Never print credentials or connection URLs."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Literal


Mode = Literal["mock", "prod"]


def _read_dotenv(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("invalid .env line")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    test_database_url: str = field(repr=False, default="")
    tcad_mode: Mode = "mock"
    unity_mode: Mode = "mock"
    tcad_mock_url: str = "http://127.0.0.1:8100"
    tcad_prod_url: str = ""
    tcad_mock_scenario: str = "pass"
    tcad_http_timeout_seconds: float = 10
    tcad_poll_interval_seconds: float = 5
    ros_domain_id: str | None = None
    rmw_implementation: str | None = None
    ros_event_topic: str = "/fab/events"
    ros_event_ack_topic: str = "/fab/event_acks"
    ros_command_topic: str = "/fab/commands"
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    approval_token: str = field(repr=False, default="")
    approval_operator: str = ""
    ros_command_key: str = field(repr=False, default="")
    jetson_host: str = ""
    jetson_user: str = ""
    jetson_password: str = field(repr=False, default="")
    jetson_project_path: str = "/home/jetson/project/smart_factory"

    @property
    def tcad_url(self) -> str:
        return self.tcad_prod_url if self.tcad_mode == "prod" else self.tcad_mock_url

    @property
    def run_mock_unity(self) -> bool:
        return self.unity_mode == "mock"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        values = _read_dotenv(path)
        values.update(os.environ)
        def get(name: str, default: str = "") -> str:
            return values.get(name, default)
        database_url = get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        tcad_mode = get("TCAD_MODE", "mock")
        unity_mode = get("UNITY_MODE", "mock")
        if tcad_mode not in {"mock", "prod"} or unity_mode not in {"mock", "prod"}:
            raise ValueError("TCAD_MODE and UNITY_MODE must be mock or prod")
        if tcad_mode == "prod" and not get("TCAD_PROD_URL"):
            raise ValueError("TCAD_PROD_URL is required in prod mode")
        return cls(
            database_url=database_url,
            test_database_url=get("TEST_DATABASE_URL"),
            tcad_mode=tcad_mode,
            unity_mode=unity_mode,
            tcad_mock_url=get("TCAD_MOCK_URL", "http://127.0.0.1:8100"),
            tcad_prod_url=get("TCAD_PROD_URL"),
            tcad_mock_scenario=get("TCAD_MOCK_SCENARIO", "pass"),
            tcad_http_timeout_seconds=float(get("TCAD_HTTP_TIMEOUT_SECONDS", "10")),
            tcad_poll_interval_seconds=float(get("TCAD_POLL_INTERVAL_SECONDS", "5")),
            ros_domain_id=get("ROS_DOMAIN_ID") or None,
            rmw_implementation=get("RMW_IMPLEMENTATION") or None,
            ros_event_topic=get("ROS_EVENT_TOPIC", "/fab/events"),
            ros_event_ack_topic=get("ROS_EVENT_ACK_TOPIC", "/fab/event_acks"),
            ros_command_topic=get("ROS_COMMAND_TOPIC", "/fab/commands"),
            gateway_host=get("GATEWAY_HOST", "0.0.0.0"),
            gateway_port=int(get("GATEWAY_PORT", "8000")),
            approval_token=get("APPROVAL_TOKEN"),
            approval_operator=get("APPROVAL_OPERATOR"),
            ros_command_key=get("ROS_COMMAND_KEY"),
            jetson_host=get("JETSON_HOST"),
            jetson_user=get("JETSON_USER"),
            jetson_password=get("JETSON_PASSWORD"),
            jetson_project_path=get("JETSON_PROJECT_PATH", "/home/jetson/project/smart_factory"),
        )
