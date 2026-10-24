import importlib.util
import errno
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location("csv_service", Path(__file__).with_name("server.py"))
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
CSV = Path(__file__).with_name("jetson_테스트입력.csv")


class Checks(unittest.TestCase):
    def test_startup_errors_are_distinguished(self):
        self.assertIn("CSV_SERVICE_PORT_IN_USE", service.startup_error(OSError(errno.EADDRINUSE, "Address already in use")))
        self.assertIn("CSV_SERVICE_FILE_MISSING", service.startup_error(FileNotFoundError(errno.ENOENT, "No such file")))
        self.assertIn("CSV_SERVICE_INVALID_DATA", service.startup_error(ValueError("CSV columns missing")))
        self.assertIn("CSV_SERVICE_OS_ERROR", service.startup_error(PermissionError(errno.EACCES, "Permission denied")))

    def test_values_and_missing_high_precision(self):
        data = service.load_dataset(CSV)
        normal = next(r for r in data["rows"] if r["id"] == "B001")
        self.assertEqual(normal["dose_ratio"], 1)
        self.assertAlmostEqual(normal["tcad"]["bv"], 41.11703688066623)
        self.assertNotEqual(normal["tcad"]["vth"], normal["pc"]["vth"])
        missing = next(r for r in data["rows"] if r["id"] == "B122")
        self.assertFalse(missing["has_high_precision_vth"])
        predicted = next(r for r in data["rows"] if r["id"] == "N001")
        self.assertFalse(predicted["has_tcad"])
        self.assertIsNone(predicted["tcad"])
        self.assertTrue(predicted["has_pc"])
        self.assertEqual(len(data["rows"]), 100)

    def test_invalid_number_rejected(self):
        raw = CSV.read_text(encoding="utf-8-sig").replace("B001,TCAD,1.0,", "B001,TCAD,nan,", 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(ValueError):
                service.load_dataset(path)

    def test_http_reads_only_named_resource(self):
        server = service.make_server(CSV, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urllib.request.urlopen(address + "/api/v1/test-samples") as response:
                result = json.load(response)
            self.assertEqual(result, service.load_dataset(CSV))
            # Simulate Linux's occupied-port error; Windows may permit SO_REUSEADDR rebinding.
            with patch.object(service, "make_server", side_effect=OSError(errno.EADDRINUSE, "Address already in use")):
                self.assertIsNone(service.start_or_reuse(CSV, server.server_port))
            with tempfile.TemporaryDirectory() as folder:
                changed = Path(folder) / "changed.csv"
                changed.write_bytes(CSV.read_bytes() + b"\n")
                with patch.object(service, "make_server", side_effect=OSError(errno.EADDRINUSE, "Address already in use")):
                    with self.assertRaises(OSError):
                        service.start_or_reuse(changed, server.server_port)
            # Reuse and mismatch checks must not stop the existing service.
            with urllib.request.urlopen(address + "/api/v1/test-samples") as response:
                self.assertEqual(json.load(response), result)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(address + "/server.py")
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
