import pytest

from event_gateway.config import Settings


def test_default_modes_are_mock(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("TCAD_MOCK_URL", "http://127.0.0.1:8100")
    monkeypatch.delenv("TCAD_MODE", raising=False)
    monkeypatch.delenv("UNITY_MODE", raising=False)
    settings = Settings.load()
    assert settings.tcad_mode == "mock"
    assert settings.unity_mode == "mock"
    assert settings.tcad_url == "http://127.0.0.1:8100"


@pytest.mark.parametrize("tcad_mode,unity_mode", [
    ("mock", "mock"), ("prod", "mock"), ("mock", "prod"), ("prod", "prod")
])
def test_modes_are_independent(monkeypatch, tcad_mode, unity_mode):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("TCAD_MOCK_URL", "http://127.0.0.1:8100")
    monkeypatch.setenv("TCAD_PROD_URL", "http://tcad.example:8100")
    monkeypatch.setenv("TCAD_API_TOKEN", "test-token")
    monkeypatch.setenv("TCAD_MODE", tcad_mode)
    monkeypatch.setenv("UNITY_MODE", unity_mode)
    settings = Settings.load()
    assert settings.tcad_url == ("http://tcad.example:8100" if tcad_mode == "prod" else "http://127.0.0.1:8100")
    assert settings.run_mock_unity is (unity_mode == "mock")


def test_prod_missing_url_fails(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("TCAD_MODE", "prod")
    monkeypatch.delenv("TCAD_PROD_URL", raising=False)
    with pytest.raises(ValueError, match="TCAD_PROD_URL"):
        Settings.load()


def test_inherits_ros_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("ROS_DOMAIN_ID", "27")
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    settings = Settings.load()
    assert settings.ros_domain_id == "27"
    assert settings.rmw_implementation == "rmw_fastrtps_cpp"
    assert settings.ros_event_topic == "/fab/events"
    assert settings.ros_command_topic == "/fab/commands"
    assert settings.ros_diagnosis_request_topic == "/fab/diagnosis_requests"
    assert settings.diagnosis_mode == "mock"


def test_secrets_are_redacted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:supersecret@localhost/test")
    monkeypatch.setenv("APPROVAL_TOKEN", "approval-secret")
    monkeypatch.setenv("ROS_COMMAND_KEY", "ros-secret")
    settings = Settings.load()
    assert "supersecret" not in repr(settings)
    assert "approval-secret" not in repr(settings)
    assert "ros-secret" not in repr(settings)


def test_tcad_prod_requires_api_token(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("TCAD_MODE", "prod")
    monkeypatch.setenv("TCAD_PROD_URL", "http://tcad.example:8100")
    monkeypatch.delenv("TCAD_API_TOKEN", raising=False)
    with pytest.raises(ValueError, match="TCAD_API_TOKEN"):
        Settings.load()


def test_tcad_queue_settings_parse_and_redact_token(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("TCAD_API_TOKEN", "tcad-secret")
    monkeypatch.setenv("TCAD_AUTO_SUBMIT_ENABLED", "false")
    monkeypatch.setenv("TCAD_MAX_CONCURRENT_JOBS", "2")
    monkeypatch.setenv("TCAD_CONNECT_TIMEOUT_SECONDS", "6")
    monkeypatch.setenv("TCAD_REQUEST_TIMEOUT_SECONDS", "31")
    monkeypatch.setenv("TCAD_JOB_DEADLINE_SECONDS", "6001")
    monkeypatch.setenv("TCAD_POLICY_VERSION", "route-v2")
    settings = Settings.load()
    assert settings.tcad_auto_submit_enabled is False
    assert settings.tcad_max_concurrent_jobs == 2
    assert settings.tcad_connect_timeout_seconds == 6
    assert settings.tcad_request_timeout_seconds == 31
    assert settings.tcad_job_deadline_seconds == 6001
    assert settings.tcad_policy_version == "route-v2"
    assert "tcad-secret" not in repr(settings)


@pytest.mark.parametrize("name,value", [
    ("TCAD_MAX_CONCURRENT_JOBS", "0"),
    ("TCAD_CONNECT_TIMEOUT_SECONDS", "0"),
    ("TCAD_REQUEST_TIMEOUT_SECONDS", "-1"),
    ("TCAD_JOB_DEADLINE_SECONDS", "0"),
])
def test_tcad_queue_numeric_settings_must_be_positive(monkeypatch, name, value):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        Settings.load()


def test_tcad_auto_submit_requires_explicit_boolean(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/test")
    monkeypatch.setenv("TCAD_AUTO_SUBMIT_ENABLED", "sometimes")
    with pytest.raises(ValueError, match="TCAD_AUTO_SUBMIT_ENABLED"):
        Settings.load()
