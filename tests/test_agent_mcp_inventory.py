#!/usr/bin/env python3
"""Tests for the TEL99 MCP / capabilities inventory (issue #86).

Stdlib only, no network, no LLM: the inventory is static data plus pure
functions, so the tests assert exact, reproducible behaviour and the safety
invariants the owner asked for:

- the five verdict buckets are always present;
- nothing is reported as enabled/tested unless it is free, read-only and
  backed by reproducible evidence;
- an "A_AJOUTER" entry may never duplicate an existing capability;
- Context7 is recorded as already present (not as a thing to install);
- the inventory never claims an order or a deployment is allowed.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from capabilities import inventory  # noqa: E402


class InventorySafetyTests(unittest.TestCase):
    def test_validate_passes(self):
        inventory.validate()  # must not raise

    def test_five_buckets_present(self):
        counts = inventory.counts()
        for bucket in ("EXISTANT", "A_AJOUTER", "AJOUTE_ET_TESTE",
                       "NON_NECESSAIRE", "BLOCKED"):
            self.assertIn(bucket, counts)

    def test_read_only_no_orders_no_deploy(self):
        data = inventory.report()
        self.assertEqual(data["mode"], "read_only")
        self.assertFalse(data["orders_allowed"])
        self.assertFalse(data["deploy_allowed"])

    def test_quota_gate_matches_issue(self):
        self.assertEqual(inventory.QUOTA_MIN_REMAINING, 12)

    def test_tested_is_free_readonly_and_evidenced(self):
        for cap in inventory.all_capabilities():
            if cap.verdict == "AJOUTE_ET_TESTE":
                self.assertEqual(cap.cost, "gratuit", cap.key)
                self.assertFalse(cap.writes, cap.key)
                self.assertTrue(cap.evidence, cap.key)

    def test_to_add_never_duplicates_existing(self):
        existing = {c.key for c in inventory.EXISTING}
        for cap in inventory.TO_ADD:
            self.assertNotIn(cap.key, existing)

    def test_context7_recorded_as_existing_not_to_install(self):
        keys = {c.key for c in inventory.EXISTING}
        self.assertIn("context7_mcp", keys)
        to_add = {c.key for c in inventory.TO_ADD}
        self.assertNotIn("context7_mcp", to_add)

    def test_github_and_memory_not_reinstalled(self):
        # GitHub is already connected and memory already exists -> a second
        # integration of the same capability is explicitly NON_NECESSAIRE.
        not_needed = {c.key for c in inventory.NOT_NEEDED}
        self.assertIn("github_mcp_second", not_needed)
        self.assertIn("second_memory", not_needed)

    def test_quota_block_is_recorded(self):
        blocked = {c.key for c in inventory.BLOCKED}
        self.assertIn("long_mission_quota", blocked)

    def test_roles_are_the_three_active_agents(self):
        self.assertEqual(
            set(inventory.ROLES),
            {"tel99-analyst", "tel99-dev", "tel99-verifier"},
        )

    def test_needs_matrix_covers_all_roles_and_common(self):
        for role in inventory.ROLES:
            self.assertIn(role, inventory.NEEDS_MATRIX)
        self.assertIn("commun", inventory.NEEDS_MATRIX)

    def test_report_is_json_serialisable(self):
        import json

        text = json.dumps(inventory.report(), sort_keys=True)
        self.assertIn("context7", text)

    def test_validate_rejects_paid_tested_capability(self):
        # Guard against a future edit that marks a paid server as tested.
        bad = inventory.Capability(
            key="x", label="x", verdict="AJOUTE_ET_TESTE", scope="compte",
            cost="payant", writes=False, evidence=("cmd",),
        )
        original = inventory.ADDED_AND_TESTED
        try:
            inventory.ADDED_AND_TESTED = original + (bad,)
            with self.assertRaises(ValueError):
                inventory.validate()
        finally:
            inventory.ADDED_AND_TESTED = original


if __name__ == "__main__":
    unittest.main()
