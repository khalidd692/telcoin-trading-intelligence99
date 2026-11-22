import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import windows_diagnostic as diagnostic


REPO = "khalidd692/telcoin-trading-intelligence99"
PRIVATE = "private-test-value"


class DiagnosticTests(unittest.TestCase):
    def run_diagnostic(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = diagnostic.main(list(args))
        self.assertNotIn(PRIVATE, output.getvalue())
        self.assertEqual(code, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "BLOCKED")
        return report

    def test_local_default_does_not_initialize_state_or_call_github(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(diagnostic, "github_get") as github:
            state = Path(tmp, PRIVATE, "kept-absent")
            report = self.run_diagnostic("--state", str(state))
            github.assert_not_called()
            self.assertFalse(state.parent.exists())
        self.assertEqual(report["state"]["directory"], "ABSENT")
        self.assertEqual(report["github"]["status"], "NOT_REQUESTED")
        self.assertEqual(report["kilo"]["agent_manager_sessions"], "WINDOWS_PENDING")
        self.assertEqual(report["hermes"]["runtime_status"], "WINDOWS_PENDING")
        self.assertEqual(report["openhands"]["connection"], "WINDOWS_PENDING")
        self.assertRegex(report["timestamp_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")

    def test_existing_stop_is_observed_without_creating_locks(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            marker = state / "stop.request"
            marker.write_bytes(PRIVATE.encode())
            heartbeat = state / "ledger" / "github" / "heartbeat.json"
            heartbeat.parent.mkdir(parents=True)
            heartbeat.write_text(json.dumps({"STATE": "ACCEPTED", "QUOTA": PRIVATE}), encoding="utf-8")
            before = sorted(state.rglob("*"))
            report = self.run_diagnostic("--state", str(state))
            self.assertEqual(sorted(state.rglob("*")), before)
            self.assertEqual(marker.read_bytes(), PRIVATE.encode())
        self.assertEqual(report["state"]["stop_request"], "PRESENT")
        self.assertEqual(report["state"]["heartbeat_file"], "PRESENT")
        self.assertNotIn("ACCEPTED", json.dumps(report))

    @unittest.skipUnless(shutil.which("git"), "git required for worktree probe")
    def test_git_counts_nul_records_without_exposing_names_or_touching_index(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=tree, capture_output=True, check=True)

        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            git("init", "--quiet")
            file = tree / "tracked.txt"
            file.write_text("tracked\n", encoding="utf-8")
            git("add", file.name)
            git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
            git("mv", file.name, PRIVATE + ".txt")
            file.write_text("untracked\n", encoding="utf-8")
            index = tree / ".git" / "index"
            before = index.stat().st_mtime_ns, index.read_bytes()
            report = diagnostic.worktree_status(tree)
            self.assertEqual((index.stat().st_mtime_ns, index.read_bytes()), before)
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["changes"], {"staged": 1, "unstaged": 0, "untracked": 1, "conflicts": 0})
        self.assertNotIn(PRIVATE, json.dumps(report))

    def test_kilo_help_discloses_only_known_flags_without_claiming_a_session(self):
        def local_probe(argv, *_):
            if argv[1:] == ["--version"] and Path(argv[0]).stem == "kilo":
                return f"7.8.27\n{PRIVATE}"
            if argv[1:] == ["run", "--help"] and Path(argv[0]).stem == "kilo":
                return ("kilo run [message..]\nOptions:\n  --session   session ID\n"
                        f"  --agent    {PRIVATE}\n  --{PRIVATE}   private option\n")
            return None

        with tempfile.TemporaryDirectory() as tmp, patch.object(diagnostic, "local_probe", side_effect=local_probe), \
                patch.object(diagnostic.shutil, "which", return_value="kilo"):
            report = self.run_diagnostic("--state", tmp)
        self.assertEqual(report["versions"]["kilo"]["version"], "7.8.27")
        self.assertEqual(report["kilo"]["run_help"]["flags"], ["--agent", "--session"])
        self.assertEqual(report["kilo"]["agent_manager_sessions"], "WINDOWS_PENDING")

    def test_github_reads_use_pinned_preflight_and_publish_only_fixed_fields(self):
        from tests.test_kilo_github_handoff import GitHub, ISSUE, MANDATE, OWNER

        fixture = GitHub()
        endpoints = []

        def get(endpoint):
            endpoints.append(endpoint)
            if endpoint == "user":
                return {**OWNER, "email": PRIVATE}
            if endpoint == f"repos/{REPO}":
                return {"permissions": {"pull": True, "push": False, "other": PRIVATE}}
            if endpoint == "rate_limit":
                return {"resources": {"core": {"limit": 5000, "remaining": 4999, "reset": 1800000000,
                                               "arbitrary": PRIVATE}}}
            return fixture.fetch(endpoint)

        with tempfile.TemporaryDirectory() as tmp, patch.object(diagnostic, "github_get", side_effect=get):
            report = self.run_diagnostic("--state", tmp, "--issue", str(ISSUE), "--mandate-comment", str(MANDATE),
                                         "--mandate-sha256", fixture.pin)
        self.assertEqual(report["github"]["identity"]["status"], "PINNED_OWNER")
        self.assertEqual(report["github"]["permissions"], {"pull": True, "push": False})
        self.assertEqual(report["github"]["core_rate_limit"], {"limit": 5000, "remaining": 4999, "reset": 1800000000})
        self.assertEqual(report["github"]["mandate"]["status"], "WAITING_APPROVALS")
        self.assertEqual(set(endpoints), {"user", "rate_limit", f"repos/{REPO}",
                         f"repos/{REPO}/issues/{ISSUE}", f"repos/{REPO}/issues/comments/{MANDATE}",
                         f"repos/{REPO}/issues/{ISSUE}/comments?per_page=100&page=1"})

    def test_invalid_pin_is_blocked_without_remote_detail(self):
        from tests.test_kilo_github_handoff import GitHub, ISSUE, MANDATE, OWNER

        fixture = GitHub()

        def get(endpoint):
            if endpoint == "user":
                return OWNER
            if endpoint in {"rate_limit", f"repos/{REPO}"}:
                raise OSError(PRIVATE)
            return fixture.fetch(endpoint)

        with tempfile.TemporaryDirectory() as tmp, patch.object(diagnostic, "github_get", side_effect=get):
            report = self.run_diagnostic("--state", tmp, "--issue", str(ISSUE), "--mandate-comment", str(MANDATE),
                                         "--mandate-sha256", "1" * 64)
        self.assertEqual(report["github"]["mandate"]["status"], "BLOCKED")
        self.assertIsNone(report["github"]["permissions"])

    def test_malformed_approval_is_excluded_without_traceback(self):
        from tests.test_kilo_github_handoff import GitHub, ISSUE, MANDATE, OWNER, mission

        fixture = GitHub()
        fixture.approve(mission(), origin=[PRIVATE])

        def get(endpoint):
            if endpoint == "user":
                return OWNER
            if endpoint in {"rate_limit", f"repos/{REPO}"}:
                return {}
            return fixture.fetch(endpoint)

        with tempfile.TemporaryDirectory() as tmp, patch.object(diagnostic, "github_get", side_effect=get):
            report = self.run_diagnostic("--state", tmp, "--issue", str(ISSUE), "--mandate-comment", str(MANDATE),
                                         "--mandate-sha256", fixture.pin)
        self.assertEqual(report["github"]["mandate"]["status"], "WAITING_APPROVALS")
        self.assertEqual(report["github"]["mandate"]["approved_count"], 0)


if __name__ == "__main__":
    unittest.main()
