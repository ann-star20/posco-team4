"""The Jetson package must be discovered by colcon as an ament Python package."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_colcon_discovers_ament_python_package():
    if shutil.which("colcon") is None:
        pytest.skip("colcon is unavailable in this Python environment")
    package = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["colcon", "list", "--base-paths", str(package.parent),
         "--packages-select", "fab_virtual_lot"],
        capture_output=True, text=True, check=True,
    )
    assert "fab_virtual_lot" in result.stdout
    assert "(ros.ament_python)" in result.stdout
