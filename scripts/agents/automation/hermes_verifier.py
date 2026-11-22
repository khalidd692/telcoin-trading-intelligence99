"""Independent fixed-code verifier for Hermes relay artifacts.

Same pattern as the #124 kilo verifier: a distinct Python process with fixed
code, JSON input, no specialist-supplied criterion. It checks the approved
acceptance hash, the specialist identity and the durable Hermes session /
zero-cost evidence. It does not certify broad source-code correctness or a
GitHub approval.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.agents.automation.kilo_executor import verify_fixed_report

# Independent verifier allowlist: explicitly pin the same reviewed free-model
# policy as HermesExecutor; no imports of executor or specialist-supplied rules.
FREE_MODELS = ("qwen/qwen4-max:free", "meituan/longcat-2.5:free", "upstage/solar-mini4:free")

_VERIFY_CODE = r'''
import hashlib, json, re, sys
FREE = ("qwen/qwen4-max:free", "meituan/longcat-2.5:free", "upstage/solar-mini4:free")
try:
    payload = json.loads(sys.stdin.buffer.read(100000))
    mission, result = payload['mission'], payload['result']
    artifact = result.get('artifact')
    actual = hashlib.sha256(artifact.encode('utf-8')).hexdigest() if isinstance(artifact, str) else None
    evidence = result.get('provider_evidence') or {}
    role = mission.get('specialist') or mission.get('assigned_to') or mission.get('role')
    checks = [
        {'name': 'synthetic-contract', 'ok': mission.get('synthetic_data') is True and mission.get('project') == 'synthetic'},
        {'name': 'artifact-sha256', 'ok': actual is not None and actual == mission.get('expected_sha256') == result.get('sha256')},
        {'name': 'specialist-identity', 'ok': result.get('specialist_id') == role and role in ('tel99-dev', 'tel99-analyst', 'tel99-verifier')},
        {'name': 'hermes-session-evidence', 'ok': re.fullmatch(r'local-[0-9a-f]{64}', str(result.get('session_id', ''))) is not None and evidence.get('session_id') == result.get('session_id') and evidence.get('exit_code') == 0 and type(evidence.get('api_call_count')) is int and evidence.get('api_call_count') >= 1},
        {'name': 'zero-cost-evidence', 'ok': all(type(evidence.get(key)) in (float, int) and evidence[key] == 0 for key in ('estimated_cost_usd', 'actual_cost_usd')) and evidence.get('model') in FREE and evidence.get('billing_provider') == 'nous' and result.get('model') == evidence.get('model')},
    ]
    print(json.dumps({'ok': all(c['ok'] for c in checks), 'checks': checks, 'artifact_sha256': actual, 'verifier': 'hermes-fixed-subprocess-v1'}))
except Exception:
    print(json.dumps({'ok': False, 'checks': [{'name': 'verifier-input', 'ok': False}]}))
'''


def verify(mission, result, *, executable=None):
    return verify_fixed_report(
        mission, result, _VERIFY_CODE, "hermes-fixed-subprocess-v1",
        {"synthetic-contract", "artifact-sha256", "specialist-identity",
         "hermes-session-evidence", "zero-cost-evidence"}, executable=executable,
    )


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify",))
    parser.parse_args(argv)
    raw = sys.stdin.buffer.read(100001)
    if len(raw) > 100000:
        print(json.dumps({"ok": False, "unavailable": True}))
        return 4
    payload = json.loads(raw)
    report = verify(payload["mission"], payload["result"])
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0 if report.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
