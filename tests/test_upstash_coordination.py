import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "automation"
sys.path.insert(0, str(AUTOMATION))
import local_coordination as coordination
from upstash_coordination import RedisLease, RedisRest, RedisUnavailable


class TransportTests(unittest.TestCase):
    def test_destination_is_pinned_and_credentials_are_not_in_errors(self):
        for url in (
            "http://example.upstash.io", "https://example.upstash.io.evil.com",
            "https://example.upstash.io/?token=secret", "https://example.upstash.io:443",
        ):
            with self.assertRaises(RedisUnavailable) as error:
                RedisRest(url, "secret")
            self.assertNotIn("secret", str(error.exception))

    def test_free_must_be_confirmed_and_backend_must_be_unique(self):
        env = {"TEL99_UPSTASH_REST_URL": "https://example.upstash.io", "TEL99_UPSTASH_REST_TOKEN": "token"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(coordination.CoordinationUnavailable):
                coordination.coordination_backend()
        with patch.dict(os.environ, {**env, "TEL99_UPSTASH_FREE": "1"}, clear=True):
            with patch.object(coordination, "kv_env", return_value=("https://legacy.example", "token")):
                with self.assertRaises(coordination.CoordinationUnavailable):
                    coordination.coordination_backend()


class DockerRedis:
    def __init__(self):
        self.container = os.environ["TEL99_TEST_REDIS_CONTAINER"]

    def fork(self):
        return DockerRedis()

    def command(self, *args):
        result = subprocess.check_output(
            ["docker", "exec", self.container, "redis-cli", "--json", *map(str, args)],
            encoding="utf-8", timeout=20,
        )
        return json.loads(result)


@unittest.skipUnless(os.environ.get("TEL99_TEST_REDIS_CONTAINER"), "Redis de recette facultatif")
class ServerTests(unittest.TestCase):
    def setUp(self):
        self.shared = coordination.UpstashCoordination.__new__(coordination.UpstashCoordination)
        self.shared.store = RedisLease(DockerRedis(), "{tel99-test-" + uuid4().hex + "}")

    def test_concurrent_preflight_runs_actual_lua(self):
        self.shared.probe()

    def test_two_native_deliveries_execute_once_on_the_same_request(self):
        namespace = self.shared.store.namespace

        def attempt(_):
            client = coordination.UpstashCoordination.__new__(coordination.UpstashCoordination)
            client.store = RedisLease(DockerRedis(), namespace)
            try:
                with client.claim("CODEX110-EXAMPLE", 112, "approval") as (owner, finish):
                    finish("PREPARED", owner)
                    return 1
            except coordination.CoordinationUnavailable:
                return 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(outcomes), [0, 1])
        self.assertEqual(self.shared.read("codex-windows/CODEX110-EXAMPLE")["status"], "PREPARED")

    def test_closed_worker_can_resume_after_transient_network_failure(self):
        with self.assertRaises(ConnectionError):
            with self.shared.claim("CODE109", 109, "approval") as (owner, _):
                raise ConnectionError("lost worker response")
        record, finish = self.shared.resume("CODE109", 109, "approval", owner)
        self.assertEqual(record["status"], "CLAIMED")
        with patch.object(self.shared.store.transport, "command", side_effect=OSError):
            with self.assertRaises(coordination.CoordinationUnavailable):
                finish("PREPARED", "sha")
        _, finish = self.shared.resume("CODE109", 109, "approval", owner)
        finish("PREPARED", "sha")
        with self.assertRaises(coordination.CoordinationUnavailable):
            with self.shared.claim("CODE109", 109, "approval"):
                self.fail("mission réservée deux fois")

    def test_expired_owner_cannot_update_or_release_after_new_owner(self):
        lease = self.shared.store
        self.assertTrue(lease.acquire("old", 250))
        self.assertTrue(lease.put_cas("claim", {"version": 1}, None, owner="old"))
        deadline = time.monotonic() + 5
        while lease.owns("old") and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(lease.acquire("new", 5000))
        self.assertFalse(lease.release("old"))
        self.assertFalse(lease.put_cas("claim", {"version": 2}, {"version": 1}, owner="old"))
        self.assertFalse(lease.put_cas("claim", {"version": 2}, None, owner="new"))
        self.assertTrue(lease.put_cas("claim", {"version": 2}, {"version": 1}, owner="new"))
