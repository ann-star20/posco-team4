import json
import sys
import tempfile
import types
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch

import process_worker as worker


class ReferenceChecks(unittest.TestCase):
    def test_sidecar_reference_is_forwarded_to_child_job(self):
        class Process:
            returncode = 0
            async def communicate(self, _):
                return b'COMPUTED_ANALYSIS {}\n', b''
        async def run():
            with patch.object(worker.asyncio, 'create_subprocess_exec', return_value=Process()) as spawn, patch.object(worker, 'validate_analysis'):
                await worker.run_job(Path('/models'), {}, reference_file=Path('/bridge/ref.json'))
                arguments = spawn.call_args.args
                self.assertEqual(arguments[arguments.index('--reference') + 1], str(Path('/bridge/ref.json')))
        asyncio.run(run())

    def test_sidecar_reference_does_not_require_writing_model_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "model"
            root.mkdir()
            bridge = Path(folder) / "bridge"
            bridge.mkdir()
            reference = bridge / "agent_reference.json"
            hashes = {"最終": "fixture", "최종ML/모델/gp.npz": "c02d4f1724f0" + "0" * 52}
            reference.write_text(json.dumps({"status": "passed", "hashes": hashes}), encoding="utf-8")
            fake = types.SimpleNamespace(fingerprint=lambda _: hashes)
            with patch.dict(sys.modules, {"agent_check": fake}):
                self.assertEqual(worker.verify_model(root, reference)["hashes"], hashes)
                reference.write_text(json.dumps({"status": "passed", "hashes": {"changed": "different"}}))
                with self.assertRaises(ValueError):
                    worker.verify_model(root, reference)
            self.assertEqual(list(root.iterdir()), [])

    def test_original_reference_location_remains_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            hashes = {"fixture": "hash"}
            (root / "agent_reference.json").write_text(json.dumps({"status": "passed", "hashes": hashes}))
            with patch.dict(sys.modules, {"agent_check": types.SimpleNamespace(fingerprint=lambda _: hashes)}):
                self.assertEqual(worker.verify_model(root)["hashes"], hashes)


if __name__ == "__main__":
    unittest.main()
