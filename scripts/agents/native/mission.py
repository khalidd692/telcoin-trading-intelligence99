"""Deterministic native mission verdict kernel.

Pure, stateless verdict over a list of check results. Reused by the native
mission runner (scripts/agents/native/) and by the contract tests
(tests/test_agent_native_verdict_contract.py). No network, no provider, no
order, no secret.
"""

from __future__ import annotations


def decide_verdict(checks: list[dict]) -> str:
    """Return ``"PASS"`` only if every check carries ``ok: True``.

    A check is valid when it is a mapping containing an ``ok`` key set to
    ``True``. Any missing ``ok`` key, any ``ok`` value other than ``True``, or
    an empty list yields ``"FAIL"``. Fail-closed: uncertainty never becomes PASS.
    """
    if not isinstance(checks, list) or len(checks) == 0:
        return "FAIL"
    for check in checks:
        if not isinstance(check, dict):
            return "FAIL"
        if check.get("ok") is not True:
            return "FAIL"
    return "PASS"
