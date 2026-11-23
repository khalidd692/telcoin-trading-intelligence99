"""Exercise the Night Lab server against the existing local campaign ledger."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from importlib.util import find_spec
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from scripts.agents import night_lab_20261123 as lab
from scripts.agents.automation import local_code_pr
from scripts.agents.automation.autonomy_runtime import Runtime
from tests.test_github_local_code_campaign import FIRST, LocalFixture
from tests.test_local_code_pr_publisher import fixture


@contextmanager
def running_server(root, **kwargs):
    with lab.cockpit(None, 0, github_state=root, **kwargs) as server:
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join(timeout=2)


def request(port, path="/status.json", *, method="GET", body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def read_status(port):
    status, headers, body = request(port)
    if status != 200:
        raise AssertionError((status, body))
    if headers["Cache-Control"] != "no-store":
        raise AssertionError(headers)
    return json.loads(body)


def update_heartbeat(store, state, mission_id=None, *, older_than=0, phase=None):
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=older_than)
    store.put("github/heartbeat", {
        "PID": os.getpid(), "HEARTBEAT": timestamp.isoformat(),
        "STATE": state, "ACTIVE_TASK": mission_id, "PHASE": phase,
    })


class GitHubCockpitTests(unittest.TestCase):
    def test_empty_source_is_waiting_and_creates_no_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "next-campaign"
            with running_server(root) as port:
                self.assertEqual(200, request(port, "/")[0])
                data = read_status(port)
            self.assertEqual("WAITING", data["supervisor"]["status"])
            self.assertEqual("unavailable", data["supervisor"]["freshness"])
            self.assertEqual(12, len(data["roles"]))
            self.assertEqual([], data["missions"])
            self.assertFalse(root.exists())

    def test_running_phase_is_live_but_individual_roles_require_direct_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = Runtime(root)
            scenario = LocalFixture()
            scenario.handoff(runtime).source()
            first, second = scenario.missions
            with running_server(root) as port:
                runtime.save(first, "RUNNING", attempt=1)
                update_heartbeat(runtime.store, "RUNNING", first["id"], phase="WORKER")
                data = read_status(port)
                self.assertEqual("ACTIVE", data["supervisor"]["status"])
                self.assertEqual("WORKER", data["missions"][0]["stage"])
                self.assertEqual("ACTIVE", data["missions"][0]["status"])
                self.assertEqual("WAITING", data["missions"][1]["status"])
                self.assertEqual([first["id"]], data["missions"][1]["dependencies"])
                self.assertFalse(any(role["status"] == "ACTIVE" for role in data["roles"]))

                runtime.save(first, "WORKER_EXITED", attempt=1)
                update_heartbeat(runtime.store, "WORKER_EXITED", first["id"], phase="VERIFICATION")
                data = read_status(port)
                verifier = next(role for role in data["roles"] if role["id"] == "tel99-verifier")
                self.assertEqual("ACTIVE", verifier["status"])
                self.assertEqual("DETERMINISTIC", verifier["engine"])

                update_heartbeat(runtime.store, "WORKER_EXITED", first["id"],
                                 phase="VERIFICATION", older_than=31)
                data = read_status(port)
                self.assertEqual("stale", data["supervisor"]["freshness"])
                self.assertEqual("VERIFICATION_PENDING", data["missions"][0]["stage"])
                self.assertFalse(any(role["status"] == "ACTIVE" for role in data["roles"]))

                runtime.save(first, "RUNNING", attempt=1)
                update_heartbeat(runtime.store, "RUNNING", first["id"], phase="WORKER", older_than=31)
                data = read_status(port)
                self.assertEqual("BLOCKED", data["missions"][0]["status"])
                self.assertEqual("RECONCILIATION", data["missions"][0]["stage"])

    def test_completed_mission_projects_correlated_github_and_docker_proofs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store, state, evidence, api, source = fixture(root)
            scenario = LocalFixture()
            mission_id = state["id"]
            config = store.get("github-local-code/config")
            store.put("github-local-code/config", {**config, "mandate_id": 4001,
                                                   "mandate_sha256": scenario.pin})
            store.put("runtime-config/transport", "github-local-code")
            approval = store.get(f"kilo-github/approvals/{mission_id}")
            store.put(f"kilo-github/approvals/{mission_id}", {**approval, "comment_id": 5241})
            state = {**state, "at": datetime.now(timezone.utc).timestamp(),
                     "reason": "secret=never-display-this", "attempt": 1}
            store.put(f"kilo-local/{mission_id}", state)
            with patch.object(local_code_pr.local_codegen, "_source", return_value=source):
                pr = local_code_pr.publish_verified_code_pr(
                    local_code_pr.REPO, FIRST, local_code_pr.BASE_REF, local_code_pr.BASE_SHA,
                    state, evidence, api=api, store=store, root=root,
                )
            self.assertEqual(f"https://github.com/{local_code_pr.REPO}/pull/805", pr)
            prefix = f"https://github.com/{local_code_pr.REPO}/issues/{FIRST}#issuecomment-"
            for phase, url in (("ACK", prefix + "8999"), ("RESULT", prefix + "9002")):
                event = {**store.get(f"kilo-github/outbox/{mission_id}/EVIDENCE")["event"],
                         "phase": phase, "status": "ACK" if phase == "ACK" else "ACCEPTED"}
                if phase == "RESULT":
                    event.update(pull_request_url=pr, evidence_url=evidence)
                store.put(f"kilo-github/outbox/{mission_id}/{phase}", {"event": event, "url": url})
            update_heartbeat(store, "STOPPED")
            before = {str(path.relative_to(root)): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            with running_server(root) as port:
                data = read_status(port)
                row = data["missions"][0]
                self.assertEqual("ACCEPTED", row["status"])
                self.assertEqual("COMPLETE", row["stage"])
                self.assertEqual(pr, row["pull_request"])
                self.assertEqual(4, len(row["checks"]))
                self.assertEqual(3, len(row["handoffs"]))
                self.assertEqual("STOPPED", data["supervisor"]["status"])
                raw = request(port)[2]
                self.assertNotIn(b"never-display-this", raw)
                self.assertNotIn(b"Keep the env tuple shape", raw)
                self.assertNotIn(b"return ('ready', 'token')", raw)
                self.assertEqual(403, request(port, headers={"Host": "outside.example"})[0])
            after = {str(path.relative_to(root)): path.read_bytes()
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_stop_requires_opt_in_origin_code_and_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = Runtime(root)
            scenario = LocalFixture()
            scenario.handoff(runtime).source()
            update_heartbeat(runtime.store, "IDLE")
            input_data = json.dumps({"code": "local-test-code", "confirm": True})
            with running_server(root) as port:
                self.assertEqual(405, request(port, "/actions/stop", method="POST",
                                              body=input_data)[0])
            with running_server(root, stop_code="local-test-code") as port:
                headers = {"Origin": f"http://127.0.0.1:{port}",
                           "Content-Type": "application/json"}
                spoofed = {**headers, "Origin": "https://outside.example"}
                self.assertEqual(403, request(port, "/actions/stop", method="POST",
                                              body=input_data, headers=spoofed)[0])
                for invalid in ({"code": "wrong", "confirm": True},
                                {"code": "local-test-code", "confirm": False}):
                    self.assertEqual(403, request(port, "/actions/stop", method="POST",
                                                  body=json.dumps(invalid), headers=headers)[0])
                self.assertFalse((root / "stop.request").exists())
                self.assertNotIn(b"local-test-code", request(port)[2])
                self.assertEqual(202, request(port, "/actions/stop", method="POST",
                                              body=input_data, headers=headers)[0])
                self.assertTrue((root / "stop.request").is_file())
                self.assertEqual("STOP_REQUESTED", read_status(port)["supervisor"]["stage"])

    def test_cockpit_rejects_invalid_campaign_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = Runtime(root)
            runtime.store.put("github-local-code/config", {"profile": "wrong-profile"})
            with running_server(root) as port:
                status, _, body = request(port)
                self.assertEqual(503, status)
                self.assertNotIn(b"wrong-profile", body)

    @unittest.skipUnless(shutil.which("chromium") and find_spec("playwright"), "Chromium + Playwright unavailable")
    def test_browser_refresh_role_details_and_confirmed_stop_on_mobile(self):
        from playwright.sync_api import expect, sync_playwright

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = Runtime(root)
            scenario = LocalFixture()
            scenario.handoff(runtime).source()
            first = scenario.missions[0]
            update_heartbeat(runtime.store, "IDLE")
            with running_server(root, stop_code="local-browser-code") as port, sync_playwright() as playwright:
                with playwright.chromium.launch(executable_path=shutil.which("chromium")) as browser:
                    page = browser.new_page(viewport={"width": 390, "height": 844})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{port}/")
                    expect(page.locator(".mission")).to_have_count(2)
                    expect(page.locator("#roles button")).to_have_count(12)
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    page.get_by_text("Checkpoint, tests et transmissions").first.click()
                    expect(page.get_by_text("Fichier approuvé").first).to_be_visible()
                    page.get_by_role("button", name="Vérification").click()
                    expect(page.get_by_role("dialog")).to_be_visible()
                    expect(page.get_by_text("Déterministe", exact=True)).to_be_visible()
                    page.get_by_role("button", name="Fermer").click()

                    runtime.save(first, "RUNNING", attempt=1)
                    update_heartbeat(runtime.store, "RUNNING", first["id"], phase="WORKER")
                    expect(page.locator("#supervisor-status")).to_have_text("ACTIF", timeout=6500)
                    expect(page.locator("#active-roles")).to_have_text("0")
                    expect(page.get_by_text("Fichier approuvé").first).to_be_visible()

                    page.get_by_role("button", name="Demander un arrêt propre").click()
                    page.get_by_role("button", name="Confirmer l’arrêt").click()
                    expect(page.get_by_text("Saisir le code et cocher la confirmation.")).to_be_visible()
                    page.get_by_label("Code de contrôle").fill("local-browser-code")
                    page.get_by_label("Je confirme la demande d’arrêt.").check()
                    page.get_by_role("button", name="Confirmer l’arrêt").click()
                    expect(page.get_by_role("dialog")).not_to_be_visible()
                    expect(page.locator("#supervisor-stage")).to_have_text("Arrêt demandé")
                    self.assertTrue((root / "stop.request").is_file())
                    self.assertEqual([], errors)
