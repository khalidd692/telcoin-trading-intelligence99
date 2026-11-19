"""Redis REST transport for the existing TEL99 coordination interface."""

import json
import re
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class RedisUnavailable(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RedisRest:
    def __init__(self, url, token):
        if not re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\.upstash\.io/?", url):
            raise RedisUnavailable("Origine HTTPS Upstash invalide.")
        if not token or not token.isascii() or not token.isprintable() or any(c.isspace() for c in token):
            raise RedisUnavailable("Jeton REST Upstash invalide.")
        self.url = url.rstrip("/")
        self.token = token
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def fork(self):
        return RedisRest(self.url, self.token)

    def command(self, *args):
        request = Request(
            self.url, data=json.dumps(args).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=12) as reply:
                response = json.loads(reply.read(65537))
            if isinstance(response, dict) and "result" in response and "error" not in response:
                return response["result"]
        except (URLError, OSError, ValueError):
            pass
        raise RedisUnavailable("Réponse Redis REST indisponible ou refusée.")


FENCED_CAS = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
local current = redis.call('GET', KEYS[2])
if ARGV[2] == '' then
  if current then return 0 end
elseif current ~= ARGV[2] then
  return 0
end
redis.call('SET', KEYS[2], ARGV[3])
return 1
"""

RELEASE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""
OWNS = "return redis.call('GET', KEYS[1]) == ARGV[1] and 1 or 0"


class RedisLease:
    def __init__(self, transport, namespace="{tel99-94-windows-v1}"):
        self.transport = transport
        self.namespace = namespace

    def key(self, name):
        return f"{self.namespace}:{name}"

    def acquire(self, owner, ttl_ms=600_000):
        return self.transport.command("SET", self.key("active_mission_lock"), owner, "NX", "PX", ttl_ms) == "OK"

    def owns(self, owner):
        return self.transport.command("EVAL", OWNS, 1, self.key("active_mission_lock"), owner) == 1

    def release(self, owner):
        return self.transport.command("EVAL", RELEASE, 1, self.key("active_mission_lock"), owner) == 1

    def read(self, key):
        value = self.transport.command("GET", self.key(key))
        return None if value is None else json.loads(value)

    def put_cas(self, key, value, expected, *, owner):
        # The owner token changes at every admission. Compare it inside the
        # same server-side operation as the record version/value.
        encode = lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
        previous = "" if expected is None else encode(expected)
        return self.transport.command(
            "EVAL", FENCED_CAS, 2, self.key("active_mission_lock"), self.key(key),
            owner, previous, encode(value),
        ) == 1
