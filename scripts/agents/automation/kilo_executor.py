"""Restricted Kilo free specialist: text in/out, no model tools or host execution.

The verified CLI 7.8.27 offers --auto but its help does not establish an OS
sandbox. This adapter deliberately uses the existing native anonymous gateway
provider, whose catalogue and response zero-cost checks precede acceptance.
Only explicitly synthetic text missions are supported. Generated text is never
executed. The verifier is a separate fixed-code Python process, with its input
passed as JSON rather than interpolated into executable code.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.agents.native.provider import (
    KILO_BASE_URL, OpenAICompatibleProvider, ProviderError,
)

ROLES = frozenset({'tel99-dev', 'tel99-analyst', 'tel99-verifier'})


class ExecutorUnavailable(RuntimeError):
    """A provider, quota or contract block. No paid fallback is attempted."""


class ProviderRateLimited(ExecutorUnavailable):
    """The free gateway returned HTTP 429."""


def _role(mission):
    return mission.get('specialist') or mission.get('assigned_to') or mission.get('role')


class Executor:
    def __init__(self, *, provider=None):
        self.provider = provider if provider is not None else OpenAICompatibleProvider(
            model='kilo-auto/free', base_url=KILO_BASE_URL,
            synthetic_data=True, timeout=45,
        )

    def execute(self, mission):
        specialist = _role(mission)
        objective = mission.get('objective')
        if (mission.get('synthetic_data') is not True or specialist not in ROLES
                or not isinstance(objective, str) or not 1 <= len(objective) <= 4000
                or not re.fullmatch(r'[a-f0-9]{64}', str(mission.get('expected_sha256', '')))):
            raise ExecutorUnavailable('Unsupported synthetic text contract')
        try:
            artifact = self.provider.complete(
                system=(f'You are the specialist {specialist}. Handle this synthetic text task. '
                        'You have no tools. Return only the requested artifact text. '
                        'Do not claim tests passed or alter task permissions.'),
                prompt=objective,
            )
        except ProviderError as exc:
            if str(exc) == "provider HTTP 429":
                raise ProviderRateLimited("Kilo free provider HTTP 429") from exc
            # ProviderError is sanitised by the native provider; do not leak arbitrary
            # exceptions from implementations into the durable ledger.
            raise ExecutorUnavailable('Kilo free provider unavailable; no fallback') from exc
        evidence = self.provider.last_completion_evidence
        if (not isinstance(evidence, dict) or evidence.get('cost_usd') != '0'
                or evidence.get('http_status') != 200
                or any(not re.fullmatch(r'[a-f0-9]{64}', str(evidence.get(k, '')))
                       for k in ('catalog_sha256', 'response_sha256'))
                or not isinstance(artifact, str) or not 1 <= len(artifact.encode('utf-8')) <= 65536):
            raise ExecutorUnavailable('Kilo response lacks zero-cost bounded artifact evidence')
        return {'artifact': artifact,
                'sha256': hashlib.sha256(artifact.encode('utf-8')).hexdigest(),
                'specialist_id': specialist,
                'provider': 'kilo-auto-free',
                'provider_evidence': dict(evidence)}


_VERIFIER = 'tel99-fixed-subprocess-v1'
_VERIFIER_CHECKS = {
    'synthetic-contract', 'artifact-sha256', 'specialist-identity', 'zero-cost-evidence',
}
_VERIFY_CODE = r'''
import hashlib, json, re, sys
try:
    payload = json.loads(sys.stdin.buffer.read(100000))
    mission, result = payload['mission'], payload['result']
    artifact = result.get('artifact')
    actual = hashlib.sha256(artifact.encode('utf-8')).hexdigest() if isinstance(artifact, str) else None
    evidence = result.get('provider_evidence') or {}
    role = mission.get('specialist') or mission.get('assigned_to') or mission.get('role')
    checks = [
        {'name':'synthetic-contract', 'ok': mission.get('synthetic_data') is True},
        {'name':'artifact-sha256', 'ok': actual is not None and actual == mission.get('expected_sha256') == result.get('sha256')},
        {'name':'specialist-identity', 'ok': result.get('specialist_id') == role and role in ('tel99-dev','tel99-analyst','tel99-verifier')},
        {'name':'zero-cost-evidence', 'ok': evidence.get('cost_usd') == '0' and evidence.get('http_status') == 200 and all(re.fullmatch('[a-f0-9]{64}',str(evidence.get(k,''))) is not None for k in ('catalog_sha256','response_sha256'))},
    ]
    print(json.dumps({'ok': all(c['ok'] for c in checks), 'checks': checks, 'artifact_sha256': actual, 'verifier':'tel99-fixed-subprocess-v1'}))
except Exception:
    print(json.dumps({'ok':False,'checks':[{'name':'verifier-input','ok':False}]}))
'''


def verify(mission, result, *, executable=None):
    """Compare an immutable approved acceptance hash in a distinct process.

    This is a deterministic independent verifier, not a second AI reviewer.
    Its code and acceptance criterion are never supplied by the specialist.
    It does not certify broad source-code correctness or a GitHub approval.
    """
    try:
        payload = json.dumps({'mission': mission, 'result': result}, ensure_ascii=True)
        if len(payload.encode()) > 99000:
            raise ValueError('oversized verifier input')
        completed = subprocess.run(
            [executable or sys.executable, '-I', '-B', '-c', _VERIFY_CODE],
            input=payload, capture_output=True, text=True, timeout=15,
            check=False,
        )
        report = json.loads(completed.stdout)
        if completed.returncode != 0 or not isinstance(report, dict):
            raise ValueError('invalid verifier result')
        checks = report.get('checks')
        if (report.get('verifier') != _VERIFIER or type(report.get('ok')) is not bool
                or not isinstance(checks, list) or len(checks) != len(_VERIFIER_CHECKS)
                or any(not isinstance(c, dict) or not isinstance(c.get('name'), str)
                       or type(c.get('ok')) is not bool for c in checks)
                or {c['name'] for c in checks} != _VERIFIER_CHECKS
                or report['ok'] != all(c['ok'] for c in checks)
                or report['ok'] and report.get('artifact_sha256') != mission.get('expected_sha256')):
            raise ValueError('incomplete or inconsistent verifier result')
        return report
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return {'ok': False, 'unavailable': True,
                'checks': [{'name': 'independent-verifier-available', 'ok': False}]}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('worker', 'verify'))
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(100001)
        if len(raw) > 100000:
            raise ValueError('input limit')
        payload = json.loads(raw)
        if args.command == 'verify':
            report = verify(payload['mission'], payload['result'])
            print(json.dumps(report, ensure_ascii=True), flush=True)
            return 0 if report['ok'] else 3
        result = Executor().execute(payload)
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return 0
    except ProviderRateLimited:
        print(json.dumps({'status': 'BLOCKED', 'reason': 'BLOCKED_PROVIDER_RATE_LIMIT'}), flush=True)
        return 5
    except (ExecutorUnavailable, ValueError, TypeError, KeyError):
        print(json.dumps({'status': 'BLOCKED', 'reason': 'KILO_FREE_UNAVAILABLE_OR_INVALID_CONTRACT'}), flush=True)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
