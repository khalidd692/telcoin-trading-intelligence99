"""Deterministic owner-feed tests: no live GitHub, Ollama or Docker."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import github_owner_feed as feed
from scripts.agents.automation import github_multi_mandate_session as multi
from tests.test_github_local_code_campaign import OWNER, TIMES, EXPIRY, block
from tests.test_github_multi_mandate_session import FakeCampaign

BASE = "934d9fd8a3fd498c6e3e69226007dd46276aa6da"
REF = "agents/tel99-code-base-recipe-a-20261124"


def fixture(issue=211):
    scope = {
        "repo": feed.REPO, "issue": issue, "label": "enhancement",
        "expires_at": EXPIRY, "base": REF, "base_sha": BASE,
        "contracts": {"first": "1"*64, "second": "2"*64},
    }
    comment = {
        "id": 70000+issue,
        "issue_url": f"https://api.github.com/repos/{feed.REPO}/issues/{issue}",
        "user": OWNER.copy(), "created_at": TIMES[0], "updated_at": TIMES[0],
        "body": block(feed.MANDATE, scope),
    }
    row = {
        "number": issue, "state": "open", "user": OWNER.copy(),
        "body": "New explicitly approved controller\n"+feed.OWNER_MARKER,
    }
    return row, comment


class FakeGitHub:
    def __init__(self):
        self.issue, self.comment = fixture()
        self.requests = []
        self.hide = False
        self.fail_auth = False

    def __call__(self, endpoint):
        self.requests.append(endpoint)
        if endpoint == "user":
            return {"login": "someoneelse", "id": 1, "type": "User"} if self.fail_auth else OWNER.copy()
        if endpoint.startswith(f"repos/{feed.REPO}/issues?"):
            return [] if self.hide else [self.issue]
        if endpoint.startswith(f"repos/{feed.REPO}/issues/{self.issue['number']}/comments?"):
            return [self.comment]
        raise AssertionError(f"unexpected URL {endpoint}")


class OwnerFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.github = FakeGitHub()

    def test_read_only_discovers_one_pinned_owner_controller(self):
        found = feed.discover_owner_pins(fetcher=self.github)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["issue"], 211)
        self.assertEqual(found[0]["mandate_sha256"], hashlib.sha256(
            self.github.comment["body"].encode("utf-8")).hexdigest())
        self.assertTrue(all("?" in url or url == "user" for url in self.github.requests))
        self.assertEqual(found[0]["base_sha"], BASE)

    def test_rejects_any_other_github_account(self):
        self.github.fail_auth = True
        with self.assertRaisesRegex(ValueError, "pinned repository owner"):
            feed.pinned_owner_feed(self.root, fetcher=self.github)
        self.assertFalse((self.root / "feed-ledger").exists())

    def test_an_unmarked_issue_is_never_executable(self):
        self.github.issue["body"] = "new task idea; not approved"
        self.assertEqual(feed.discover_owner_pins(fetcher=self.github), [])

    def test_historical_or_forged_issue_refused(self):
        self.github.issue["number"] = 199
        self.github.comment["issue_url"] = f"https://api.github.com/repos/{feed.REPO}/issues/199"
        self.assertEqual(feed.discover_owner_pins(fetcher=self.github), [])
        self.github.issue, self.github.comment = fixture()
        self.github.issue["user"] = {"id": 55, "login": "impersonator", "type": "User"}
        self.assertEqual(feed.discover_owner_pins(fetcher=self.github), [])

    def test_changed_and_duplicated_owner_comments_fail_closed(self):
        self.github.comment["updated_at"] = TIMES[1]
        with self.assertRaisesRegex(ValueError, "exactly one immutable"):
            feed.discover_owner_pins(fetcher=self.github)
        self.github.comment["updated_at"] = TIMES[0]
        original = self.github
        class DuplicateComments:
            def __call__(self, endpoint):
                if "/comments?" in endpoint:
                    return [original.comment, original.comment]
                return original(endpoint)
        with self.assertRaisesRegex(ValueError, "exactly one immutable"):
            feed.discover_owner_pins(fetcher=DuplicateComments())

    def test_persistent_pin_rejects_vanishing_or_edited_mandates(self):
        saved = feed.pinned_owner_feed(self.root, fetcher=self.github)
        self.assertEqual(feed.pinned_owner_feed(self.root, fetcher=self.github), saved)
        self.github.comment["body"] += " "
        with self.assertRaisesRegex(ValueError, "changed"):
            feed.pinned_owner_feed(self.root, fetcher=self.github)
        self.github.comment["body"] = fixture()[1]["body"]
        self.github.hide = True
        with self.assertRaisesRegex(ValueError, "disappeared"):
            feed.pinned_owner_feed(self.root, fetcher=self.github)

    def test_preflight_still_requires_complete_mission_approvals(self):
        pins = feed.discover_owner_pins(fetcher=self.github)
        calls = []
        def build(spec, root, deadline):
            calls.append(spec["issue"])
            return FakeCampaign(spec, {}, [], ready=False)
        with self.assertRaisesRegex(multi.Blocked, "lacks signed approvals"):
            multi.preflight_campaigns(pins, self.root, None, build=build)
        self.assertEqual(calls, [211])

    def test_runtime_discovers_second_mandate_without_manifest_copy(self):
        first, second = fixture(211), fixture(212)
        selections = [[{"issue": 211}], [{"issue": 211}, {"issue": 212}]]
        calls, done = [], {}
        def discover(root):
            if selections:
                return selections.pop(0)
            return [{"issue":211}, {"issue":212}]
        def build(spec, root, deadline):
            return FakeCampaign(spec, done, calls)
        def sleep(_):
            if not done.get(212):
                import time
                time.sleep(_)
        report = multi.run_campaigns(
            None, self.root/"state", seconds=2, poll_interval=1,
            build=build, discover=discover, sleep=sleep)
        self.assertEqual(calls, [211,212])
        self.assertEqual(report, {211:True,212:True})

    def test_main_preflight_explains_idle_queue_without_faking_work(self):
        with patch.object(feed, "pinned_owner_feed", return_value=[]):
            result = multi.main(["preflight", "--state", str(self.root), "--auto-feed"])
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
