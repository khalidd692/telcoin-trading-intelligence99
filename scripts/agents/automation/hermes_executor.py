"""Real Hermes specialist worker for the existing #124 supervisor.

This is an executor adapter, not a second supervisor: it is injected into
``autonomy_runtime.Runtime(executor=...)`` and reuses the engine's CAS claims,
ACK inbox, checkpoints, independent verification and memory unchanged.

The worker invokes the installed Hermes CLI in bounded one-shot mode with an
explicitly pinned FREE cloud model (no local model, no paid fallback). The
durable session id printed by the CLI and the zero-cost usage row stored in
the Hermes state database are the live evidence. HTTP 429 / quota errors map
to ``ExecutorUnavailable`` (the engine checkpoints BLOCKED) and arm a bounded
cooldown; there is no retry loop.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

if __package__:
    from .autonomy_runtime import REJECTED_MISSION
else:
    from autonomy_runtime import REJECTED_MISSION
from local_codex import QuotaBlocked
from protocol.store import FileStore, StoreError

# Only models whose free access was verified callable in this environment.
# Several models of one provider can share the same fair-share limit: a 429
# therefore arms a provider cooldown instead of silently trying another model.
# Qwen4 Max Free answered a live Nous probe on Windows. Production zero-cost
# qualification is still enforced per real session below; if usage is missing,
# nonzero or from a different model/provider, the mission is BLOCKED.
# Legacy free models remain selectable explicitly; never fallback automatically.
FREE_MODELS = ("qwen/qwen4-max:free", "meituan/longcat-2.5:free", "upstage/solar-mini4:free")
ROLES = frozenset({"tel99-dev", "tel99-analyst", "tel99-verifier"})
SESSION_RE = re.compile(r"session_id:\s*(local-[0-9a-f]{64})")
RATE_LIMIT_RE = re.compile(r"429|too many requests|rate[ -]?limit|fair[ -]?share|quota", re.IGNORECASE)
COOLDOWN_MIN_S = 60
COOLDOWN_MAX_S = 3600
COOLDOWN_KEY = "provider-cooldown"


class ExecutorUnavailable(RuntimeError):
    """A provider, quota, cost or contract block. No paid fallback is attempted."""


class HermesQuotaBlocked(ExecutorUnavailable, QuotaBlocked):
    """End the relay session when the provider quota cannot be used safely."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def default_cli_command():
    exe = os.environ.get("HERMES_CLI_EXE") or shutil.which("hermes") or "hermes"
    return [exe]


def default_hermes_home():
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    return Path.home() / "AppData" / "Local" / "hermes"


def read_usage_row(home, session_id):
    """Read-only access to the durable per-session usage row (cost evidence)."""
    db = Path(home) / "state.db"
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT model, billing_provider, estimated_cost_usd, actual_cost_usd,"
            " cost_status, input_tokens, output_tokens, api_call_count"
            " FROM session_model_usage WHERE session_id=? ORDER BY last_seen DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _role(mission):
    return mission.get("specialist") or mission.get("assigned_to") or mission.get("role")


