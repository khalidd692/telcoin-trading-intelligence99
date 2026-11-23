import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.agents.automation.autonomy_runtime import fingerprint
from scripts.agents.automation import local_codegen
from scripts.agents.protocol.handoff import verify_mission


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return sha(path.read_bytes())


def completed(root, label, model, *, edit_test=False, tamper_model=False, repair_first=False, block_first=False):
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tasks = [
        {
            "id": f"{label}-{i}", "owner": "local", "project": "tel99", "specialist": "tel99-dev",
            "priority": "P1", "dependencies": [], "objective": f"Test objective {i}",
            "base_sha": base, "path": "scripts/agents/automation/policy.py", "function": "repository_allowed",
            "test": f"# independent task {i}" + (" changed" if i == 1 and edit_test else ""),
            "sandbox_image": IMAGE, "model": model, "port": 18089, "max_attempts": 2,
        }
        for i in range(1, 6)
    ]
    state = root / "code-state"
    report, checks = [], {}
    approvals = {task["id"]: fingerprint(task) for task in tasks}
    pin = write(root / "registry.json", {"missions": tasks, "approvals": approvals})
    for i, task in enumerate(tasks, 1):
        mid = task["id"]
        source = local_codegen._source(task)
        artifact = "def repository_allowed(repository: str) -> bool:\n    return False"
        candidate = local_codegen.replace_function(source, task["function"], artifact)
        diff = "reviewable fixture diff\n"
        receipt = {
            "artifact": artifact, "sha256": sha(artifact), "specialist_id": "tel99-dev",
            "provider": local_codegen.PROVIDER, "model": "other-model" if tamper_model and i == 1 else model,
            "generation_seconds": 0.25, "host_memory_before_mib": 8000, "host_memory_after_mib": 7950,
        }
        verified = {
            "verifier": local_codegen.VERIFIER, "artifact_sha256": sha(artifact), "ok": True,
            "base_sha": base, "path": task["path"], "function": task["function"],
            "test_sha256": sha(task["test"]), "sandbox_image": IMAGE,
            "checks": [
                {"name": "bounded-model-receipt", "ok": True},
                {"name": "approved-function-diff", "ok": True},
                {"name": "baseline-fails", "ok": True, "exit_code": 1},
                {"name": "candidate-passes", "ok": True, "exit_code": 0},
            ],
            "base_file_sha256": sha(source), "candidate_sha256": sha(candidate), "diff_sha256": sha(diff),
            "verification_seconds": 0.5,
        }
        verdict = verify_mission(conversation_finished=True, roles={"tel99-dev": {"reported": True}},
            acceptance_checks=[{"id": "independent-code-contract", "exit_code": 0,
                                "command": "isolated Docker baseline and candidate",
                                "reproducible": True, "output_digest": fingerprint(verified)}])
        checkpoint = {
            "id": mid, "project": "tel99", "status": "ACCEPTED", "execution_status": "COMPLETED",
            "contract_sha256": approvals[mid], "at": 100 + i + 3.5, "attempt": 1,
            "verification": verified, "verdict": verdict,
        }
        if repair_first and i == 1:
            previous = {**receipt, "artifact": "def repository_allowed(repository: str) -> bool:\n    return True"}
            previous["sha256"] = sha(previous["artifact"])
            rejected = {
                **verified, "ok": False, "artifact_sha256": previous["sha256"],
                "checks": [*verified["checks"][:-1], {"name": "candidate-passes", "ok": False, "exit_code": 1}],
            }
            checkpoint["attempt"] = 2
            checkpoint["attempt_history"] = [{"number": 1, "reason": "independent rejection", "verification": rejected}]
            write(state / f"{mid}.attempt-1.worker.json", previous)
        if block_first and i == 1:
            checkpoint.update(status="BLOCKED", execution_status="UNKNOWN", reason="fixture provider unavailable",
                              verification=None)
            checkpoint.pop("verdict")
            write(state / f"{mid}.attempt-1.worker.json", {"status": "BLOCKED", "reason": checkpoint["reason"]})
        else:
            write(state / f"{mid}.attempt-{checkpoint['attempt']}.worker.json", receipt)
            target = state / "verified-code" / mid / task["path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(candidate.encode())
            (state / "verified-code" / mid / "change.diff").write_bytes(diff.encode())
        write(state / "ledger" / "kilo-claims" / f"{mid}.json",
              {"contract_sha256": approvals[mid], "project": "tel99", "at": 100 + i})
        write(state / "ledger" / "kilo-local" / f"{mid}.json",
              {**checkpoint, "result": receipt if checkpoint["status"] == "ACCEPTED" else None})
        report.append({"id": mid, "status": checkpoint["status"], "dependencies": [], "unmet_dependencies": [],
                       "path": task["path"], "function": task["function"], "checkpoint": checkpoint})
        checks[mid] = checkpoint["verification"]
    phase, code = ("BLOCKED", 2) if block_first else ("COMPLETE", 0)
    write(root / "campaign.json", {"version": 1, "registry_sha256": pin, "repo": str(ROOT)})
    write(root / "status.json", {"phase": phase, "worker_exit": code, "checkout_sha": base,
                                "supervisor_pid": 12, "missions": {row["id"]: row["status"] for row in report}})
    write(root / "PREUVES.json", {"campagne": phase, "registre_sha256": pin,
                                 "checkout_sha": base, "code_sortie_superviseur": code,
                                 "pid_superviseur": 12, "preuves_missions": checks})
    write(root / "MISSIONS.json", report)
    return pin


class CompareLocalCodeTests(unittest.TestCase):
    def run_comparison(self, baseline, base_pin, candidate, candidate_pin):
        return subprocess.run(
            [sys.executable, "-B", "-m", "scripts.agents.automation.compare_local_code",
             "--baseline", str(baseline), "--baseline-sha256", base_pin,
             "--candidate", str(candidate), "--candidate-sha256", candidate_pin],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )

    def test_paired_sessions_use_claim_duration_and_actual_receipt_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = (Path(directory) / side for side in ("base", "candidate"))
            bp = completed(baseline, "baseline", "fixed-a")
            cp = completed(candidate, "candidate", "fixed-b")
            before = {p: p.read_bytes() for p in Path(directory).rglob("*") if p.is_file()}
            result = self.run_comparison(baseline, bp, candidate, cp)
            self.assertEqual(0, result.returncode, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(5, data["comparison"]["task_count"])
            self.assertEqual(17.5, data["baseline"]["claim_to_terminal_seconds"])
            self.assertEqual(1.25, data["candidate"]["generation_seconds"])
            self.assertEqual(3.75, data["candidate"]["measured_work_seconds"])
            self.assertEqual(5, data["candidate"]["first_attempt_successes"])
            self.assertIsNone(data["comparison"]["paired_metrics"]["fixed-a"]["tokens"])
            self.assertEqual(before, {p: p.read_bytes() for p in Path(directory).rglob("*") if p.is_file()})

    def test_same_path_with_different_pinned_test_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = (Path(directory) / side for side in ("base", "candidate"))
            bp = completed(baseline, "baseline", "fixed-a")
            cp = completed(candidate, "candidate", "fixed-b", edit_test=True)
            result = self.run_comparison(baseline, bp, candidate, cp)
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("same pinned cases", result.stderr)

    def test_unexpected_model_in_receipt_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = (Path(directory) / side for side in ("base", "candidate"))
            bp = completed(baseline, "baseline", "fixed-a")
            cp = completed(candidate, "candidate", "fixed-b", tamper_model=True)
            result = self.run_comparison(baseline, bp, candidate, cp)
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("receipt model", result.stderr)

    def test_independent_failure_followed_by_second_attempt_acceptance_is_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = (Path(directory) / side for side in ("base", "candidate"))
            bp = completed(baseline, "baseline", "fixed-a")
            cp = completed(candidate, "candidate", "fixed-b", repair_first=True)
            result = self.run_comparison(baseline, bp, candidate, cp)
            self.assertEqual(0, result.returncode, result.stderr)
            comparison = json.loads(result.stdout)
            self.assertEqual(4, comparison["candidate"]["first_attempt_successes"])
            self.assertEqual(1, comparison["candidate"]["second_attempt_successes"])
            self.assertEqual(1.0, comparison["candidate"]["second_attempt_success_rate"])
            self.assertEqual(1.5, comparison["candidate"]["generation_seconds"])

    def test_unattributed_provider_failure_cannot_make_a_definitive_recommendation(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = (Path(directory) / side for side in ("base", "candidate"))
            bp = completed(baseline, "baseline", "fixed-a", block_first=True)
            cp = completed(candidate, "candidate", "fixed-b")
            result = self.run_comparison(baseline, bp, candidate, cp)
            self.assertEqual(0, result.returncode, result.stderr)
            comparison = json.loads(result.stdout)
            self.assertEqual("inconclusive", comparison["comparison"]["verdict"])
            self.assertEqual(1, comparison["baseline"]["failures"])
            self.assertIsNone(comparison["baseline"]["measured_work_seconds"])

    def test_registry_pin_is_independent_of_campaign_files(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = (Path(directory) / side for side in ("base", "candidate"))
            completed(baseline, "baseline", "fixed-a")
            cp = completed(candidate, "candidate", "fixed-b")
            result = self.run_comparison(baseline, "0" * 64, candidate, cp)
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("operator pin", result.stderr)
