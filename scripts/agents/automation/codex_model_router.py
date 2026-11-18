"""Model routing for approved Codex CLI missions. The caller owns execution and storage."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import json
import queue
import re
import subprocess
from threading import Thread
import time
from types import MappingProxyType


# Use the same standard-speed provider for discovery and new CLI executions.
STANDARD_CONFIG = (
    "-c", 'model_provider="openai"',
    "-c", 'service_tier="default"',
)
EXEC_AUTH = ("-c", 'forced_login_method="chatgpt"')
PROFILES = {
    "routine": ("GPT-6 Luna", "low"),
    "coding": ("GPT-6.2 Sol", "medium"),
    "debug": ("GPT-6.2 Sol", "high"),
    "critical": ("GPT-6.2 Astra", "high"),
}
ASTRA = PROFILES["critical"][0]
SUBSCRIPTION_PLANS = frozenset({"plus", "pro", "prolite", "promax", "team", "business"})
MODEL_SLUG = re.compile(r"gpt-\d+(?:\.\d+)?-(?:luna|sol|astra)")
WINDOWS = {300, 10080}
MAX_QUOTA_AGE_SECONDS = 30


class RouteBlocked(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Policy:
    """Trusted local policy. Fallbacks preserve the profile's reasoning effort."""

    fallbacks: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: {"routine": ("GPT-6.2 Sol",)}
    )
    reserve_percent: int = 10
    max_attempts: int = 3

    def __post_init__(self):
        if type(self.reserve_percent) is not int or not 10 <= self.reserve_percent < 100:
            raise ValueError("The quota reserve must be at least 10 and below 100 percent.")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 3:
            raise ValueError("The attempt limit must be between one and three.")
        for profile, models in self.fallbacks.items():
            if profile not in PROFILES or not isinstance(models, tuple):
                raise ValueError("Each fallback list must be a tuple for a known profile.")
            if any(not isinstance(name, str) or name not in {p[0] for p in PROFILES.values()}
                   for name in models):
                raise ValueError("Fallbacks must use the supported Luna, Sol or Astra names.")
            if profile == "routine" and ASTRA in models:
                raise ValueError("Routine work cannot fall back to Astra.")
        object.__setattr__(self, "fallbacks", MappingProxyType(dict(self.fallbacks)))


@dataclass(frozen=True)
class Snapshot:
    account: dict
    models: tuple[dict, ...]
    limits: dict
    observed_at: float


@dataclass(frozen=True)
class AttemptPlan:
    checkpoint: dict
    exec_args: tuple[str, ...]

    @property
    def attempt(self):
        return self.checkpoint["attempts"][-1]


def _authorize(account_result):
    account = account_result.get("account")
    if (not isinstance(account, dict) or account.get("type") != "chatgpt"
            or account.get("planType") not in SUBSCRIPTION_PLANS):
        raise RouteBlocked("BLOCKED_AUTH", "An eligible ChatGPT subscription was not confirmed.")
    return account["planType"]


@contextmanager
def _app_server(cli, cwd, env):
    """Exchange newline-delimited JSON-RPC over a short-lived metadata connection."""
    with subprocess.Popen(
        [cli, *STANDARD_CONFIG, "app-server"], cwd=cwd, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        encoding="utf-8", errors="replace",
    ) as process:
        lines = queue.Queue()

        def read_lines():
            try:
                for line in process.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        reader = Thread(target=read_lines, daemon=True)
        reader.start()
        deadline = time.monotonic() + 25
        request_id = 0

        def send(message):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        def request(method, params=None):
            nonlocal request_id
            request_id += 1
            status = {
                "account/read": "BLOCKED_AUTH",
                "account/rateLimits/read": "WAITING_QUOTA",
            }.get(method, "BLOCKED_MODEL")
            try:
                message = {"id": request_id, "method": method}
                if params is not None:
                    message["params"] = params
                send(message)
                while time.monotonic() < deadline:
                    line = lines.get(timeout=max(0.0, deadline - time.monotonic()))
                    if line is None:
                        break
                    event = json.loads(line)
                    if isinstance(event, dict) and event.get("id") == request_id:
                        result = event.get("result")
                        if "error" not in event and isinstance(result, dict):
                            return result
                        break
            except (queue.Empty, OSError, ValueError):
                pass
            raise RouteBlocked(status, f"Codex metadata unavailable for {method}.")

        try:
            request("initialize", {"clientInfo": {"name": "tel99-model-router", "version": "1.0"}})
            send({"method": "initialized"})
            yield request
        finally:
            if process.poll() is None:
                process.kill()
            reader.join(timeout=2)


