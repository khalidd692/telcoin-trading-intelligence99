"""Offline regression tests for a bounded multi-issue TEL99 hour campaign.

The existing 2-issue GitHub flow stays supported. These fixtures use mock
GitHub receipts and no real Ollama, Docker or network calls.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.agents.automation import github_local_code_campaign as campaign, local_team
from scripts.agents.automation.autonomy_runtime import Runtime, fingerprint
from tests.test_github_local_code_campaign import (
    LocalFixture, SOURCE, OWNER, CONTROL, FIRST, SECOND, MANDATE_ID,
    TIMES, EXPIRY, block, comment,
)


def three_issues():
    fixture = LocalFixture()
    source = json.loads(SOURCE.read_text(encoding="utf-8"))["missions"]
    third = next(m for m in source if m["function"] == "git_changes").copy()
    third.update(
        id="tel99-pilot-code-c", model="gemma4:e4b-tel99-8k",
        port=11434, team=local_team.TEAM.copy(),
        dependencies=[fixture.missions[1]["id"]],
    )
    fixture.missions = tuple([*fixture.missions, third])
    fixture.scope["contracts"][third["id"]] = fingerprint(third)
    fixture.mandate["body"] = block(campaign.MANDATE, fixture.scope)
    fixture.pin = hashlib.sha256(fixture.mandate["body"].encode("utf-8")).hexdigest()
    n = SECOND + 1
    fixture.issues[n] = {
        "number": n, "state": "open", "user": OWNER.copy(),
        "labels": [{"name": campaign.CODE_LABEL}],
        "created_at": TIMES[1], "body": f"tel99-code-campaign: {MANDATE_ID}",
    }
    approval = {
        "approver": "khalidd692", "origin": "owner-direct",
        "mandate_comment_id": MANDATE_ID, "issue": n,
        "mission_sha256": fingerprint(third), "expires_at": EXPIRY,
    }
    fixture.comments.append(
        comment(5000 + n, n,
                block(campaign.APPROVAL, {"mission": third, "approval": approval}), TIMES[2]),
    )
    return fixture


class HourCampaignTests(unittest.TestCase):
    def test_three_distinct_signed_missions_are_admitted(self):
        f = three_issues()
        records = f.handoff().preflight()
        self.assertEqual(len(records), 3)
        self.assertEqual({x["issue"] for x in records}, {FIRST, SECOND, SECOND + 1})
        self.assertEqual({x["id"] for x in records}, set(f.scope["contracts"]))

    def test_two_mission_legacy_contract_remains_compatible(self):
        self.assertEqual(len(LocalFixture().handoff().preflight()), 2)

    def test_branching_dependencies_are_refused(self):
        f = three_issues()
        a, b, c = f.missions
        bad = {a["id"]: {"mission": a}, b["id"]: {"mission": b},
               c["id"]: {"mission": {**c, "dependencies": [a["id"]]}}}
        with self.assertRaisesRegex(ValueError, "ordered dependency chain"):
            campaign.LocalCodeCampaign.check_campaign_graph(bad, f.scope)

    def test_missing_predecessor_is_refused(self):
        f = three_issues()
        a, b, c = f.missions
        broken = {a["id"]: {"mission": a}, b["id"]: {"mission": b},
                  c["id"]: {"mission": {**c, "dependencies": ["missing-contract"]}}}
        with self.assertRaisesRegex(ValueError, "unknown or self-referential"):
            campaign.LocalCodeCampaign.check_campaign_graph(broken, f.scope)

    def test_no_complete_claim_without_three_real_result_receipts(self):
        f = three_issues()
        with tempfile.TemporaryDirectory() as folder:
            runtime = Runtime(Path(folder))
            handoff = f.handoff(runtime)
            handoff.source()
            self.assertFalse(handoff.complete())

    def test_no_more_than_ten_signed_missions_in_scope(self):
        f = three_issues()
        for i in range(8):
            f.scope["contracts"][f"extra-{i}"] = "a" * 64
        f.mandate["body"] = block(campaign.MANDATE, f.scope)
        f.pin = hashlib.sha256(f.mandate["body"].encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "signed code campaign"):
            f.handoff().check_mandate()


if __name__ == "__main__":
    unittest.main()
