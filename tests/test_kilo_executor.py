import hashlib
import unittest
from unittest.mock import Mock
from scripts.agents.automation.kilo_executor import Executor, ExecutorUnavailable, verify
from scripts.agents.native.provider import ProviderError


def mission():
    return {'id': 'synthetic-a', 'synthetic_data': True, 'role': 'tel99-dev',
            'objective': 'Return synthetic greeting',
            'expected_sha256': hashlib.sha256(b'HELLO').hexdigest()}


class KiloExecutorTests(unittest.TestCase):
    def provider(self, text='HELLO'):
        p = Mock()
        p.complete.return_value = text
        p.last_completion_evidence = {'cost_usd': '0', 'http_status': 200,
            'catalog_sha256': 'a'*64, 'response_sha256': 'b'*64}
        return p

    def test_real_adapter_calls_provider_and_preserves_exact_bytes(self):
        p = self.provider()
        result = Executor(provider=p).execute(mission())
        self.assertEqual(result['artifact'], 'HELLO')
        self.assertEqual(result['specialist_id'], 'tel99-dev')
        self.assertTrue(verify(mission(), result)['ok'])
        self.assertEqual(p.complete.call_count, 1)

    def test_verifier_rejects_red_artifact_independently(self):
        result = Executor(provider=self.provider('BAD')).execute(mission())
        self.assertFalse(verify(mission(), result)['ok'])

    def test_verifier_unavailable_fails_closed(self):
        result = Executor(provider=self.provider()).execute(mission())
        self.assertFalse(verify(mission(), result, executable='does-not-exist-tel99')['ok'])

    def test_provider_quota_has_no_fallback(self):
        p = self.provider()
        p.complete.side_effect = ProviderError('provider HTTP 429')
        with self.assertRaises(ExecutorUnavailable):
            Executor(provider=p).execute(mission())
        self.assertEqual(p.complete.call_count, 1)

    def test_provider_cost_not_proven_fails_closed(self):
        p = self.provider()
        p.last_completion_evidence['cost_usd'] = '1'
        with self.assertRaises(ExecutorUnavailable):
            Executor(provider=p).execute(mission())

    def test_no_private_prompt_or_unknown_specialist(self):
        for key, value in [('synthetic_data', False), ('role', 'unknown')]:
            m = mission(); m[key] = value
            p = self.provider()
            with self.assertRaises(ExecutorUnavailable):
                Executor(provider=p).execute(m)
            p.complete.assert_not_called()

    def test_verifier_rejects_falsified_evidence(self):
        result = Executor(provider=self.provider()).execute(mission())
        result['provider_evidence']['cost_usd'] = '1'
        self.assertFalse(verify(mission(), result)['ok'])

    def test_lf_is_not_silently_stripped(self):
        result = Executor(provider=self.provider('HELLO\n')).execute(mission())
        self.assertFalse(verify(mission(), result)['ok'])


if __name__ == '__main__':
    unittest.main()
