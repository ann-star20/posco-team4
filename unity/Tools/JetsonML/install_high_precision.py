"""Install TabPFN in a separate venv while retaining the existing Jetson torch."""
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import traceback
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT / ".venv-tabpfn-9.2"
ENV_PYTHON = ENVIRONMENT / "bin" / "python"
PROBE = """import json,sys,torch,numpy
r=dict(prefix=sys.prefix,base_prefix=sys.base_prefix,torch=torch.__version__,torch_file=torch.__file__,numpy=numpy.__version__,numpy_file=numpy.__file__,cuda_compiled=torch.version.cuda,cuda_available=torch.cuda.is_available())
try:
    a=torch.tensor([1.0]).numpy()
    b=torch.from_numpy(numpy.array([2.0]))
    r['numpy_bridge_ok']=bool(a[0]==1.0 and b.item()==2.0)
except Exception as e:
    r['numpy_bridge_ok']=False
    r['numpy_bridge_error']=type(e).__name__+': '+str(e)
print(json.dumps(r))
"""


def run(command, **kwargs):
    print("STEP", " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, timeout=900, **kwargs)


def probe(python):
    completed = run([python, "-c", PROBE], capture_output=True, text=True)
    if completed.stderr:
        print("PROBE_STDERR", completed.stderr[:6000], flush=True)
    return json.loads(completed.stdout.splitlines()[-1])


def protected_plan(plan, allow_numpy=False):
    names = [entry["metadata"]["name"].lower().replace("_", "-") for entry in plan.get("install", [])]
    protected = {"torch", "torchvision", "torchaudio"}
    if not allow_numpy:
        protected.add("numpy")
    forbidden = set(names) & protected
    if forbidden:
        raise RuntimeError("Installer would replace protected packages: " + ", ".join(sorted(forbidden)))


def main():
    report = {"status": "installing", "environment": str(ENVIRONMENT), "started_at_unix": time.time()}
    try:
        if sys.platform != "linux":
            raise RuntimeError("This installer is for the Jetson Linux deployment only")
        before = probe(sys.executable)
        report["base_before"] = before
        print("BASE_ENVIRONMENT", json.dumps(before), flush=True)
        repair_numpy = not before["numpy_bridge_ok"] and before["numpy"].startswith("2.")
        if not before["numpy_bridge_ok"] and not repair_numpy:
            raise RuntimeError("Torch/NumPy bridge failed for an unsupported reason")
        numpy_version = "1.26.4" if repair_numpy else importlib.metadata.version("numpy")
        report["venv_numpy_target"] = numpy_version
        constraints = ROOT / "tabpfn-protected-constraints.txt"
        constraints.write_text("torch==" + importlib.metadata.version("torch") + "\nnumpy==" + numpy_version + "\n", encoding="utf-8")
        if ENVIRONMENT.exists() and not (ENVIRONMENT / "pyvenv.cfg").is_file():
            raise RuntimeError("Environment path exists but is not a virtual environment")
        if not ENVIRONMENT.exists():
            venv.EnvBuilder(system_site_packages=True, with_pip=False).create(ENVIRONMENT)
        run([ENV_PYTHON, "-c", "import sys; assert sys.prefix != sys.base_prefix; import pip; print('VENV_PIP_READY', pip.__version__)"])
        run([ENV_PYTHON, "-m", "pip", "install", "--index-url", "https://pypi.org/simple", "--upgrade", "pip"])
        install = [ENV_PYTHON, "-m", "pip", "install", "--index-url", "https://pypi.org/simple",
                   "--only-binary=:all:", "--constraint", constraints, "tabpfn==9.2.0"]
        plan_path = ROOT / "tabpfn-install-plan.json"
        run(install + ["--dry-run", "--report", plan_path])
        protected_plan(json.loads(plan_path.read_text(encoding="utf-8")), allow_numpy=repair_numpy)
        run(install + ["--report", ROOT / "tabpfn-installed.json"])
        after = probe(ENV_PYTHON)
        report["environment_probe"] = after
        for key in ("torch", "torch_file", "cuda_available"):
            if before[key] != after[key]:
                raise RuntimeError("Protected runtime changed: " + key)
        if after["numpy"] != numpy_version or not after["numpy_bridge_ok"]:
            raise RuntimeError("Venv NumPy version or torch array conversion check failed")
        if repair_numpy and not Path(after["numpy_file"]).resolve().is_relative_to(ENVIRONMENT.resolve()):
            raise RuntimeError("NumPy compatibility adjustment escaped the virtual environment")
        report["base_after"] = probe(sys.executable)
        if report["base_after"] != before:
            raise RuntimeError("Base environment changed")
        run([ENV_PYTHON, ROOT / "high_precision_check.py"])
        test = json.loads((ROOT / "high_precision_result.json").read_text(encoding="utf-8"))
        report["high_precision"] = test
        report["status"] = test["status"]
    except Exception as exc:
        traceback.print_exc()
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    report["finished_at_unix"] = time.time()
    (ROOT / "high_precision_install_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("JETSON_HP_INSTALL_STATUS " + json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
