"""Offline tests for two independently pinned TEL99 GitHub controllers.

No network, Ollama, Docker or GitHub writes. The real subprocess test exercises
a killed RUNNING worker and durable fail-closed recovery.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import github_multi_mandate_session as multi
from scripts.agents.automation import github_local_code_campaign as campaign
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from tests.test_autonomy_runtime import mission
from tests.test_github_local_code_campaign import LocalFixture, OWNER, TIMES, EXPIRY, block, comment


def spec(issue):
    return {
        "issue": issue, "mandate_comment": 50000 + issue,
        "mandate_sha256": "a" * 64,
        "base_ref": "agents/tel99-code-base-recipe-20261123",
        "base_sha": "b" * 40,
    }


def write_manifest(root, entries):
    p = root / "manifest.json"
    p.write_text(json.dumps({"version": 1, "campaigns": entries}), encoding="utf-8")
    return p


class FakeCampaign:
    def __init__(self, info, state, counts, *, ready=True):
        self.info, self.state, self.counts = info, state, counts
        self.ready = ready
        self.github_rate_limited = False

    def check_github_identity(self):
        return None

    def preflight(self):
        return [{"id": "a"}, {"id": "b"}] if self.ready else []

    def check_mandate(self):
        return {"contracts": {"a": "x", "b": "y"}}

    def complete(self):
        return self.state.get(self.info["issue"], False)

    def poll(self):
        issue = self.info["issue"]
        self.counts.append(issue)
        self.state[issue] = True
        return True


class MultiMandateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_historical_or_duplicate_controller_refused(self):
        for entries in ([spec(178)], [spec(201), spec(201)], []):
            file = write_manifest(self.root, entries)
            with self.assertRaises(ValueError):
                multi.load_manifest(file)

    def test_malformed_pins_and_excess_controllers_refused(self):
        for entries in ([{**spec(201), "mandate_sha256": "0"}],
                        [{**spec(201), "base_ref": "main"}],
                        [spec(i) for i in range(200, 211)]):
            with self.assertRaises(ValueError):
                multi.load_manifest(write_manifest(self.root, entries))

    def test_two_distinct_controllers_in_one_session_without_replay(self):
        manifest = write_manifest(self.root, [spec(201), spec(202)])
        calls, done = [], {}
        def build(info, root, deadline):
            return FakeCampaign(info, done, calls)
        summary = multi.run_campaigns(manifest, self.root / "ledger",
                                      seconds=1, once=True, build=build)
        self.assertEqual(summary, {201: True, 202: True})
        self.assertEqual(calls, [201, 202])
        multi.run_campaigns(manifest, self.root / "ledger",
                            seconds=1, once=True, build=build)
        self.assertEqual(calls, [201, 202])

    def test_new_approved_controller_discovered_without_restart(self):
        manifest = write_manifest(self.root, [spec(201)])
        calls, done, ticks = [], {}, []
        def build(info, root, deadline):
            return FakeCampaign(info, done, calls)
        def sleep(_):
            ticks.append(1)
            if len(ticks) == 1:
                write_manifest(self.root, [spec(201), spec(202)])
            time.sleep(_)
        summary = multi.run_campaigns(
            manifest, self.root / "ledger", seconds=2,
            poll_interval=1, build=build, sleep=sleep)
        self.assertEqual(calls, [201, 202])
        self.assertEqual(summary, {201: True, 202: True})

    def test_second_mandate_requires_approval_before_first_worker(self):
        manifest = write_manifest(self.root, [spec(201), spec(202)])
        calls, done = [], {}
        def build(info, root, deadline):
            return FakeCampaign(info, done, calls, ready=info["issue"] == 201)
        with self.assertRaisesRegex(multi.Blocked, "lacks signed approvals"):
            multi.run_campaigns(manifest, self.root / "ledger",
                                seconds=1, once=True, build=build)
        self.assertEqual(calls, [])

    def test_two_distinct_real_owner_pinned_mandates_validate(self):
        """Use the genuine LocalCodeCampaign preflight, not a fake approval parser."""
        def fixture_for(controller):
            f = LocalFixture()
            issues = [controller + 1, controller + 2]
            mids = [f"controller-{controller}-a", f"controller-{controller}-b"]
            originals = f.missions
            a = {**originals[0], "id": mids[0]}
            b = {**originals[1], "id": mids[1], "dependencies": [mids[0]]}
            f.missions = (a, b)
            f.scope["issue"] = controller
            f.scope["contracts"] = {m["id"]: campaign.fingerprint(m) for m in f.missions}
            cid = 50000 + controller
            f.mandate = comment(cid, controller, block(campaign.MANDATE, f.scope), TIMES[0])
            f.pin = hashlib.sha256(f.mandate["body"].encode()).hexdigest()
            f.controller = {"number": controller, "state": "open", "user": OWNER.copy()}
            f.issues = {}
            f.comments = []
            for n, m in zip(issues, f.missions):
                f.issues[n] = {"number": n, "state": "open", "user": OWNER.copy(),
                               "labels": [{"name": campaign.CODE_LABEL}],
                               "created_at": TIMES[1], "body": f"tel99-code-campaign: {cid}"}
                approval = {"approver": "khalidd692", "origin": "owner-direct",
                            "mandate_comment_id": cid, "issue": n,
                            "mission_sha256": campaign.fingerprint(m), "expires_at": EXPIRY}
                f.comments.append(comment(80000 + n, n,
                    block(campaign.APPROVAL, {"mission": m, "approval": approval}), TIMES[2]))

            def fetch(endpoint):
                prefix = f"repos/{campaign.REPO}/"
                self.assertTrue(endpoint.startswith(prefix))
                endpoint = endpoint[len(prefix):]
                if endpoint == f"issues/{controller}":
                    return f.controller
                if endpoint == f"issues/comments/{cid}":
                    return f.mandate
                if endpoint == f"git/ref/heads/{f.scope['base']}":
                    return {"object": {"sha": f.scope["base_sha"], "type": "commit"}}
                if endpoint.startswith("issues?"):
                    return [f.controller, *f.issues.values()]
                if endpoint.startswith("issues/") and "/comments" in endpoint:
                    number = int(endpoint.split("/")[1])
                    return [r for r in f.comments if r["issue_url"].endswith(f"/issues/{number}")]
                if endpoint.startswith("issues/"):
                    return f.issues[int(endpoint.split("/")[1])]
                raise AssertionError(f"unexpected GitHub endpoint: {endpoint}")
            return f, fetch

        a, fa = fixture_for(250)
        b, fb = fixture_for(260)
        manifest = write_manifest(self.root, [
            {**spec(250), "mandate_comment": a.mandate["id"],
             "mandate_sha256": a.pin,
             "base_ref": a.scope["base"], "base_sha": a.scope["base_sha"]},
            {**spec(260), "mandate_comment": b.mandate["id"],
             "mandate_sha256": b.pin,
             "base_ref": b.scope["base"], "base_sha": b.scope["base_sha"]},
        ])
        remote = {250: fa, 260: fb}
        def build(info, root, deadline):
            return campaign.LocalCodeCampaign(
                None, info["issue"], info["mandate_comment"],
                info["mandate_sha256"], fetcher=remote[info["issue"]],
                base_ref=info["base_ref"], base_sha=info["base_sha"])
        with patch.object(campaign.LocalCodeCampaign, "check_github_identity", return_value=None):
            handlers = multi.preflight_campaigns(
                multi.load_manifest(manifest), self.root, None, build=build)
        self.assertEqual(len(handlers), 2)
        self.assertEqual([len(c.preflight()) for c in handlers], [2, 2])


    def test_stop_propagates_into_controller_ledgers(self):
        root = self.root / "state"
        for num in (201, 202):
            (root / f"campaign-{num}").mkdir(parents=True, exist_ok=True)
        with patch.object(multi, "LEGACY_STOP", self.root / "unused-global-stop"):
            self.assertEqual(multi.main(["stop", "--state", str(root)]), 0)
            self.assertTrue((root / "stop.request").exists())
            self.assertTrue((root / "campaign-201" / "stop.request").exists())
            self.assertTrue((root / "campaign-202" / "stop.request").exists())

    def test_global_emergency_stop_prevents_dispatch(self):
        manifest = write_manifest(self.root, [spec(201)])
        calls = []
        stop = self.root / "global-stop"
        stop.touch()
        with patch.object(multi, "LEGACY_STOP", stop):
            self.assertEqual(
                multi.main(["run", "--state", str(self.root / "state"),
                            "--manifest", str(manifest), "--once"]), 2)
            result = multi.run_campaigns(
                manifest, self.root / "state", seconds=1, once=True,
                build=lambda info, root, deadline: calls.append(info))
        self.assertEqual(calls, [])
        self.assertEqual(result, {})


class AbruptCrashTests(unittest.TestCase):
    def test_killed_running_worker_is_not_reexecuted(self):
        """Kill the whole Python process inside an executor, then start a fresh Runtime."""
        with tempfile.TemporaryDirectory() as tmp:
            script = (
                "import os,sys\n"
                "from scripts.agents.automation.autonomy_runtime import Runtime,seal\n"
                "from tests.test_autonomy_runtime import mission\n"
                "m=mission('CRASH-A')\n"
                "Runtime(sys.argv[1],executor=lambda m: os._exit(55))"
                ".run_queue([m],seal([m]))\n"
            )
            proc = subprocess.run(
                [sys.executable, "-B", "-c", script, tmp],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=25, check=False,
            )
            self.assertEqual(proc.returncode, 55, proc.stderr.decode(errors="replace"))
            calls = []
            m = mission("CRASH-A")
            restarted = Runtime(tmp, executor=lambda task: calls.append(task["id"]))
            restarted.run_queue([m], seal([m]))
            self.assertEqual(calls, [], "an uncertain worker must never be launched twice")
            self.assertEqual(restarted.state(m)["status"], "AWAITING_HUMAN")


if __name__ == "__main__":
    unittest.main()
