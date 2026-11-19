"""Bounded code work and an independent, test-at-commit verifier for Windows."""

import hashlib
import json
import re

NATIVE_BASE = "codex/native-v1-delivery-20261118"
_PYTHON_FILE = re.compile(r"(?:scripts/agents/native/[a-z0-9_]+|tests/test_[a-z0-9_]+)\.py")
_TEST_FILE = re.compile(r"test_[a-z0-9_]+\.py")
_TEST_SELECTOR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")


def contract_digest(mission):
    scope = {key: mission[key] for key in (
        "id", "issue", "role", "assignee", "base_sha", "files", "test_file",
        "objective", "priority", "dependencies", "expires_at",
    )}
    scope["dependency_evidence"] = mission.get("dependency_evidence", {})
    scope["test_selector"] = mission.get("test_selector")
    scope["supplemental_test"] = mission.get("supplemental_test")
    if mission.get("routing_profile"):
        scope["routing_profile"] = mission["routing_profile"]
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode("utf-8")).hexdigest()


def valid_scope(mission):
    files = mission.get("files")
    test = mission.get("test_file", "")
    selector = mission.get("test_selector")
    supplemental = mission.get("supplemental_test")
    return (
        isinstance(files, list) and 1 <= len(files) <= 8
        and all(isinstance(path, str) and _PYTHON_FILE.fullmatch(path) for path in files)
        and len(set(files)) == len(files)
        and not {"scripts/agents/native/provider.py", "scripts/agents/native/__init__.py"} & set(files)
        and isinstance(test, str) and bool(_TEST_FILE.fullmatch(test))
        and f"tests/{test}" not in files
        and (selector is None or isinstance(selector, str) and _TEST_SELECTOR.fullmatch(selector))
        and (supplemental is None or isinstance(supplemental, str)
             and _TEST_FILE.fullmatch(supplemental) and f"tests/{supplemental}" in files)
    )


def status_paths(status):
    """Only plain additions/modifications are allowed, including staged replay."""
    paths = []
    for line in status.splitlines():
        code, separator, path = line[:2], line[2:3], line[3:]
        if separator != " " or code not in {"??", " M", "M ", "MM", "A ", "AM"}:
            raise ValueError("Le diff comporte une suppression, un renommage ou un fichier ignoré.")
        paths.append(path)
    return paths


def synthetic_missions():
    fixtures = (
        ("CODE-DEMO-01", [], "add(a, b), qui renvoie la somme", "add", "2, 3", 5),
        ("CODE-DEMO-02", ["CODE-DEMO-01"], "multiply(a, b), qui renvoie le produit", "multiply", "4, 3", 12),
    )
    return [
        {"id": task, "priority": "P0", "dependencies": deps, "kind": "code",
         "files": ["arithmetic.py", "operation.py"], "test_file": "test_independent.py",
         "objective": (
             f"Dans operation.py implémente {operation}. Dans arithmetic.py réexporte "
             f"{name} depuis operation.py. N'ajoute aucun autre fichier."
         ),
         "fixture": (
             "import unittest\n"
             f"from arithmetic import {name} as public_operation\n"
             f"from operation import {name} as implementation\n\n"
             "class IndependentTest(unittest.TestCase):\n"
             "    def test_contract(self):\n"
             f"        self.assertEqual(public_operation({args}), {expected})\n"
             "        self.assertIs(public_operation, implementation)\n"
         )}
        for task, deps, operation, name, args, expected in fixtures
    ]
