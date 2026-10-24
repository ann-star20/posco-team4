from pathlib import Path


def test_ros_setup_is_loaded_before_nounset_is_enabled():
    root = Path(__file__).resolve().parents[4]

    for relative in ("scripts/run-mock-e2e.sh", "scripts/run-full-stack.sh"):
        source = (root / relative).read_text(encoding="utf-8")
        assert source.index("source /opt/ros/humble/setup.bash") < source.index("set -u")
        assert "/opt/ros/humble/local/lib/python3.10/dist-packages" in source
        assert "$PWD/jetson_ws/src/fab_virtual_lot" in source


def test_full_stack_starts_direct_aoi_unity_only_when_enabled():
    root = Path(__file__).resolve().parents[4]
    source = (root / "scripts/run-full-stack.sh").read_text(encoding="utf-8")
    assert '"${AOI_UNITY_DIRECT_ENABLED:-false}" == true' in source
    assert '"$python_bin" -m fab_virtual_lot.aoi_unity' in source
