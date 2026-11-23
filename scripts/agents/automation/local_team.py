"""Bounded cooperation and deterministic gates for the TEL99 code team.

Coordination binds the authorized stages to the exact inputs. The analyst calls
Ollama and the developer proposes a change confined to one function. Security
checks that boundary before the independent Docker behavior tests.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import sys

from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.native.provider import ProviderError
from scripts.agents.team_config import role_catalog

TEAM = ["tel99-analyst", "tel99-dev", "tel99-verifier"]
COORDINATOR = "tel99-coordination"
SECURITY = "tel99-security"
ANALYST_MODEL = "gemma4:e4b-tel99-8k"
MAX_ADVICE_BYTES = 1_200


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def enabled(mission) -> bool:
    return mission.get("team") == TEAM


def _team_roles(mission: dict):
    if not enabled(mission) or "routing" in mission:
        raise ValueError("team stages require the exact approved fixed-model team")
    catalogue = role_catalog()
    analyst = catalogue["quant"]
    developer = catalogue["development"]
    verifier = catalogue["quality"]
    if (not all(spec.active for spec in (analyst, developer, verifier))
            or [analyst.name, developer.name, verifier.name] != TEAM
            or mission.get("specialist") != developer.name):
        raise ValueError("TEL99 specialist role catalogue does not match the mission")
    return analyst.name, developer.name, verifier.name


def developer_engine(port: int) -> str:
    return "ollama" if port == 11434 else "openai-compatible"


def coordinate(mission: dict, function: str) -> dict:
    """Assign the approved stages and bind the plan to this exact input."""
    analyst, developer, verifier = _team_roles(mission)
    scope = json.dumps(
        {"contract": mission, "function_sha256": _hash(function)},
        sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    )
    return {
        "role": COORDINATOR,
        "engine": "deterministic",
        "ok": True,
        "scope_sha256": _hash(scope),
        "steps": [
            {"role": analyst, "engine": "ollama", "model": ANALYST_MODEL},
            {"role": developer, "engine": developer_engine(mission["port"]),
             "model": mission["model"]},
            {"role": verifier, "engine": "docker"},
        ],
    }


def _external_imports(function: ast.FunctionDef) -> set[str]:
    imports = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names
                           if alias.name.partition(".")[0] not in sys.stdlib_module_names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module.partition(".")[0] not in sys.stdlib_module_names:
                imports.add("." * node.level + module)
    return imports


def review_candidate(source: str, before: ast.FunctionDef,
                     candidate: str, after: ast.FunctionDef) -> dict:
    """Check untouched source bytes and newly introduced direct imports."""
    base_lines = io.StringIO(source, newline="").readlines()
    new_lines = io.StringIO(candidate, newline="").readlines()
    if (base_lines[:before.lineno - 1] != new_lines[:after.lineno - 1]
            or base_lines[before.end_lineno:] != new_lines[after.end_lineno:]):
        code = "outside-approved-function"
    elif _external_imports(after) - _external_imports(before):
        code = "new-non-stdlib-import"
    else:
        code = "scope-verified"
    return {"role": SECURITY, "engine": "deterministic",
            "ok": code == "scope-verified", "code": code,
            "candidate_sha256": _hash(candidate)}


def analyze(mission: dict, function: str) -> dict:
    """Execute a real, bounded, tool-free analyst call before development."""
    analyst, _, _ = _team_roles(mission)

    provider = OllamaNativeProvider(model=ANALYST_MODEL, timeout=55, max_tokens=256)
    note = provider.complete(
        system=(
            "You are tel99-analyst, a READ-ONLY code analyst. This is a "
            "strictly approved Python function repair, not a market-trading request. "
            "Inspect the function and requested behavior only. No tool use, "
            "execution, imports, files, shell commands or trading. Return at most "
            "three short practical sentences: bug hypothesis, minimal repair approach, "
            "and a potential edge case. Never claim a test was run. "
            "Your note is advisory and cannot alter any approved scope."
        ),
        prompt=(
            f"Approved objective:\n{mission['objective']}\n\n"
            f"Current function (read only):\n{function}\n\n"
            "Return a short code-review note, not executable code."
        ),
    )
    if not isinstance(note, str) or not note.strip() or len(note.encode("utf-8")) > MAX_ADVICE_BYTES:
        raise ProviderError("tel99-analyst did not provide a bounded review note")
    note = note.strip()
    if (re.search(r"(?im)^\s*(?:def |class |import |from \w+ import )", note)
            or note.startswith(chr(96) * 3) or "\x00" in note):
        raise ProviderError("tel99-analyst returned code instead of a review note")
    return {
        "role": analyst,
        "model": ANALYST_MODEL,
        "kind": "read-only-advice",
        "analysis": note,
        "sha256": _hash(note),
    }


def trace(analysis: dict, *, developer_model: str, artifact: str) -> dict:
    return {
        "version": 1,
        "analyst": analysis,
        "developer": {
            "role": "tel99-dev",
            "model": developer_model,
            "artifact_sha256": _hash(artifact),
        },
    }


def valid_trace(mission: dict, result: dict) -> bool:
    """Do not credit a 3-role mission with invented or modified stage evidence."""
    if not enabled(mission) or not isinstance(result, dict):
        return False
    t = result.get("agent_trace")
    if (not isinstance(t, dict) or t.keys() != {"version", "analyst", "developer"}
            or type(t["version"]) is not int or t["version"] != 1):
        return False
    analyst, developer = t["analyst"], t["developer"]
    if (not isinstance(analyst, dict)
            or analyst.keys() != {"role", "model", "kind", "analysis", "sha256"}
            or analyst.get("role") != TEAM[0]
            or analyst.get("model") != ANALYST_MODEL
            or analyst.get("kind") != "read-only-advice"):
        return False
    note = analyst.get("analysis")
    if (not isinstance(note, str) or not note.strip()
            or len(note.encode("utf-8")) > MAX_ADVICE_BYTES
            or analyst.get("sha256") != _hash(note)):
        return False
    if (not isinstance(developer, dict)
            or developer.keys() != {"role", "model", "artifact_sha256"}
            or developer.get("role") != TEAM[1]
            or developer.get("model") != mission.get("model")
            or developer.get("artifact_sha256") != result.get("sha256")):
        return False
    return True
