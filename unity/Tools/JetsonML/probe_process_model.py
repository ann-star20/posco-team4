"""Read-only model/runtime location inventory. Never reads credentials or prints environment."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def inventory(home):
    home = Path(home)
    roots, runtimes = [], {sys.executable}
    visited = 0
    skip = {".cache", ".local", ".git", "node_modules", "site-packages", "__pycache__", "Trash"}
    for current, directories, files in os.walk(home, followlinks=False):
        visited += 1
        path = Path(current)
        if visited > 8000:
            break
        depth = len(path.relative_to(home).parts)
        if (path / "최종ML" / "모델" / "gp.npz").is_file():
            gp = path / "최종ML" / "모델" / "gp.npz"
            roots.append({"path": str(path), "has_agent": (path / "진단에이전트" / "진단에이전트.py").is_file(),
                          "has_reference": (path / "agent_reference.json").is_file(),
                          "has_check": (path / "agent_check.py").is_file(),
                          "gp_sha256": hashlib.sha256(gp.read_bytes()).hexdigest()})
        for folder in directories:
            candidate = path / folder / "bin" / "python"
            if candidate.is_file() and os.access(candidate, os.X_OK) and len(runtimes) < 12:
                runtimes.add(str(candidate))
        directories[:] = [folder for folder in directories if folder not in skip and not folder.startswith(".venv") and folder not in {"venv", "env"} and depth < 6]
    info = []
    code = "import importlib.util,json,sys;print(json.dumps({'version':sys.version.split()[0],'numpy':importlib.util.find_spec('numpy') is not None,'websockets':importlib.util.find_spec('websockets') is not None,'tabpfn':importlib.util.find_spec('tabpfn') is not None}))"
    for runtime in sorted(runtimes):
        item = {"path": runtime}
        try:
            result = subprocess.run([runtime, "-c", code], capture_output=True, text=True, timeout=8)
            if result.returncode == 0:
                item.update(json.loads(result.stdout))
            else:
                item["probe"] = "failed"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            item["probe"] = "failed"
        info.append(item)
    return {"schema_version": 1, "home": str(home), "model_roots": roots[:30], "python_runtimes": info,
            "scan_limit_reached": visited > 8000}


if __name__ == "__main__":
    print(json.dumps(inventory(Path.home()), ensure_ascii=True))
