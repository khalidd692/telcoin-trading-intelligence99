"""Bounded cooperation of TEL99 analyst, developer and verifier roles.

No new supervisor or arbitrary tools. The analyst performs one read-only
Ollama call. The developer is the existing scoped function-only worker.
The third stage remains the independent Docker verifier, never LLM self-approval.
"""
from __future__ import annotations

import hashlib
import re

from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.native.provider import ProviderError
from scripts.agents.team_config import role_catalog

TEAM = ["tel99-analyst", "tel99-dev", "tel99-verifier"]
ANALYST_MODEL = "gemma4:e4b-tel99-8k"
MAX_ADVICE_BYTES = 1_200


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def enabled(mission) -> bool:
    return mission.get("team") == TEAM


def analyze(mission: dict, function: str) -> dict:
    """Execute a real, bounded, tool-free analyst call before development."""
    if not enabled(mission) or "routing" in mission:
        raise ValueError("team analyst requires the exact approved fixed-model team")
    catalogue = role_catalog()
    analyst = catalogue["quant"]
    developer = catalogue["development"]
    verifier = catalogue["quality"]
    if (not all(spec.active for spec in (analyst, developer, verifier))
            or [analyst.name, developer.name, verifier.name] != TEAM
            or mission.get("specialist") != developer.name):
        raise ValueError("TEL99 specialist role catalogue does not match the mission")

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
        "role": analyst.name,
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
