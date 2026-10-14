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


def test_secrets_are_redacted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:supersecret@localhost/test")
    monkeypatch.setenv("APPROVAL_TOKEN", "approval-secret")
    monkeypatch.setenv("ROS_COMMAND_KEY", "ros-secret")
    settings = Settings.load()
    assert "supersecret" not in repr(settings)
    assert "approval-secret" not in repr(settings)
    assert "ros-secret" not in repr(settings)