def read_snapshot(cli, cwd, env, *, include_catalog=True):
    """Read account, visible catalog and quota using the caller's scrubbed CLI environment."""
    try:
        with _app_server(cli, cwd, env) as request:
            plan = _authorize(request("account/read", {"refreshToken": False}))
            models = []
            cursor = None
            cursors = set()
            for _ in range(20 if include_catalog else 0):
                page = request("model/list", {"includeHidden": False, "limit": 50, "cursor": cursor})
                entries, cursor = page.get("data"), page.get("nextCursor")
                if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
                    raise RouteBlocked("BLOCKED_MODEL", "Invalid Codex catalog page.")
                models.extend(entries)
                if cursor is None:
                    break
                if not isinstance(cursor, str) or not cursor or cursor in cursors:
                    raise RouteBlocked("BLOCKED_MODEL", "Invalid Codex catalog cursor.")
                cursors.add(cursor)
            else:
                if include_catalog:
                    raise RouteBlocked("BLOCKED_MODEL", "Codex catalog pagination limit reached.")
            limits = request("account/rateLimits/read")
            return Snapshot({"account": {"type": "chatgpt", "planType": plan}},
                            tuple(models), limits, time.time())
    except OSError as exc:
        raise RouteBlocked("BLOCKED_MODEL", "Codex app-server could not be started.") from exc


def _quota(snapshot, model, *, reserve=None):
    plan = _authorize(snapshot.account)
    now = time.time()
    if not 0 <= now - snapshot.observed_at <= MAX_QUOTA_AGE_SECONDS:
        raise RouteBlocked("WAITING_QUOTA", "Codex quota observation is stale.")
    shared = snapshot.limits.get("rateLimits")
    indexed = snapshot.limits.get("rateLimitsByLimitId")
    if not isinstance(shared, dict) or shared.get("limitId") not in (None, "codex"):
        raise RouteBlocked("WAITING_QUOTA", "Shared Codex quota unavailable.")
    if indexed is not None and (not isinstance(indexed, dict)
                                or any(not isinstance(value, dict) for value in indexed.values())):
        raise RouteBlocked("WAITING_QUOTA", "Invalid indexed Codex quota.")
    indexed = indexed or {}
    limits = {"codex": shared}
    if "codex" in indexed and indexed["codex"] != shared:
        raise RouteBlocked("WAITING_QUOTA", "Conflicting shared Codex quota.")
    limits.update({key: value for key, value in indexed.items()
                   if key != "codex" and (key == model or value.get("normalModelSlug") == model)})

    evidence = {}
    for key, limit in limits.items():
        credits = limit.get("credits", shared.get("credits"))
        if not isinstance(credits, dict) or credits.get("hasCredits") is not False or credits.get("unlimited") is not False:
            raise RouteBlocked("WAITING_QUOTA", "Absence of billable credits was not confirmed.")
        if reserve is not None and limit.get("rateLimitReachedType") is not None:
            raise RouteBlocked("WAITING_QUOTA", "Codex reports an exhausted quota.")
        windows = {}
        for field_name in ("primary", "secondary"):
            window = limit.get(field_name)
            if window is None:
                continue
            if not isinstance(window, dict):
                raise RouteBlocked("WAITING_QUOTA", "Invalid Codex quota window.")
            minutes, used, reset = (window.get(field) for field in ("windowDurationMins", "usedPercent", "resetsAt"))
            if (type(minutes) is not int or minutes <= 0 or minutes in windows
                    or type(used) not in (float, int) or not 0 <= used <= 100
                    or (reset is not None and (type(reset) is not int or reset <= 0))):
                raise RouteBlocked("WAITING_QUOTA", "Invalid Codex quota window.")
            if reserve is not None and (used >= 100 - reserve or (reset is not None and reset <= now)):
                raise RouteBlocked("WAITING_QUOTA", "A Codex quota window is stale or at the reserve.")
            windows[minutes] = {"minutes": minutes, "used_percent": used, "resets_at": reset}
        if not windows or (key == "codex" and not WINDOWS.issubset(windows)):
            raise RouteBlocked("WAITING_QUOTA", "Both the five-hour and weekly quota windows are required.")
        evidence[key] = [windows[key] for key in sorted(windows)]
    return {"source": "account/rateLimits/read", "observed_at": snapshot.observed_at,
            "plan": plan, "credits_present": False, "limits": evidence}


