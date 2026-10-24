"""Read-only camera/source inventory. Never emits tokens, passwords or image bytes."""
import json
import os
import pathlib
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

PHONE_URL = "http://192.168.10.123:8080/video"
home = pathlib.Path.home()
result = {"login_user": home.name, "phone_url": PHONE_URL, "phone_test": {}, "services": [], "candidate_files": [], "camera_settings": []}
try:
    with urllib.request.urlopen(PHONE_URL, timeout=4) as reply:
        content_type = reply.headers.get_content_type()
        found = False
        buffer = bytearray()
        deadline = time.monotonic() + 8
        while len(buffer) < 1024 * 1024 and time.monotonic() < deadline:
            part = reply.read(4096)
            if not part:
                break
            buffer.extend(part)
            start = buffer.find(b"\xff\xd8")
            if start >= 0 and buffer.find(b"\xff\xd9", start + 2) >= 0:
                found = True
                break
        result["phone_test"] = {"http_status": reply.status, "content_type": content_type, "jpeg_received": found}
except urllib.error.HTTPError as error:
    result["phone_test"] = {"http_status": error.code, "jpeg_received": False}
except Exception as error:
    result["phone_test"] = {"error_type": type(error).__name__, "jpeg_received": False}

roots = {home / "project", home / "projects", home / "smart_factory"}
try:
    lines = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=5).stdout.splitlines()
    for line in lines:
        if not re.search(r":(?:8400|8500)\b", line):
            continue
        ports = re.findall(r":(8400|8500)\b", line)
        for raw_pid in re.findall(r"pid=(\d+)", line):
            proc = pathlib.Path("/proc") / raw_pid
            service = {"pid": int(raw_pid), "ports": ports}
            try:
                cwd = pathlib.Path(os.readlink(proc / "cwd"))
                service["cwd"] = str(cwd)
                if home == cwd or home in cwd.parents:
                    roots.add(cwd)
            except OSError:
                pass
            result["services"].append(service)
except Exception:
    result["listener_inventory"] = "unavailable"

skip = {"venv", ".venv", "node_modules", ".git", "__pycache__", "site-packages", ".cache", "models", "weights", "datasets", "result", "results"}
visited = set()
for root in roots:
    if not root.is_dir():
        continue
    for directory, folders, files in os.walk(root):
        current = pathlib.Path(directory)
        depth = len(current.relative_to(root).parts)
        folders[:] = [f for f in folders if f not in skip and not f.startswith(".") and depth < 5]
        for name in files:
            path = current / name
            if str(path) in visited:
                continue
            visited.add(str(path))
            if name.endswith(".py") and any(word in name.lower() for word in ("camera", "preview", "aoi", "config")):
                if len(result["candidate_files"]) < 120:
                    result["candidate_files"].append(str(path))
            if not (name.startswith(".env") or name.endswith(".env")) or path.stat().st_size > 256 * 1024:
                continue
            try:
                for line in path.read_text(errors="replace").splitlines():
                    match = re.match(r"\s*(?:export\s+)?(CAMERA_SOURCE_URL|CAMERA_MODE|CAMERA_ID)\s*=\s*(.*?)\s*$", line)
                    if not match:
                        continue
                    key, value = match.groups()
                    value = value.strip("\"'")
                    if key == "CAMERA_SOURCE_URL":
                        parsed = urllib.parse.urlsplit(value)
                        host = parsed.hostname or ""
                        if parsed.port:
                            host += ":" + str(parsed.port)
                        value = urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", "")) if parsed.scheme else "configured (non-URL)"
                    elif not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
                        value = "configured"
                    result["camera_settings"].append({"file": str(path), "key": key, "value": value})
            except (OSError, ValueError):
                pass
print(json.dumps(result, ensure_ascii=False, indent=2))
