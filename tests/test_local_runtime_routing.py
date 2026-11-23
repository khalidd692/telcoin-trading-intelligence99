import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import autonomy_runtime as runtime
from tests.test_local_codegen import mission


SMALL = {"id": "local/llama-qwen2.5-3b", "model": "qwen2.5-3b-instruct", "port": 18089}
LARGE = {"id": "local/llama-qwen2.5-coder-7b", "model": "qwen2.5-coder-7b-instruct", "port": 18090}


def routed(**changes):
    value = mission(max_attempts=2, routing={"candidates": [SMALL, LARGE]}, **changes)
    del value["model"], value["port"]
    return value


def receipt(contract):
    candidate = "def increment(value):\n    return value + 1"
    return {"artifact": candidate, "sha256": hashlib.sha256(candidate.encode()).hexdigest(),
            "specialist_id": contract["specialist"], "provider": "loopback-code", "model": contract["model"]}


def verdict(contract, result, ok):
    return {"ok": ok, "verifier": runtime.local_codegen.VERIFIER,
            "artifact_sha256": result["sha256"], "base_sha": contract["base_sha"],
            "model": contract["model"], "path": contract["path"],
            "test_sha256": hashlib.sha256(contract["test"].encode()).hexdigest(),
            "candidate_sha256": "2" * 64, "diff_sha256": "3" * 64,
            "checks": [{"name": name, "ok": passed,
                        **({"exit_code": 0 if passed else 1} if name == "candidate-passes" else {})}
                       for name, passed in (
                ("bounded-model-receipt", True), ("approved-function-diff", True),
                ("baseline-fails", True), ("candidate-passes", ok))],
            **({"feedback": {"kind": "candidate-test", "line": 1}} if not ok else {})}


class RoutedRuntimeTests(unittest.TestCase):
    def test_delivery_can_use_an_accepted_predecessor_or_its_authorized_successor(self):
        parent = routed(id="route-parent")
        followup = routed(id="route-escalation", escalates_from=parent["id"])
        queue = [parent, followup]
        self.assertTrue(runtime.delivered(queue, {parent["id"]: "ACCEPTED"}))
        self.assertTrue(runtime.delivered(queue, {parent["id"]: "BLOCKED", followup["id"]: "ACCEPTED"}))
        self.assertFalse(runtime.delivered(queue, {parent["id"]: "BLOCKED"}))

    def test_selection_survives_stop_and_repair_uses_same_model(self):
        contract = routed()
        runtime.validate_contract(contract, runtime.seal([contract]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []

            def worker(effective):
                calls.append(effective["model"])
                return receipt(effective)

            def verify(effective, result):
                if len(calls) == 1:
                    (root / "stop.request").touch()
                return verdict(effective, result, len(calls) == 2)

            with (patch.object(runtime.local_codegen, "choose_route", return_value={"selection": SMALL}) as choose,
                  patch.object(runtime.local_codegen, "check_selected", return_value=True)):
                first = runtime.Runtime(root, executor=worker, verifier=verify)
                first.run_queue([contract], runtime.seal([contract]))
                self.assertEqual(first.state(contract)["status"], "WORKER_EXITED")
                self.assertEqual(first.state(contract)["model_route"]["selection"], SMALL)
                (root / "stop.request").unlink()
                resumed = runtime.Runtime(root, executor=worker,
                                          verifier=lambda m, r: verdict(m, r, len(calls) == 2))
                resumed.run_queue([contract], runtime.seal([contract]))
                resumed.run_queue([contract], runtime.seal([contract]))
                self.assertEqual(resumed.state(contract)["status"], "ACCEPTED")
                self.assertEqual(calls, [SMALL["model"], SMALL["model"]])
                self.assertEqual(choose.call_count, 1)

    def test_escalation_requires_authorized_new_id_and_proven_failure(self):
        parent = routed(id="route-parent")
        next_contract = routed(id="route-escalation", escalates_from=parent["id"])
        approvals = runtime.seal([parent, next_contract])
        with tempfile.TemporaryDirectory() as temporary:
            calls = []

            def worker(effective):
                calls.append((effective["id"], effective["model"]))
                return receipt(effective)

            def choose(m, **kwargs):
                if m == parent:
                    self.assertEqual(kwargs, {})
                    return {"selection": SMALL}
                self.assertEqual(kwargs["exclude"], (SMALL["id"],))
                self.assertGreater(kwargs["minimum_memory_mib"], 0)
                return {"selection": LARGE}

            with (patch.object(runtime.local_codegen, "choose_route", side_effect=choose),
                  patch.object(runtime.local_codegen, "check_selected", return_value=True)):
                run = runtime.Runtime(Path(temporary), executor=worker,
                                      verifier=lambda m, r: verdict(m, r, m["model"] == LARGE["model"]))
                run.run_queue([next_contract, parent], approvals)
                before = run.state(parent)
                self.assertEqual(before["status"], "BLOCKED")
                self.assertEqual(run.state(next_contract)["status"], "ACCEPTED")
                self.assertEqual(calls, [(parent["id"], SMALL["model"])] * 2
                                 + [(next_contract["id"], LARGE["model"])])
                run.run_queue([parent, next_contract], approvals)
                self.assertEqual(run.state(parent), before)

    def test_escalation_changed_scope_has_no_worker_call(self):
        parent = routed(id="route-parent")
        other = routed(id="wrong-scope", path="demo/different.py", escalates_from=parent["id"])
        with tempfile.TemporaryDirectory() as temporary:
            with (patch.object(runtime.local_codegen, "choose_route", return_value={"selection": SMALL}),
                  patch.object(runtime.local_codegen, "check_selected", return_value=True)):
                run = runtime.Runtime(Path(temporary), executor=receipt, verifier=lambda m, r: verdict(m, r, False))
                run.run_queue([parent, other], runtime.seal([parent, other]))
                self.assertEqual(run.state(parent)["status"], "BLOCKED")
                self.assertEqual(run.state(other), {})
