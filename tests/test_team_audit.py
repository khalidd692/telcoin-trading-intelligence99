import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("team_audit", ROOT / "scripts/agents/team_audit.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class TeamAuditTests(unittest.TestCase):
    def test_read_only(self):
        result = MODULE.audit()
        self.assertEqual(result["mode"], "read_only")
        self.assertEqual(result["agents_running"], 0)
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["deploy_allowed"])
    def test_roles_have_paths(self):
        result = MODULE.audit()
        self.assertGreaterEqual(result["roles_defined"], 10)
        self.assertTrue(all(v["paths"] for v in result["roles"].values()))

if __name__ == "__main__":
    unittest.main()