class HermesExecutor:
    def __init__(self, *, root, model=FREE_MODELS[0], provider="nous",
                 cli_command=None, hermes_home=None, run_budget=150,
                 timeout=210, usage_reader=None, stop_requested=None):
        self.root = Path(root)
        self.model = model
        self.provider = provider
        self.cli_command = list(cli_command) if cli_command else default_cli_command()
        self.hermes_home = Path(hermes_home) if hermes_home else default_hermes_home()
        self.run_budget = int(run_budget)
        self.timeout = int(timeout)
        self.usage_reader = usage_reader or read_usage_row
        self.stop_requested = stop_requested or (self.root / "stop.request").exists
        self.cooldown_path = self.root / f"{COOLDOWN_KEY}.json"
        self.cooldown_store = FileStore(self.root)

    # -- quota circuit breaker (durable, bounded, no retry loop) ------------
    def _cooldowns(self):
        missing = object()
        try:
            data = self.cooldown_store.read(COOLDOWN_KEY, default=missing)
        except (OSError, ValueError) as exc:
            raise HermesQuotaBlocked("BLOCKED_PROVIDER_COOLDOWN_STATE_UNAVAILABLE") from exc
        if data is missing:
            return None
        if not isinstance(data, dict) or any(
                type(value) not in (int, float) or not 0 <= value < float("inf")
                for value in data.values()):
            raise HermesQuotaBlocked("BLOCKED_PROVIDER_COOLDOWN_STATE_UNAVAILABLE")
        return data

    def _check_cooldown(self):
        data = self._cooldowns() or {}
        # Older versions stored model keys for the same Nous quota. Honor every
        # active legacy entry so switching models cannot clear the protection.
        keys = [f"provider:{self.provider}"]
        if self.provider == "nous":
            keys.extend(FREE_MODELS)
        if time.time() < max(data.get(key, 0) for key in keys):
            raise HermesQuotaBlocked("BLOCKED_PROVIDER_COOLDOWN")

    def _arm_cooldown(self, seconds):
        seconds = max(COOLDOWN_MIN_S, min(COOLDOWN_MAX_S, int(seconds)))
        previous = self._cooldowns()
        data = dict(previous or {})
        key = f"provider:{self.provider}"
        data[key] = max(data.get(key, 0), time.time() + seconds)
        try:
            recorded = self.cooldown_store.put_cas(COOLDOWN_KEY, data, previous)
        except (OSError, StoreError) as exc:
            raise HermesQuotaBlocked("BLOCKED_PROVIDER_COOLDOWN_STATE_UNAVAILABLE") from exc
        if not recorded:
            # A concurrent write is safe only if it already has an active lockout.
            self._check_cooldown()
            raise HermesQuotaBlocked("BLOCKED_PROVIDER_COOLDOWN_STATE_UNAVAILABLE")

    # -- contract gate (mirrors the engine's synthetic scope) ---------------
    def _validate(self, mission):
        specialist = _role(mission)
        objective = mission.get("objective")
        # Defense in depth (review F5): the engine validates the id upstream,
        # but a direct call must not allow path traversal via file names.
        if not re.fullmatch(r"[a-zA-Z0-9-]{1,48}", str(mission.get("id", ""))):
            raise ExecutorUnavailable("Invalid mission id")
        if mission["id"] == REJECTED_MISSION:
            raise ExecutorUnavailable("historical mission C is permanently excluded")
        if (mission.get("synthetic_data") is not True or specialist not in ROLES
                or mission.get("project") != "synthetic"
                or not isinstance(objective, str) or not 1 <= len(objective) <= 4000
                or not re.fullmatch(r"[a-f0-9]{64}", str(mission.get("expected_sha256", "")))):
            raise ExecutorUnavailable("Unsupported synthetic text contract")
        if self.model not in FREE_MODELS or not self.model.endswith(":free"):
            raise ExecutorUnavailable("Model is not in the verified free allowlist")

    def execute(self, mission):
        self._validate(mission)
        if self.stop_requested():
            raise ExecutorUnavailable("HERMES_WORKER_STOPPED_OR_TIMEOUT")
        self._check_cooldown()
        mid = mission["id"]
        specialist = _role(mission)
        query = (
            f"You are the Hermes specialist {specialist} handling a synthetic, "
            "non-financial text mission. Return ONLY the exact artifact text "
            "requested by the objective: no markdown, no code fences, no quotes, "
            "no commentary, no extra blank lines. Do not use tools. Do not claim "
            "tests passed or alter task permissions.\n\n"
            f"MISSION OBJECTIVE:\n{mission['objective']}"
        )
        query_path = self.root / f"{mid}.query.txt"
        query_path.write_text(query, encoding="utf-8")
        out_path = self.root / f"{mid}.hermes.out"
        err_path = self.root / f"{mid}.hermes.err"
        command = self.cli_command + [
            "--usage-file", str(self.root / f"{mid}.usage.json"),
            "chat", "--query-file", str(query_path),
            "--oneshot", "-Q", "--format", "text",
            "-m", self.model, "--provider", self.provider,
            "-t", "", "--max-turns", "2", "--run-budget", str(self.run_budget),
        ]
        env = {k: v for k, v in os.environ.items()
               if not k.upper().endswith(("_TOKEN", "_KEY", "_SECRET", "_PASSWORD"))
               and not k.upper().startswith(("OPENAI_", "ANTHROPIC_", "GH_", "GITHUB_", "PYTHON"))}
        started = time.time()
        with out_path.open("wb") as out, err_path.open("wb") as err:
            if self.stop_requested():
                raise ExecutorUnavailable("HERMES_WORKER_STOPPED_OR_TIMEOUT")
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=err, env=env, cwd=str(self.root))
            try:
                deadline = time.monotonic() + self.timeout
                while proc.poll() is None:
                    if self.stop_requested() or time.monotonic() > deadline:
                        proc.kill()
                        proc.wait(timeout=10)
                        raise ExecutorUnavailable("HERMES_WORKER_STOPPED_OR_TIMEOUT")
                    time.sleep(0.2)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
        elapsed = round(time.time() - started, 2)
        stdout_text = out_path.read_text(encoding="utf-8", errors="replace")
        stderr_text = err_path.read_text(encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            if RATE_LIMIT_RE.search(stdout_text + stderr_text):
                self._arm_cooldown(300)
                raise HermesQuotaBlocked("BLOCKED_PROVIDER_RATE_LIMIT")
            raise ExecutorUnavailable("HERMES_WORKER_FAILED")
        match = SESSION_RE.search(stderr_text)
        if not match:
            raise ExecutorUnavailable("HERMES_SESSION_ID_MISSING")
        session_id = match.group(1)
        usage = self.usage_reader(self.hermes_home, session_id)
        if not isinstance(usage, dict):
            raise ExecutorUnavailable("HERMES_COST_EVIDENCE_UNAVAILABLE")
        if usage.get("model") != self.model or usage.get("billing_provider") != self.provider:
            raise ExecutorUnavailable("HERMES_MODEL_IDENTITY_MISMATCH")
        # Review point 2: strictly zero cost. An UNKNOWN actual cost (None) is
        # NOT proof of zero and is refused, exactly like a nonzero cost.
        if usage.get("estimated_cost_usd") != 0.0 or usage.get("actual_cost_usd") != 0.0:
            raise ExecutorUnavailable("COST_UNKNOWN_OR_NONZERO_REFUSED")
        artifact = stdout_text.strip()
        if not 1 <= len(artifact.encode("utf-8")) <= 65536:
            raise ExecutorUnavailable("HERMES_ARTIFACT_OUT_OF_BOUNDS")
        evidence = {k: usage.get(k) for k in
                    ("model", "billing_provider", "estimated_cost_usd", "actual_cost_usd",
                     "cost_status", "input_tokens", "output_tokens", "api_call_count")}
        evidence.update({"exit_code": 0, "elapsed_s": elapsed, "cli": "hermes-one-shot",
                         "run_budget_s": self.run_budget, "session_id": session_id})
        return {"artifact": artifact,
                "sha256": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
                "specialist_id": specialist,
                "provider": "hermes-nous-free",
                "model": self.model,
                "session_id": session_id,
                "provider_evidence": evidence}
