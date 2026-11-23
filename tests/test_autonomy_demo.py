import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROGRAM = Path(__file__).resolve().parents[1] / "docs/agents/autonomy-demo/tasks.py"


class TaskLookupTests(unittest.TestCase):
    def test_edit_mixed_records_preserves_positions_and_updates_first_match(self):
        original = [
            None,
            "old",
            17,
            {"title": "legacy"},
            {"id": "ok", "title": "old title", "done": False},
            {"id": "ok", "title": "duplicate", "done": False},
        ]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tasks.json"
            database.write_text(json.dumps(original), encoding="utf-8")
            command = [sys.executable, "-I", "-B", str(PROGRAM), "--db", str(database)]

            edited = subprocess.run(
                [*command, "edit", "ok", "new title"], capture_output=True, text=True, timeout=5,
            )
            expected = {"id": "ok", "title": "new title", "done": False}
            self.assertEqual(edited.returncode, 0, edited.stderr)
            self.assertEqual(json.loads(edited.stdout), expected)
            self.assertEqual(
                json.loads(database.read_text(encoding="utf-8")),
                [*original[:4], expected, original[5]],
            )

            missing = subprocess.run(
                [*command, "delete", "missing"], capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(missing.returncode, 1, missing.stderr)
            self.assertEqual(json.loads(missing.stdout), {"error": "Task not found"})
            self.assertEqual(
                json.loads(database.read_text(encoding="utf-8")),
                [*original[:4], expected, original[5]],
            )
