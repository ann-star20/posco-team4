"""Read-only CSV service, bound to Jetson loopback and accessed over SSH forwarding."""
import argparse
import csv
import errno
import hashlib
import io
import json
import math
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def load_dataset(path):
    raw = Path(path).read_bytes()
    if len(raw) > 5_000_000:
        raise ValueError("CSV too large")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"ID", "구분", "도즈", "에피", "산화막"}
    required.update(f"{prefix}_{field}" for prefix in ("TCAD", "PC") for field in ("vth", "gm", "id4v", "bv"))
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("CSV columns missing")
    rows, ids = [], set()

    def number(row, key, positive=False):
        value = float(row[key])
        if not math.isfinite(value) or (positive and value <= 0):
            raise ValueError("Invalid number in " + key)
        return value

    for row in reader:
        identity = row["ID"].strip()
        if not identity or len(identity) > 100 or identity in ids or len(rows) >= 10000:
            raise ValueError("Invalid or duplicate sample ID")
        ids.add(identity)
        item = {"id": identity, "kind": row["구분"].strip(),
                "dose_ratio": number(row, "도즈", True),
                "epi_doping_ratio": number(row, "에피", True),
                "oxide_ratio": number(row, "산화막", True)}
        for prefix in ("TCAD", "PC"):
            fields = ("vth", "gm", "id4v", "bv")
            present = [bool(row[f"{prefix}_{field}"].strip()) for field in fields]
            if any(present) and not all(present):
                raise ValueError("Partial electrical quartet")
            item["has_" + prefix.lower()] = all(present)
            item[prefix.lower()] = ({field: number(row, f"{prefix}_{field}", field != "vth")
                                    for field in fields} if all(present) else None)
        # Keep partial high-precision references separate; never silently mix sources.
        for field in ("vth", "bv"):
            key = "PC_고정밀_" + field
            present = bool(row.get(key, "").strip())
            item["has_high_precision_" + field] = present
            item["high_precision_" + field] = number(row, key) if present else 0
        rows.append(item)
    if not rows:
        raise ValueError("Empty CSV")
    return {"schema_version": 1, "data_source": "jetson_csv_test",
            "dataset_sha256": hashlib.sha256(raw).hexdigest(),
            "epi_semantics": "drift_doping_ratio", "rows": rows}


def make_server(path, port=8601):
    body = json.dumps(load_dataset(path), ensure_ascii=False, allow_nan=False).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/api/v1/test-samples":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def startup_error(error):
    if isinstance(error, OSError):
        if error.errno == errno.EADDRINUSE or getattr(error, "winerror", None) == 10048:
            return ("CSV_SERVICE_PORT_IN_USE: Jetson 127.0.0.1:8601 is already in use. "
                    "Existing service did not match this CSV or did not respond. No process was stopped.")
        if error.errno == errno.ENOENT:
            return "CSV_SERVICE_FILE_MISSING: uploaded CSV file was not found. Run the copy step again."
        return f"CSV_SERVICE_OS_ERROR: {type(error).__name__}, errno={error.errno}, {error.strerror}"
    return f"CSV_SERVICE_INVALID_DATA: {type(error).__name__}: {error}"


def start_or_reuse(path, port=8601):
    try:
        return make_server(path, port)
    except OSError as error:
        if error.errno != errno.EADDRINUSE and getattr(error, "winerror", None) != 10048:
            raise
        # Reuse only a complete, matching dataset; leave every existing process untouched.
        expected = load_dataset(path)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/api/v1/test-samples", timeout=3) as response:
                raw = response.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise ValueError("Response too large")
                actual = json.loads(raw)
        except (OSError, ValueError, urllib.error.URLError):
            raise error from None
        if actual != expected:
            raise error
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()
    try:
        server = start_or_reuse(args.csv)
    except (ValueError, OSError) as error:
        raise SystemExit(startup_error(error))
    if server is None:
        print("Existing CSV service verified: same dataset hash and all rows. Reusing without restart.", flush=True)
    print("UNITY_TEST_DATA_READY http://127.0.0.1:8601/api/v1/test-samples", flush=True)
    try:
        if server is None:
            threading.Event().wait()  # Keep the SSH tunnel open without owning the existing service.
        else:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
