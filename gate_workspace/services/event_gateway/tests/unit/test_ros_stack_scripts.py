import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
BASH = "bash"
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="실행 대상인 Linux/WSL Bash에서 검증하는 통합 테스트",
)


def run_script(name: str, runtime: Path, host_ips: str, *args: str):
    env = os.environ.copy()
    env.update({
        "FAB_RUNTIME_DIR": runtime.as_posix(),
        "FAB_HOST_IPS": host_ips,
    })
    return subprocess.run(
        [BASH, (ROOT / "scripts" / name).as_posix(), *args, "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_wsl_launcher_generates_current_unicast_peers_and_gateway_command(tmp_path):
    result = run_script(
        "ros-stack-wsl.sh",
        tmp_path,
        "192.168.10.182 172.20.32.1",
        "start",
        "--jetson-ip",
        "192.168.10.224",
    )

    assert result.returncode == 0, result.stderr
    xml = (tmp_path / "wsl-fastdds.generated.xml").read_text(encoding="utf-8")
    assert "<address>192.168.10.182</address>" in xml
    assert "<address>192.168.10.224</address>" in xml
    assert "172.20.32.1" not in xml
    assert "event_gateway.ros_adapter" in result.stdout


def test_jetson_launcher_ignores_usb_and_docker_ips_and_starts_both_workers(tmp_path):
    result = run_script(
        "ros-stack-jetson.sh",
        tmp_path,
        "192.168.10.224 192.168.55.1 172.17.0.1",
        "start",
        "--wsl-ip",
        "192.168.10.182",
    )

    assert result.returncode == 0, result.stderr
    xml = (tmp_path / "jetson-fastdds.generated.xml").read_text(encoding="utf-8")
    assert "<address>192.168.10.224</address>" in xml
    assert "<address>192.168.10.182</address>" in xml
    assert "192.168.55.1" not in xml
    assert "172.17.0.1" not in xml
    assert "fab_virtual_lot.surrogate_worker" in result.stdout
    assert "fab_virtual_lot.diagnosis_worker" in result.stdout


def test_launcher_rejects_invalid_peer_ip(tmp_path):
    result = run_script(
        "ros-stack-wsl.sh",
        tmp_path,
        "192.168.10.182",
        "start",
        "--jetson-ip",
        "not-an-ip",
    )

    assert result.returncode != 0
    assert "올바른 IPv4" in result.stderr


def test_common_loader_sources_ros_setup_even_when_nounset_is_enabled(tmp_path):
    setup = tmp_path / "setup.bash"
    setup.write_text(
        'if [ -n "$AMENT_TRACE_SETUP_FILES" ]; then :; fi\n'
        'export FAB_SETUP_LOADED=yes\n',
        encoding="utf-8",
    )
    command = (
        "set -u; "
        f"source '{(ROOT / 'scripts/lib/ros-stack-common.sh').as_posix()}'; "
        f"source_setup_safely '{setup.as_posix()}'; "
        "test \"$FAB_SETUP_LOADED\" = yes; test -o nounset"
    )

    result = subprocess.run(
        [BASH, "-c", command],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_status_helper_works_with_nounset_and_no_pid_file(tmp_path):
    command = (
        "set -u; "
        f"source '{(ROOT / 'scripts/lib/ros-stack-common.sh').as_posix()}'; "
        f"show_managed_status diagnosis-worker '{tmp_path.as_posix()}'"
    )
    result = subprocess.run(
        [BASH, "-c", command], cwd=ROOT, text=True, encoding="utf-8",
        capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "diagnosis-worker: STOPPED"