def _hash(value, pattern=r"[0-9a-f]{64}"):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def new_checkpoint(task_id, approval_sha256, profile):
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task_id):
        raise ValueError("Invalid task identifier.")
    if profile not in PROFILES or not _hash(approval_sha256):
        raise ValueError("A known profile and approval digest are required.")
    return {"version": 1, "task_id": task_id, "approval_sha256": approval_sha256,
            "profile": profile, "attempts": []}


def _history(checkpoint, approval_sha256):
    if (not isinstance(checkpoint, dict) or checkpoint.get("version") != 1
            or checkpoint.get("approval_sha256") != approval_sha256
            or not _hash(approval_sha256) or checkpoint.get("profile") not in PROFILES
            or not isinstance(checkpoint.get("attempts"), list)):
        raise RouteBlocked("BLOCKED_CHECKPOINT", "Routing checkpoint does not match this approval.")
    attempts = checkpoint["attempts"]
    for number, attempt in enumerate(attempts, 1):
        if (not isinstance(attempt, dict) or attempt.get("number") != number
                or attempt.get("status") not in ("running", "tests_passed", "tests_failed", "worker_error")
                or (number < len(attempts) and attempt["status"] != "tests_failed")
                or (attempt["status"] == "tests_failed" and not _hash(attempt.get("test_evidence_sha256")))):
            raise RouteBlocked("BLOCKED_CHECKPOINT", "Invalid routing attempt history.")
    return attempts


def _compatible(models, display_name, effort):
    # Keep the exact CLI slug from the catalog and reject aliases for speed or other model families.
    expected = display_name.lower().replace(" ", "-")
    for model in models:
        slug = model.get("model")
        efforts = model.get("supportedReasoningEfforts")
        if (model.get("hidden") is False and model.get("displayName") == display_name
                and isinstance(slug, str) and MODEL_SLUG.fullmatch(slug) and slug == expected
                and isinstance(efforts, list)
                and any(isinstance(item, dict) and item.get("reasoningEffort") == effort for item in efforts)):
            return slug
    return None


def prepare_attempt(checkpoint, approval_sha256, base_commit, snapshot, *,
                    policy=None, escalation_evidence_sha256=None):
    """Plan one launch. The returned running checkpoint must be persisted before launching."""
    attempts = _history(checkpoint, approval_sha256)
    if not _hash(base_commit, r"(?:[0-9a-f]{40}|[0-9a-f]{64})"):
        raise ValueError("A full workspace commit hash is required.")
    if policy is None:
        policy = Policy()
    profile = checkpoint["profile"]
    preferred, effort = PROFILES[profile]
    names = (preferred, *policy.fallbacks.get(profile, ()))
    reason = "preferred"
    if attempts:
        last = attempts[-1]
        if last["status"] == "running":
            raise RouteBlocked("RECONCILE_ATTEMPT", "The previous launch may already have run.")
        if last["status"] != "tests_failed" or profile not in ("debug", "critical"):
            raise RouteBlocked("ROUTE_FINISHED", "No further model attempt is authorized.")
        if len(attempts) >= policy.max_attempts:
            raise RouteBlocked("ATTEMPT_LIMIT", "The mission reached its model attempt limit.")
        names = (ASTRA,)
        reason = "confirmed_test_failure"
        if last.get("family") == ASTRA:
            if last.get("effort") != "high" or not _hash(escalation_evidence_sha256):
                raise RouteBlocked("ROUTE_FINISHED", "Extra High requires a documented Astra High test failure.")
            effort = "xhigh"
    _authorize(snapshot.account)
    for name in names:
        slug = _compatible(snapshot.models, name, effort)
        if slug is None or any(a.get("model") == slug and a.get("effort") == effort for a in attempts):
            continue
        before = _quota(snapshot, slug, reserve=policy.reserve_percent)
        attempt = {
            "number": len(attempts) + 1, "status": "running", "base_commit": base_commit,
            "model": slug, "family": name, "effort": effort,
            "reason": "authorized_fallback" if not attempts and name != preferred else reason,
            "quota_before": before, "reserve_percent": policy.reserve_percent,
        }
        if effort == "xhigh":
            attempt["escalation_evidence_sha256"] = escalation_evidence_sha256
        updated = deepcopy(checkpoint)
        updated["attempts"].append(attempt)
        return AttemptPlan(updated, ("--model", slug, "-c", f'model_reasoning_effort="{effort}"',
                                    *STANDARD_CONFIG, *EXEC_AUTH, "--json"))
    raise RouteBlocked("BLOCKED_MODEL", "No authorized model supports the selected reasoning effort.")


