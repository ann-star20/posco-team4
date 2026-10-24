"""The WSL launcher must retain paths installed by ROS setup.bash."""

import os
from pathlib import Path
import shutil
import subprocess


def test_launcher_preserves_existing_pythonpath(tmp_path):
    root = Path(__file__).resolve().parents[4]
    script = tmp_path / "scripts" / "run-integration.sh"
    script.parent.mkdir()
    shutil.copyfile(root / "scripts" / "run-integration.sh", script)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://unused/unused\n"
        "APPROVAL_OPERATOR=test\nAPPROVAL_TOKEN=test\nROS_COMMAND_KEY=test\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "pythonpaths"
    (bin_dir / "python3").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$PYTHONPATH" >> "$CAPTURE"\n'
    )
    (bin_dir / "ros2").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "python3").chmod(0o755)
    (bin_dir / "ros2").chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "PYTHONPATH": "/opt/ros/humble/local/lib/python3.10/dist-packages",
        "CAPTURE": str(capture),
    })

    result = subprocess.run(["bash", str(script)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)

    assert result.returncode == 0, result.stderr
    paths = capture.read_text().splitlines()
    assert len(paths) == 4
    assert all("/opt/ros/humble/local/lib/python3.10/dist-packages" in path.split(":")
               for path in paths)
