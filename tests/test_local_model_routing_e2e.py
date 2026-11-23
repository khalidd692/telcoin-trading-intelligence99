from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.agents.automation.autonomy_runtime import Runtime, seal
from scripts.agents.automation import local_model_routing
from tests.test_local_codegen_repair_e2e import CORRECTED, REJECTED, TARGET, TEST


ROOT = Path(__file__).resolve().parents[1]
SMALL_MODEL = "qwen2.5-3b-instruct"
LARGE_MODEL = "qwen2.5-coder-7b-instruct"
SAVE_TEST = '''import json, subprocess, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(dir="/scratch") as directory:
    db = Path(directory) / "new" / "tasks.json"
    added = subprocess.run([sys.executable, "-I", "-B", "/work/program.py", "--db", str(db),
                            "add", "Nouvelle tâche"], capture_output=True, text=True, timeout=5)
    assert added.returncode == 0  # case: nested-save | expected: Create the missing parent directory.
    assert json.loads(db.read_text(encoding="utf-8"))[0]["title"] == "Nouvelle tâche"
'''
SAVE_REPLY = '''def save_tasks(db_path: str, tasks: list[dict]) -> None:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)
'''
GIT_CHANGES_REPLY = r'''def git_changes(output):
    counts = {"staged": 0, "unstaged": 0, "untracked": 0, "conflicts": 0}
    fields = iter(output.split("\0"))
    for row in fields:
        if not row:
            continue
        if not re.match(r"^[ MTADRCU?]{2} ", row):
            return None
        index, worktree = row[:2]
        if (index in "RC" or worktree in "RC") and not next(fields, ""):
            return None
        if index + worktree == "??":
            counts["untracked"] += 1
        elif index + worktree in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}:
            counts["conflicts"] += 1
        else:
            counts["staged"] += index != " "
            counts["unstaged"] += worktree != " "
    return counts
'''


@contextmanager
def completion_endpoint(model, replies):
    requests = []

    class Endpoint(BaseHTTPRequestHandler):
        advertised_model = model

        def do_GET(self):
            if self.path == "/health":
                self.reply({"status": "ok"})
            elif self.path == "/v1/models":
                self.reply({"data": [{"id": self.advertised_model}]})
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            index = len(requests)
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            if index >= len(replies) or request.get("model") != model:
                self.send_error(503)
                return
            self.reply({"choices": [{"message": {"content": replies[index]}}]})

        def reply(self, data):
            payload = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    with HTTPServer(("127.0.0.1", 0), Endpoint) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port, requests, Endpoint
        finally:
            server.shutdown()
            thread.join(timeout=5)


class LocalModelRoutingEndToEndTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TEL99_TEST_SANDBOX_IMAGE"),
                         "requires a local Docker image pinned by digest")
    def test_scoped_worker_routes_real_docker_checks_and_keeps_retry_on_same_model(self):
        available = local_model_routing.available_memory_mib()
        if available is None or available < local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB:
            self.skipTest("requires an observable host memory reserve for local routing")

        registry = ROOT / "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
        [diagnostic] = [item for item in json.loads(registry.read_bytes())["missions"]
                        if item["function"] == "git_changes"]

        with (completion_endpoint(SMALL_MODEL, [SAVE_REPLY, REJECTED, CORRECTED]) as small,
              completion_endpoint(LARGE_MODEL, [GIT_CHANGES_REPLY]) as large,
              tempfile.TemporaryDirectory() as directory):
            small_port, small_requests, _ = small
            large_port, large_requests, large_endpoint = large
            small_binding = {"id": "local/llama-qwen2.5-3b", "model": SMALL_MODEL, "port": small_port}
            large_binding = {"id": "local/llama-qwen2.5-coder-7b", "model": LARGE_MODEL, "port": large_port}
            shared = {
                "owner": "local", "project": "tel99", "specialist": "tel99-dev", "dependencies": [],
                "base_sha": diagnostic["base_sha"], "max_attempts": 2,
                "sandbox_image": os.environ["TEL99_TEST_SANDBOX_IMAGE"],
                "routing": {"candidates": [small_binding, large_binding]},
            }
            easy = {
                **shared, "id": "routing-e2e-easy", "priority": "P0", "path": TARGET,
                "function": "save_tasks", "objective": "Save tasks to a new nested database path.",
                "test": SAVE_TEST,
            }
            medium = {
                **shared, "id": "routing-e2e-medium", "priority": "P1", "path": TARGET,
                "function": "find_task_index", "objective": "Accept identifiers with different letter case.",
                "test": TEST,
            }
            hard = {
                **shared, "id": "routing-e2e-hard", "priority": "P2", "path": diagnostic["path"],
                "function": diagnostic["function"], "objective": diagnostic["objective"],
                "test": diagnostic["test"],
            }
            missions = [easy, medium, hard]
            approvals = seal(missions)
            root = Path(directory)
            runtime = Runtime(root)
            runtime.run_queue(missions, approvals)

            checkpoints = []
            for mission, binding, difficulty, attempt in (
                    (easy, small_binding, "easy", 1), (medium, small_binding, "medium", 2),
                    (hard, large_binding, "hard", 1)):
                with self.subTest(mission=mission["id"]):
                    saved = runtime.state(mission)
                    self.assertEqual(saved.get("status"), "ACCEPTED", saved)
                    self.assertEqual(saved["attempt"], attempt)
                    self.assertEqual(saved["model_route"]["selection"], binding)
                    self.assertEqual(saved["model_route"]["decision"]["difficulty"], difficulty)
                    self.assertEqual(saved["verification"]["model"], binding["model"])
                    checks = {row["name"]: row["exit_code"] for row in saved["verification"]["checks"]
                              if "exit_code" in row}
                    self.assertEqual(checks, {"baseline-fails": 1, "candidate-passes": 0})
                    self.assertTrue((root / "verified-code" / mission["id"] / "change.diff").is_file())
                    checkpoints.append(saved)

            [first_medium] = checkpoints[1]["attempt_history"]
            self.assertEqual(first_medium["verification"]["model"], SMALL_MODEL)
            failed = {row["name"]: row["exit_code"] for row in first_medium["verification"]["checks"]
                      if "exit_code" in row}
            self.assertEqual(failed, {"baseline-fails": 1, "candidate-passes": 1})
            self.assertEqual([request["model"] for request in small_requests], [SMALL_MODEL] * 3)
            self.assertEqual([request["model"] for request in large_requests], [LARGE_MODEL])
            self.assertIn("mixed-case identifiers must match", small_requests[2]["messages"][-1]["content"])

            resumed = Runtime(root)
            resumed.run_queue(missions, approvals)
            self.assertEqual([resumed.state(mission) for mission in missions], checkpoints)

            large_endpoint.advertised_model = "unexpected-model"
            unavailable = {**hard, "id": "routing-e2e-unavailable"}
            resumed.run_queue([unavailable], seal([unavailable]))
            blocked = resumed.state(unavailable)
            self.assertEqual(blocked["status"], "BLOCKED", blocked)
            self.assertIsNone(blocked["model_route"]["selection"])
            self.assertEqual((len(small_requests), len(large_requests)), (3, 1))
