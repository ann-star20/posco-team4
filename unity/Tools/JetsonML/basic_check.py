"""Run the supplied basic ML checks without enabling TabPFN or changing models."""
import importlib.util
import json
import platform
import runpy
import sys
import traceback
from pathlib import Path

root = Path(__file__).resolve().parent
status_path = root / "basic_status.json"

try:
    import numpy as np

    print("DEVICE", platform.machine(), "PYTHON", platform.python_version(), "NUMPY", np.__version__, flush=True)
    model_dir = root / "최종ML"
    for relative in ("2단_GP.py", "jetson_검증.py", "jetson_벤치.py", "모델/gp.npz", "테스트/jetson_테스트입력.csv"):
        if not (model_dir / relative).is_file():
            raise FileNotFoundError(relative)
    runpy.run_path(str(model_dir / "2단_GP.py"), run_name="__main__")
    # The supplied validator otherwise initializes optional high-precision models.
    sys.modules["tabpfn"] = None
    validation = runpy.run_path(str(model_dir / "jetson_검증.py"), run_name="__main__")
    if not validation["ok_all"]:
        raise RuntimeError("Basic validation reported failed checks")
    runpy.run_path(str(model_dir / "jetson_벤치.py"), run_name="__main__")
    result = {"status": "passed", "scope": "basic GP only", "python": platform.python_version(), "numpy": np.__version__}
except Exception as exc:
    traceback.print_exc()
    result = {"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}

status_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("JETSON_BASIC_STATUS", json.dumps(result, ensure_ascii=False), flush=True)
sys.exit(0 if result["status"] == "passed" else 1)
