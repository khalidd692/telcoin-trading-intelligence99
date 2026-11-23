import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.agents.automation import prepare_local_code


SOURCE = Path(__file__).resolve().parents[1] / "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
PIN = "dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9"
SMALL = ("local/llama-qwen2.5-3b", "18089")
LARGE = ("local/llama-qwen2.5-coder-7b", "18089")


class PrepareLocalCodeTests(unittest.TestCase):
    def test_fixed_pairs_keep_tests_and_have_new_disjoint_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            a = Path(temporary) / "a.json"
            b = Path(temporary) / "b.json"
            args = [str(SOURCE), "--source-sha256", PIN, "--mode", "fixed"]
            for path, binding, prefix in ((a, SMALL, "bench-a"), (b, LARGE, "bench-b")):
                self.assertEqual(prepare_local_code.main(
                    [*args, "--binding", *binding, "--prefix", prefix, "--output", str(path)]), 0)
            first = json.loads(a.read_bytes())["missions"]
            second = json.loads(b.read_bytes())["missions"]
            self.assertTrue({m["id"] for m in first}.isdisjoint({m["id"] for m in second}))
            self.assertEqual([m["test"] for m in first], [m["test"] for m in second])
            self.assertEqual([m["base_sha"] for m in first], [m["base_sha"] for m in second])
            self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), PIN)

    def test_routed_escalation_is_sealed_with_a_new_id_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "routing.json"
            args = [str(SOURCE), "--source-sha256", PIN, "--mode", "routed",
                    "--binding", *SMALL, "--binding", *LARGE, "--prefix", "next",
                    "--escalate", "qwen-repair-metadata-shape-20261123", "--output", str(target)]
            self.assertEqual(prepare_local_code.main(args), 0)
            raw = target.read_bytes()
            registry = json.loads(raw)
            self.assertEqual(len(registry["missions"]), 6)
            parent = registry["missions"][1]
            child = registry["missions"][-1]
            self.assertNotEqual(parent["id"], child["id"])
            self.assertEqual(child["escalates_from"], parent["id"])
            self.assertEqual(child["test"], parent["test"])
            self.assertEqual(prepare_local_code.main(args), 2)
            self.assertEqual(target.read_bytes(), raw)
