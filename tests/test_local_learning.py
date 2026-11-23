import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.agents.automation import autonomy_runtime, compare_local_code, local_model_routing
from tests.test_compare_local_code import completed, write
from tests.test_ollama_native_code import GEMMA, QWEN, REASONER


def approved_route(*candidates):
    return {"id": "next-task", "project": "tel99", "base_sha": "0" * 40,
            "objective": "Corriger un normaliseur", "routing": {"candidates": list(candidates)}}


def stored_result(run, mid, *, model=GEMMA, project="tel99", at=None, accepted=True, verified=True):
    digest = "1" * 64
    checks = [
        {"name": "bounded-model-receipt", "ok": verified},
        {"name": "approved-function-diff", "ok": True},
        {"name": "baseline-fails", "ok": True, "exit_code": 1},
        {"name": "candidate-passes", "ok": accepted, "exit_code": 0 if accepted else 1},
    ]
    proof = {"verifier": autonomy_runtime.local_codegen.VERIFIER, "base_sha": "0" * 40, "path": f"demo/{mid}.py",
             "function": "normalize", "test_sha256": digest, "artifact_sha256": digest,
             "model": model["model"], "ok": accepted, "checks": checks, "generation_seconds": 21}
    checkpoint = {"id": mid, "project": project, "at": at if at is not None else time.time() - 1,
                  "contract_sha256": digest, "status": "ACCEPTED" if accepted else "BLOCKED",
                  "model_route": {"selection": model, "decision": {"difficulty": "easy"}},
                  "verification": proof}
    if accepted:
        checkpoint["verdict"] = {"validated": True}
    run.store.put_cas(f"kilo-local/{mid}", checkpoint, None)
    run.store.put_cas(f"kilo-claims/{mid}", {"contract_sha256": digest, "project": project}, None)


