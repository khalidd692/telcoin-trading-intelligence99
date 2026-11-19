"""Independent fixed-code verifier for Hermes relay artifacts.

Same pattern as the #124 kilo verifier: a distinct Python process with fixed
code, JSON input, no specialist-supplied criterion. It checks the approved
acceptance hash, the specialist identity and the durable Hermes session /
zero-cost evidence. It does not certify broad source-code correctness or a
GitHub approval.
"""
from __future__ import annotations

import json
import subprocess
import sys

FREE_MODELS = ("meituan/longcat-2.5:free", "upstage/solar-mini4:free")

_VERIFY_CODE = r'''
import hashlib, json, re, sys
FREE = ("meituan/longcat-2.5:free", "upstage/solar-mini4:free")
try:
    payload = json.loads(sys.stdin.buffer.read(100000))
    mission, result = payload['mission'], payload['result']
    artifact = result.get('artifact')
    actual = hashlib.sha256(artifact.encode('utf-8')).hexdigest() if isinstance(artifact, str) else None
    evidence = result.get('provider_evidence') or {}
    role = mission.get('specialist') or mission.get('assigned_to') or mission.get('role')
    checks = [
        {'name': 'synthetic-contract', 'ok': mission.get('synthetic_data') is True and mission.get('project') == 'synthetic'},
        {'name': 'artifact-sha256', 'ok': actual == mission.get('expected_sha256') == result.get('sha256')},
        {'name': 'specialist-identity', 'ok': result.get('specialist_id') == role and role in ('tel99-dev', 'tel99-analyst', 'tel99-verifier')},
        {'name': 'hermes-session-evidence', 'ok': re.fullmatch(r'local-[0-9a-f]{64}', str(result.get('session_id', ''))) is not None and evidence.get('session_id') == result.get('session_id') and evidence.get('exit_code') == 0 and isinstance(evidence.get('api_call_count'), int) and evidence.get('api_call_count') >= 1},
        {'name': 'zero-cost-evidence', 'ok': evidence.get('estimated_cost_usd') == 0.0 and evidence.get('actual_cost_usd') in (0.0, None) and evidence.get('model') in FREE and evidence.get('billing_provider') == 'nous' and result.get('model') == evidence.get('model')},
    ]
    print(json.dumps({'ok': all(c['ok'] for c in checks), 'checks': checks, 'artifact_sha256': actual, 'verifier': 'hermes-fixed-subprocess-v1'}))
except Exception:
    print(json.dumps({'ok': False, 'checks': [{'name': 'verifier-input', 'ok': False}]}))
'''


def verify(mission, result, *, executable=None):
    try:
        payload = json.dumps({"mission": mission, "result": result}, ensure_ascii=True)
        if len(payload.encode()) > 99000:
            raise ValueError("oversized verifier input")
        completed = subprocess.run(
            [executable or sys.executable, "-I", "-B", "-c", _VERIFY_CODE],
            input=payload, capture_output=True, text=True, timeout=15, check=False,
        )
        report = json.loads(completed.stdout)
        if completed.returncode != 0 or report.get("ok") not in (True, False):
            raise ValueError("invalid verifier result")
        return report
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return {"ok": False, "unavailable": True,
                "checks": [{"name": "independent-verifier-available", "ok": False}]}


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