def _exec_usage(exec_jsonl, effective_settings):
    thread_id = None
    terminal = None
    tokens = None
    for line in exec_jsonl.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started":
            value = event.get("thread_id")
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
                thread_id = value
        if event.get("type") in ("turn.completed", "turn.failed"):
            terminal = event["type"]
            tokens = None
            usage = event.get("usage")
            keys = ("input_tokens", "cached_input_tokens", "output_tokens")
            if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in keys):
                if usage["cached_input_tokens"] <= usage["input_tokens"]:
                    tokens = {key: usage[key] for key in keys}
    return {"source": "codex exec --json", "thread_id": thread_id, "terminal_event": terminal,
            "tokens": tokens, "effective_settings": effective_settings}


def record_result(checkpoint, approval_sha256, number, status, *, duration_ms,
                  artifact_sha256=None, test_evidence_sha256=None, quota_after=None, exec_jsonl="",
                  effective_settings=None):
    """Close the pending attempt with independent verification and observed CLI metadata."""
    attempts = _history(checkpoint, approval_sha256)
    if not attempts or attempts[-1]["number"] != number or attempts[-1]["status"] != "running":
        raise RouteBlocked("BLOCKED_CHECKPOINT", "Result does not match the pending model attempt.")
    if status not in {"tests_passed", "tests_failed", "worker_error"}:
        raise ValueError("Unknown attempt result.")
    if type(duration_ms) is not int or duration_ms < 0:
        raise ValueError("Duration must be a non-negative number of milliseconds.")
    if status != "worker_error" and not (_hash(test_evidence_sha256) and _hash(artifact_sha256)):
        raise ValueError("Test verdicts require both independent test and artifact digests.")
    if any(value is not None and not _hash(value) for value in (artifact_sha256, test_evidence_sha256)):
        raise ValueError("Invalid result evidence digest.")
    updated = deepcopy(checkpoint)
    attempt = updated["attempts"][-1]
    after = None
    after_status = "unavailable"
    if quota_after is not None:
        try:
            after = _quota(quota_after, attempt["model"])
            before = attempt["quota_before"]
            if after["observed_at"] <= before["observed_at"] or after["plan"] != before["plan"]:
                after = None
            else:
                after_status = "observed"
        except RouteBlocked as exc:
            after_status = exc.status
    if effective_settings is not None:
        observed_model = effective_settings.get("model", "")
        observed_effort = effective_settings.get("effort")
        source_sha256 = effective_settings.get("source_sha256")
        if (not isinstance(observed_model, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", observed_model)
                or not isinstance(observed_effort, str) or not re.fullmatch(r"[a-z_]{1,24}", observed_effort)
                or not _hash(source_sha256)):
            raise ValueError("Effective settings require observed model, effort and source digest.")
        effective_settings = {"model": observed_model, "effort": observed_effort, "source_sha256": source_sha256}
        if (observed_model, observed_effort) != (attempt["model"], attempt["effort"]):
            status = "worker_error"
    attempt.update(status=status, duration_ms=duration_ms, quota_after=after, quota_after_status=after_status,
                   test_evidence_sha256=test_evidence_sha256, artifact_sha256=artifact_sha256,
                   cli_usage=_exec_usage(exec_jsonl, effective_settings))
    return updated