class LocalLearningTests(unittest.TestCase):
    def test_routing_memory_excludes_stale_foreign_and_unverified_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = autonomy_runtime.Runtime(tmp)
            for index in range(5):
                stored_result(run, f"pass-{index}")
                stored_result(run, f"fail-{index}", model=QWEN, accepted=False)
            stored_result(run, "stale", at=time.time() - 65 * 86400)
            stored_result(run, "future", at=time.time() + 3600)
            stored_result(run, "foreign", project="other")
            stored_result(run, "no-proof", verified=False)
            result = run.local_model_observations(approved_route(GEMMA, QWEN))
            self.assertEqual(result["easy"][GEMMA["id"]]["tasks"], 5)
            self.assertEqual(result["easy"][GEMMA["id"]]["success_rate"], 1.0)
            self.assertEqual(result["easy"][GEMMA["id"]]["generation_seconds"], 21.0)
            self.assertEqual(result["easy"][QWEN["id"]]["tasks"], 5)
            self.assertEqual(result["easy"][QWEN["id"]]["success_rate"], 0.0)

    def test_verified_fresh_outcomes_can_disqualify_a_model_below_quality_floor(self):
        contract = approved_route(GEMMA, QWEN)
        source = "def normalize(n):\n    return n\n"
        with (patch.object(local_model_routing, "available_memory_mib", return_value=12_000),
              patch.object(local_model_routing, "_probe_ollama", side_effect=lambda tag: (tag, None, 0))):
            report = local_model_routing.choose(contract, source, measured_outcomes={
                "easy": {GEMMA["id"]: {"tasks": 5, "success_rate": 0.0, "generation_seconds": 21}},
            })
            self.assertEqual(QWEN, report["selection"])
            self.assertIn("quality", report["inventory"][0]["reason"])

    def test_installed_qwen35_requires_passing_performance_evidence(self):
        contract = approved_route(REASONER)
        source = "def normalize(n):\n    return n\n"
        with (patch.object(local_model_routing, "available_memory_mib", return_value=12_000),
              patch.object(local_model_routing, "_probe_ollama", return_value=(REASONER["model"], None, 0))):
            self.assertIsNone(local_model_routing.choose(contract, source)["selection"])
            report = local_model_routing.choose(contract, source, measured_outcomes={
                "easy": {REASONER["id"]: {"tasks": 5, "success_rate": 0.8, "generation_seconds": 42}},
            })
            self.assertEqual(REASONER, report["selection"])

    def test_ollama_selection_accounts_for_model_size_and_host_reserve(self):
        with (patch.object(local_model_routing, "available_memory_mib", return_value=7000),
              patch.object(local_model_routing, "_probe_ollama", side_effect=lambda tag: (tag, None, 0))):
            report = local_model_routing.choose(approved_route(GEMMA, QWEN), "def normalize(n):\n    return n\n")
        self.assertEqual(QWEN, report["selection"])
        self.assertIn("memory", report["inventory"][0]["reason"])

    def test_fixed_ollama_sessions_can_calibrate_later_routed_missions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "historical"
            pin = completed(session, "before", REASONER["model"], port=11434, block_first=True)
            samples = compare_local_code.read_calibration(session, pin)
            self.assertEqual(4, len(samples))
            self.assertTrue(all(sample["binding"] == REASONER for sample in samples))
            self.assertTrue(all(sample["pin"] == pin for sample in samples))
            base = samples[0]["base_sha"]
            run = autonomy_runtime.Runtime(root / "new-state", calibration=samples)
            mission = {**approved_route(REASONER), "base_sha": base}
            with patch.object(autonomy_runtime.time, "time", return_value=200):
                quality = run.local_model_observations(mission)
                # All fixture outcomes repair the same function. They are one sample.
                self.assertEqual(1, sum(rows[REASONER["id"]]["tasks"] for rows in quality.values()))
            self.assertEqual({}, run.local_model_observations(mission))

    def test_held_out_comparison_rejects_reworded_task_on_previously_seen_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "base"
            candidate = root / "candidate"
            base_pin = completed(baseline, "base", "fixed-a")
            candidate_pin = completed(candidate, "candidate", "fixed-b")
            learning = json.loads((baseline / "registry.json").read_bytes())
            source = root / "learning.json"
            for task in learning["missions"]:
                task["objective"] += " Nouvelle formulation."
            learning["approvals"] = autonomy_runtime.seal(learning["missions"])
            pin = write(source, learning)
            with self.assertRaisesRegex(ValueError, "held-out scopes overlap"):
                compare_local_code.compare_sessions(
                    baseline, base_pin, candidate, candidate_pin, learning_sources=[(source, pin)],
                )

    def test_held_out_comparison_records_the_operator_pinned_learning_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline, candidate = root / "base", root / "candidate"
            base_pin = completed(baseline, "base", "fixed-a")
            candidate_pin = completed(candidate, "candidate", "fixed-b")
            source = root / "learning.json"
            history = json.loads((baseline / "registry.json").read_bytes())
            for task in history["missions"]:
                task["function"] = "is_eligible_mission"
                task["test"] = "# separate learning fixture " + task["id"]
            history["approvals"] = autonomy_runtime.seal(history["missions"])
            pin = write(source, history)
            report = compare_local_code.compare_sessions(
                baseline, base_pin, candidate, candidate_pin, learning_sources=[(source, pin)],
            )
            self.assertEqual([pin], report["cohort"]["excluded_registry_sha256"])
            self.assertEqual(5, report["comparison"]["task_count"])
            with self.assertRaisesRegex(ValueError, "Learning registry pin"):
                compare_local_code.compare_sessions(
                    baseline, base_pin, candidate, candidate_pin, learning_sources=[(source, "0" * 64)],
                )

    def test_github_telemetry_reuses_checkpoint_and_does_not_export_private_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "session"
            completed(session, "github", GEMMA["model"], port=11434)
            ledger = session / "code-state"
            task = json.loads((session / "registry.json").read_bytes())["missions"][0]
            contract = autonomy_runtime.fingerprint(task)
            pin = "9" * 64
            ledger_store = ledger / "ledger"
            write(ledger_store / "github-local-code/config.json", {
                "repo": "khalidd692/telcoin-trading-intelligence99", "profile": "github-local-code",
                "issue": 174, "mandate_id": 998, "mandate_sha256": pin, "campaign": True,
            })
            write(ledger_store / f"kilo-github/approvals/{task['id']}.json", {
                "mission": task, "issue": 175, "contract_sha256": contract, "comment_id": 999,
                "base": "agents/isolated-test", "base_sha": task["base_sha"],
            })
            waiting = {**task, "id": "github-waiting"}
            write(ledger_store / "kilo-github/approvals/github-waiting.json", {
                "mission": waiting, "issue": 176, "contract_sha256": autonomy_runtime.fingerprint(waiting),
                "comment_id": 1000, "base": "agents/isolated-test", "base_sha": waiting["base_sha"],
            })
            destination = root / "history.json"
            from scripts.agents.automation import campaign_learning
            before = {file: file.read_bytes() for file in ledger.rglob("*") if file.is_file()}
            output = campaign_learning.export(ledger, pin, destination)
            self.assertEqual(1, output["summary"]["accepted"])
            self.assertEqual("ACCEPTED", output["missions"][0]["status"])
            self.assertEqual(0.25, output["missions"][0]["attempts"][0]["generation_seconds"])
            self.assertEqual(999, output["missions"][0]["approval_comment"])
            self.assertEqual([{"id": "github-waiting", "issue": 176, "status": "WAITING"}], output["pending"])
            self.assertEqual(before, {file: file.read_bytes() for file in ledger.rglob("*") if file.is_file()})
            exported = destination.read_text(encoding="utf-8")
            self.assertNotIn(task["objective"], exported)
            self.assertNotIn(task["test"], exported)
            self.assertNotIn("return False", exported)
            with self.assertRaises(FileExistsError):
                campaign_learning.export(ledger, pin, destination)
            with self.assertRaisesRegex(ValueError, "mandate"):
                campaign_learning.export(ledger, "a" * 64, root / "invalid.json")


    def test_paired_evaluation_aggregates_ten_distinct_cases_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            pins = []
            functions = [
                ("repository_allowed", "branch_is_protected", "work_branch_name", "_labels", "is_eligible_mission"),
                ("select_mission", "evaluate_preconditions", "utcnow_iso", "mission_content", "mission_digest"),
            ]
            for index in range(2):
                pair = []
                for side, model in (("base", "fixed-a"), ("candidate", "fixed-b")):
                    root = Path(tmp) / f"{side}-{index}"
                    pair.extend((root, completed(root, f"{side}-{index}", model, functions=functions[index])))
                pins.append(pair)
            result = compare_local_code.compare_cohorts(pins)
            self.assertEqual(10, result["comparison"]["task_count"])
            self.assertEqual("reject", result["comparison"]["verdict"])
            with self.assertRaisesRegex(ValueError, "reused"):
                compare_local_code.compare_cohorts([pins[0], pins[0]])
