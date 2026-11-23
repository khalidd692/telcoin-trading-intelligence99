import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from scripts.agents.automation.autonomy_runtime import Runtime, seal


ROOT = Path(__file__).resolve().parents[1]
TARGET = "docs/agents/autonomy-demo/tasks.py"
TEST = '''import json, subprocess, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(dir="/scratch") as directory:
    db = Path(directory) / "tasks.json"
    db.write_text(json.dumps([{"id": "ok", "title": "old", "done": False}]), encoding="utf-8")
    edited = subprocess.run([sys.executable, "-I", "-B", "/work/program.py", "--db", str(db),
                             "edit", "OK", "new"], capture_output=True, text=True, timeout=5)
    assert edited.returncode == 0, "fixture-only assertion diagnostic"  # case: mixed-case-id | expected: mixed-case identifiers must match
    assert json.loads(edited.stdout)["title"] == "new"
    assert json.loads(db.read_text(encoding="utf-8"))[0]["title"] == "new"
'''
REJECTED = '''def find_task_index(tasks: list[dict], task_id: str) -> int | None:
    candidate_lookup = "fixture-private-literal"  # fixture-private-comment
    for i, task in enumerate(tasks):
        if candidate_lookup == task.get("id"):
            return i
    return None
'''
CORRECTED = '''def find_task_index(tasks: list[dict], task_id: str) -> int | None:
    for i, task in enumerate(tasks):
        task_key = task.get("id") if isinstance(task, dict) else None
        if isinstance(task_key, str) and task_key.casefold() == task_id.casefold():
            return i
    return None
'''


class LocalCodeRepairEndToEndTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TEL99_TEST_SANDBOX_IMAGE"),
                         "requires a local Docker image pinned by digest")
    def test_real_worker_repairs_verified_failure_and_replay_skips_model(self):
        replies = (REJECTED, CORRECTED)
        requests = []

        class CompletionEndpoint(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/v1/chat/completions":
                    self.send_error(404)
                    return
                index = len(requests)
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                if index >= len(replies):
                    self.send_error(503)
                    return
                payload = json.dumps({"choices": [{"message": {"content": replies[index]}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        base_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
        with HTTPServer(("127.0.0.1", 0), CompletionEndpoint) as server, tempfile.TemporaryDirectory() as directory:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                mission = {
                    "id": "repair-feedback-e2e", "owner": "local", "project": "tel99",
                    "specialist": "tel99-dev", "priority": "P0", "dependencies": [],
                    "objective": "Make edit lookup accept identifiers with different letter case.",
                    "base_sha": base_sha, "path": TARGET, "function": "find_task_index", "test": TEST,
                    "sandbox_image": os.environ["TEL99_TEST_SANDBOX_IMAGE"], "model": "repair-test-model",
                    "port": server.server_port, "max_attempts": 2,
                }
                approvals = seal([mission])
                runtime = Runtime(Path(directory))
                runtime.run_queue([mission], approvals)
                saved = runtime.state(mission)
                self.assertEqual(saved["status"], "ACCEPTED", saved)
                self.assertEqual(saved["attempt"], 2)

                first_digest = hashlib.sha256(REJECTED.encode()).hexdigest()
                [failed] = saved["attempt_history"]
                self.assertEqual(failed["number"], 1)
                self.assertEqual(failed["verification"]["artifact_sha256"], first_digest)
                before = {row["name"]: row for row in failed["verification"]["checks"]}
                after = {row["name"]: row for row in saved["verification"]["checks"]}
                self.assertEqual(before["baseline-fails"]["exit_code"], 1)
                self.assertEqual(before["candidate-passes"]["exit_code"], 1)
                self.assertEqual(after["baseline-fails"]["exit_code"], 1)
                self.assertEqual(after["candidate-passes"]["exit_code"], 0)
                proofs = Path(directory) / "verified-code" / mission["id"]
                self.assertIn(CORRECTED, (proofs / TARGET).read_text(encoding="utf-8"))
                self.assertTrue((proofs / "change.diff").is_file())

                self.assertEqual(len(requests), 2)
                first_prompt, repair_prompt = [request["messages"][-1]["content"] for request in requests]
                self.assertNotIn("Previous candidate", first_prompt)
                self.assertIn("Previous candidate (redacted", repair_prompt)
                self.assertIn(first_digest, repair_prompt)
                self.assertIn("mixed-case-id", repair_prompt)
                self.assertIn("mixed-case identifiers must match", repair_prompt)
                self.assertIn("assertion failed", repair_prompt.lower())
                self.assertRegex(repair_prompt, r"(?m)^\s*(_name_\d+)\s*=\s*'<redacted>'[^\n]*\n"
                                                 r"\s*for [^\n]+\n\s*if \1\b")
                self.assertNotIn("candidate_lookup", repair_prompt)
                self.assertNotIn("fixture-private-literal", repair_prompt)
                self.assertNotIn("fixture-private-comment", repair_prompt)
                self.assertNotIn("fixture-only assertion diagnostic", repair_prompt)

                resumed = Runtime(Path(directory))
                resumed.run_queue([mission], approvals)
                self.assertEqual(resumed.state(mission), saved)
                self.assertEqual(len(requests), 2)
            finally:
                server.shutdown()
                thread.join(timeout=5)
