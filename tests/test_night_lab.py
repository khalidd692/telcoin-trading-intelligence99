import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

from scripts.agents import night_lab_20261123 as lab


ROOT = Path(__file__).resolve().parents[1]
NIGHT_LAB = ROOT / "scripts/agents/night_lab_20261123.py"


class NightLabTests(unittest.TestCase):
    def run_lab(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(NIGHT_LAB), *map(str, args)],
            cwd=ROOT, text=True, capture_output=True, timeout=10,
        )

    def test_registry_mismatch_produces_reports_without_launching_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "night"
            registry = Path(directory) / "registry.json"
            registry.write_bytes(b"{}")
            result = self.run_lab(
                "run", "--session", session, "--registry", registry,
                "--registry-sha256", "a" * 64,
            )
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertTrue((session / "status.json").is_file(), result.stderr)
            report = json.loads((session / "status.json").read_bytes())
            self.assertEqual("BLOCKED", report["phase"])
            self.assertIsNone(report["supervisor_pid"])
            self.assertIn("SHA-256", report["note"])
            self.assertFalse(list(session.glob("code-missions.*.log")))
            for name in ("MISSIONS.json", "PREUVES.json", "LIRE_AU_REVEIL.md",
                         "BLOCAGES.md", "PROCHAINES_PRIORITES.md"):
                self.assertTrue((session / name).is_file(), name)

    def test_budget_over_six_hours_does_not_create_session(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "night"
            registry = Path(directory) / "registry.json"
            digest = hashlib.sha256(b"{}").hexdigest()
            registry.write_bytes(b"{}")
            result = self.run_lab(
                "run", "--session", session, "--registry", registry,
                "--registry-sha256", digest, "--hours", 6.01,
            )
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn("--hours", result.stderr)
            self.assertFalse(session.exists())

    def test_stop_refuses_an_unrelated_evidence_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_lab("stop", "--session", directory)
            self.assertEqual(2, result.returncode)
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_abnormal_exit_rechecks_preflight_and_restarts_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            campaign = lab.Campaign(session, "a" * 64, time.monotonic() + 120)
            registry = session / "registry.json"
            registry.write_bytes(b"{}")
            with patch.object(campaign, "preflight", return_value="pwsh") as preflight:
                with patch.object(campaign, "run_worker", side_effect=[15, 16]) as worker:
                    self.assertEqual(16, campaign.execute(registry))
            self.assertEqual(2, preflight.call_count)
            self.assertEqual(2, worker.call_count)
            self.assertEqual(("pwsh", registry), worker.call_args.args)

    def test_abnormal_exit_stops_its_orphan_without_starting_another_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            campaign = lab.Campaign(session, "a" * 64, time.monotonic() + 120)
            campaign.runtime = lab.Runtime(campaign.root)
            campaign.state["supervisor_pid"] = 123
            registry = session / "registry.json"
            registry.write_bytes(b"{}")
            with patch.object(campaign, "preflight", return_value="pwsh"):
                with patch.object(campaign, "run_worker", return_value=15) as worker:
                    with patch.object(lab, "active_windows_workers", side_effect=[[123, 456], [456]]):
                        with self.assertRaises(lab.CampaignAwaiting):
                            campaign.execute(registry)
            worker.assert_called_once_with("pwsh", registry)
            self.assertTrue((campaign.root / "stop.request").is_file())

    def test_running_process_is_observed_and_stops_without_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            campaign = lab.Campaign(session, "a" * 64, time.monotonic() + 120)
            campaign.missions = [{"id": "mission-test", "dependencies": [],
                                  "path": "source.py", "function": "f"}]
            campaign.runtime = lab.Runtime(campaign.root)
            registry = session / "registry.json"
            registry.write_bytes(b"{}")
            child = """
from datetime import datetime, timezone
import json, os, sys, time
from pathlib import Path
from scripts.agents.protocol.store import FileStore
root = Path(sys.argv[1])
store = FileStore(root / 'ledger')
store.put('github/heartbeat', {'PID': os.getpid(), 'HEARTBEAT': datetime.now(timezone.utc).isoformat(), 'STATE': 'RUNNING'})
for status in ('ACK', 'RUNNING'):
    store.put('kilo-local/mission-test', {'id': 'mission-test', 'status': status})
    print(json.dumps({'mission_id': 'mission-test', 'status': status}), flush=True)
until = time.monotonic() + 5
while not (root / 'stop.request').exists():
    if time.monotonic() > until:
        sys.exit(9)
    time.sleep(.02)
sys.exit(2)
"""
            open_process = subprocess.Popen

            def start_fixture(command, **options):
                return open_process([sys.executable, "-B", "-c", child, str(campaign.root)], **options)

            def stop_when_running():
                until = time.monotonic() + 4
                while time.monotonic() < until:
                    try:
                        row = json.loads((session / "status.json").read_bytes())
                    except OSError:
                        row = {}
                    if row.get("first_mission", {}).get("RUNNING"):
                        (session / "STOP_NUIT").touch()
                        return
                    time.sleep(.02)

            stopper = Thread(target=stop_when_running)
            stopper.start()
            try:
                with patch.object(lab.subprocess, "Popen", side_effect=start_fixture):
                    with self.assertRaises(lab.CampaignStopped):
                        campaign.run_worker("pwsh", registry)
            finally:
                stopper.join()
            campaign.publish("Arrêt demandé pour cette campagne", "STOPPED")
            campaign.report()
            evidence = json.loads((session / "PREUVES.json").read_bytes())
            self.assertEqual("mission-test", evidence["premiere_mission"]["id"])
            self.assertIn("ACK", evidence["premiere_mission"])
            self.assertIn("RUNNING", evidence["premiere_mission"])
            self.assertEqual(evidence["pid_lanceur"], evidence["pid_superviseur"])
            self.assertFalse(evidence["arret_force"])
            self.assertEqual(2, evidence["code_sortie_superviseur"])
            missions = json.loads((session / "MISSIONS.json").read_bytes())
            self.assertEqual("RUNNING", missions[0]["status"])
