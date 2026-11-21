"""Model routing for approved Codex CLI missions. The caller owns execution and storage."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import os
import re
import subprocess
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
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SPEED_ALIAS = re.compile(r"(?:^|[_.-])(?:fast|ultrafast|priority)(?:$|[_.-])", re.I)
FAMILIES = frozenset(name for name, _ in PROFILES.values())
EFFORTS = ("low", "medium", "high", "xhigh")
COMMIT = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
WINDOWS = {300, 10080}
MAX_QUOTA_AGE_SECONDS = 30
METADATA_TIMEOUT_SECONDS = 25
MAX_METADATA_LINE_BYTES = 512 * 1024
MODEL_PAGE_SIZE = 50
MAX_MODEL_CURSOR_CHARS = 1024


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
            if any(not isinstance(name, str) or name not in FAMILIES
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
    account = account_result.get("account") if isinstance(account_result, dict) else None
    plan = account.get("planType") if isinstance(account, dict) else None
    if (not isinstance(account, dict) or account.get("type") != "chatgpt"
            or not isinstance(plan, str) or plan not in SUBSCRIPTION_PLANS
            or account_result.get("requiresOpenaiAuth", True) is not True):
        raise RouteBlocked("BLOCKED_AUTH", "An eligible ChatGPT subscription was not confirmed.")
    return plan


@contextmanager
def _app_server(cli, cwd, env):
    """Exchange newline-delimited JSON-RPC over a short-lived metadata connection."""
    with subprocess.Popen(
        [cli, *STANDARD_CONFIG, "app-server"], cwd=cwd, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        bufsize=0,
    ) as process:
        stdout = process.stdout.fileno()
        stdin = process.stdin.fileno()
        pending = bytearray()
        deadline = time.monotonic() + METADATA_TIMEOUT_SECONDS
        request_id = 0

        def send(message):
            data = memoryview((json.dumps(message) + "\n").encode("ascii"))
            while data and time.monotonic() < deadline:
                try:
                    written = os.write(stdin, data)
                except BlockingIOError:
                    written = 0
                if written:
                    data = data[written:]
                else:
                    time.sleep(0.01)
            if data:
                raise TimeoutError("Codex metadata write deadline reached.")

        def receive(status, method):
            while time.monotonic() < deadline:
                end = pending.find(b"\n")
                if end >= 0:
                    line = bytes(pending[:end])
                    del pending[:end + 1]
                    return line
                if len(pending) > MAX_METADATA_LINE_BYTES:
                    raise RouteBlocked(status, f"Codex metadata frame exceeds the size limit for {method}.")
                capacity = MAX_METADATA_LINE_BYTES + 1 - len(pending)
                try:
                    chunk = os.read(stdout, min(65536, capacity))
                except BlockingIOError:
                    time.sleep(0.01)
                    continue
                if not chunk:
                    line = bytes(pending) or None
                    pending.clear()
                    return line
                pending.extend(chunk)
            return None

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
                    line = receive(status, method)
                    if line is None:
                        break
                    event = json.loads(line.decode("utf-8"))
                    if not isinstance(event, dict):
                        raise RouteBlocked(status, f"Codex metadata frame is not a JSON object for {method}.")
                    if request_id > 2 and event.get("method") == "account/updated":
                        update = event.get("params")
                        if not isinstance(update, dict) or update.get("authMode") != "chatgpt":
                            raise RouteBlocked("BLOCKED_AUTH", "Codex authentication changed during discovery.")
                    if type(event.get("id")) is int and event["id"] == request_id:
                        result = event.get("result")
                        if "error" not in event and isinstance(result, dict):
                            return result
                        break
            except (OSError, ValueError, RecursionError):
                pass
            raise RouteBlocked(status, f"Codex metadata unavailable for {method}.")

        try:
            # Python 3.12 supports nonblocking pipes on Windows as well as POSIX.
            try:
                os.set_blocking(stdout, False)
                os.set_blocking(stdin, False)
            except (AttributeError, OSError) as exc:
                raise RouteBlocked("BLOCKED_MODEL", "Nonblocking Codex metadata pipes unavailable.") from exc
            request("initialize", {"clientInfo": {"name": "tel99-model-router", "version": "1.0"}})
            send({"method": "initialized"})
            yield request
        finally:
            if process.poll() is None:
                process.kill()


def read_snapshot(cli, cwd, env, *, include_catalog=True):
    """Read account, visible catalog and quota using the caller's scrubbed CLI environment."""
    try:
        with _app_server(cli, cwd, env) as request:
            plan = _authorize(request("account/read", {"refreshToken": False}))
            models = []
            cursor = None
            cursors = set()
            for _ in range(20 if include_catalog else 0):
                page = request("model/list", {
                    "includeHidden": False, "limit": MODEL_PAGE_SIZE, "cursor": cursor,
                    "modelProvider": "openai",
                })
                entries, cursor = page.get("data"), page.get("nextCursor")
                if (not isinstance(entries, list) or len(entries) > MODEL_PAGE_SIZE
                        or any(not isinstance(item, dict) for item in entries)):
                    raise RouteBlocked("BLOCKED_MODEL", "Invalid Codex catalog page.")
                models.extend(entries)
                if cursor is None:
                    break
                if (not isinstance(cursor, str) or not 1 <= len(cursor) <= MAX_MODEL_CURSOR_CHARS
                        or cursor in cursors):
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
    if (type(snapshot.observed_at) not in (float, int)
            or not 0 <= now - snapshot.observed_at <= MAX_QUOTA_AGE_SECONDS):
        raise RouteBlocked("WAITING_QUOTA", "Codex quota observation is stale.")
    if not isinstance(snapshot.limits, dict):
        raise RouteBlocked("WAITING_QUOTA", "Codex quota is unavailable.")
    shared = snapshot.limits.get("rateLimits")
    indexed = snapshot.limits.get("rateLimitsByLimitId")
    if not isinstance(shared, dict) or shared.get("limitId") not in (None, "codex"):
        raise RouteBlocked("WAITING_QUOTA", "Shared Codex quota unavailable.")
    if indexed is not None and (not isinstance(indexed, dict) or any(
        not isinstance(key, str) or not SAFE_ID.fullmatch(key)
        or not isinstance(value, dict) or value.get("limitId") not in (None, key)
        or (value.get("normalModelSlug") is not None and
            (not isinstance(value["normalModelSlug"], str) or not SAFE_ID.fullmatch(value["normalModelSlug"])))
        for key, value in indexed.items()
    )):
        raise RouteBlocked("WAITING_QUOTA", "Invalid indexed Codex quota.")
    indexed = indexed or {}
    shared_credits = shared.get("credits")
    evidence = {"codex": _quota_windows(shared, plan, now, reserve, shared_credits, shared=True)}
    for key, limit in indexed.items():
        if key != "codex" and key != model and limit.get("normalModelSlug") not in (None, model):
            continue
        windows = _quota_windows(limit, plan, now, reserve, shared_credits, shared=key == "codex")
        if key == "codex" and windows != evidence[key]:
            raise RouteBlocked("WAITING_QUOTA", "Conflicting shared Codex quota windows.")
        evidence[key] = windows
    return {"source": "account/rateLimits/read", "observed_at": snapshot.observed_at,
            "plan": plan, "credits_present": False, "limits": evidence}


def _quota_windows(limit, plan, now, reserve, shared_credits, *, shared):
    credits = limit.get("credits")
    if credits is None:
        credits = shared_credits
    if (not isinstance(credits, dict) or credits.get("hasCredits") is not False
            or credits.get("unlimited") is not False or limit.get("planType") not in (None, plan)):
        raise RouteBlocked("WAITING_QUOTA", "Inclusion in the verified ChatGPT quota was not confirmed.")
    spend_reached = limit.get("spendControlReached")
    if spend_reached is not None and type(spend_reached) is not bool:
        raise RouteBlocked("WAITING_QUOTA", "Invalid Codex spend-control status.")
    if reserve is not None and (limit.get("rateLimitReachedType") is not None or spend_reached):
        raise RouteBlocked("WAITING_QUOTA", "Codex reports a quota or spend-control limit.")
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
    if not windows or (shared and not WINDOWS.issubset(windows)):
        raise RouteBlocked("WAITING_QUOTA", "Required Codex quota windows are missing.")
    return [windows[key] for key in sorted(windows)]


def _hash(value, pattern=r"[0-9a-f]{64}"):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def new_checkpoint(task_id, approval_sha256, profile):
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task_id):
        raise ValueError("Invalid task identifier.")
    if not isinstance(profile, str) or profile not in PROFILES or not _hash(approval_sha256):
        raise ValueError("A known profile and approval digest are required.")
    return {"version": 1, "task_id": task_id, "approval_sha256": approval_sha256,
            "profile": profile, "attempts": []}


def _history(checkpoint, approval_sha256):
    if (not isinstance(checkpoint, dict) or type(checkpoint.get("version")) is not int
            or checkpoint["version"] != 1 or not _hash(checkpoint.get("task_id"), r"[A-Za-z0-9_-]{1,64}")
            or checkpoint.get("approval_sha256") != approval_sha256
            or not isinstance(checkpoint.get("profile"), str)
            or not _hash(approval_sha256) or checkpoint.get("profile") not in PROFILES
            or not isinstance(checkpoint.get("attempts"), list)):
        raise RouteBlocked("BLOCKED_CHECKPOINT", "Routing checkpoint does not match this approval.")
    attempts = checkpoint["attempts"]
    profile = checkpoint["profile"]
    pairs = set()
    if len(attempts) > 3:
        raise RouteBlocked("BLOCKED_CHECKPOINT", "Invalid routing attempt history.")
    for number, attempt in enumerate(attempts, 1):
        if (not isinstance(attempt, dict) or type(attempt.get("number")) is not int or attempt["number"] != number
                or attempt.get("status") not in ("running", "tests_passed", "tests_failed", "worker_error")
                or not _hash(attempt.get("model"), SAFE_ID)
                or not _hash(attempt.get("base_commit"), COMMIT)
                or attempt.get("family") not in tuple(FAMILIES) or attempt.get("effort") not in EFFORTS
                or not isinstance(attempt.get("quota_before"), dict)
                or type(attempt["quota_before"].get("observed_at")) not in (int, float)
                or not math.isfinite(attempt["quota_before"]["observed_at"])
                or attempt["quota_before"].get("plan") not in tuple(SUBSCRIPTION_PLANS)
                or (number < len(attempts) and attempt["status"] != "tests_failed")
                or (attempt["status"] in ("tests_failed", "tests_passed") and
                    not (_hash(attempt.get("test_evidence_sha256")) and _hash(attempt.get("artifact_sha256"))))):
            raise RouteBlocked("BLOCKED_CHECKPOINT", "Invalid routing attempt history.")
        pair = (attempt["model"], attempt["effort"])
        if pair in pairs:
            raise RouteBlocked("BLOCKED_CHECKPOINT", "Repeated model and effort in the checkpoint.")
        pairs.add(pair)
        if number == 1:
            if attempt["effort"] != PROFILES[profile][1] or (profile == "routine" and attempt["family"] == ASTRA):
                raise RouteBlocked("BLOCKED_CHECKPOINT", "Initial attempt does not match the approved profile.")
            continue
        previous = attempts[number - 2]
        from_astra = previous["family"] == ASTRA
        if (profile not in ("debug", "critical") or attempt["family"] != ASTRA
                or attempt["effort"] != ("xhigh" if from_astra else "high")
                or (from_astra and (previous["effort"] != "high" or previous["model"] != attempt["model"]
                                    or not _hash(attempt.get("escalation_evidence_sha256"))))):
            raise RouteBlocked("BLOCKED_CHECKPOINT", "Attempt history contains an invalid escalation.")
    return attempts


def _compatible(models, display_name, effort):
    # The display label selects a family. Only the server's model field supplies the CLI ID.
    if not isinstance(models, (tuple, list)) or any(not isinstance(model, dict) for model in models):
        raise RouteBlocked("BLOCKED_MODEL", "Invalid Codex model catalog.")
    candidates = set()
    for model in models:
        label = model.get("displayName")
        # App Server 0.170.0 displays the tier with a hyphen on some accounts.
        hyphen_label = display_name.replace(" ", "-")
        if label not in (display_name, hyphen_label) or model.get("hidden") is not False:
            continue
        slug = model.get("model")
        efforts = model.get("supportedReasoningEfforts")
        if (not _hash(slug, SAFE_ID) or SPEED_ALIAS.search(slug)
                or model.get("availabilityNux") is not None
                or model.get("defaultServiceTier") not in (None, "default")
                or not isinstance(efforts, list)
                or not any(isinstance(item, dict) and item.get("reasoningEffort") == effort for item in efforts)):
            continue
        if any(other.get("model") == slug and any(
            other.get(key) != model.get(key)
            for key in ("displayName", "hidden", "supportedReasoningEfforts", "availabilityNux", "defaultServiceTier")
        ) for other in models):
            raise RouteBlocked("BLOCKED_MODEL", "Conflicting entries for a Codex model.")
        candidates.add(slug)
    if len(candidates) > 1:
        raise RouteBlocked("BLOCKED_MODEL", "Several catalog IDs match the same routing family and effort.")
    return next(iter(candidates), None)


def prepare_attempt(checkpoint, approval_sha256, base_commit, snapshot, *,
                    policy=None, escalation_evidence_sha256=None):
    """Plan one launch. The returned running checkpoint must be persisted before launching."""
    attempts = _history(checkpoint, approval_sha256)
    if not _hash(base_commit, COMMIT):
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
        if effort == "xhigh" and slug != attempts[-1]["model"]:
            raise RouteBlocked("BLOCKED_MODEL", "Astra's model ID changed since the verified High failure.")
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


def prepare_exec(argv, checkpoint, approval_sha256, base_commit, snapshot, persist, **route_options):
    """Return the existing worker command with routing args after durable caller persistence."""
    tokens = list(argv[1:-1])
    if (argv[-1:] not in (["-"], ("-",)) or "exec" not in tokens or "--ignore-user-config" not in tokens
            or any(arg in tokens for arg in ("--", "resume", "--oss", "--fast", "--json", "--experimental-json"))):
        raise ValueError("An unrouted codex exec command reading stdin is required.")
    routing_keys = {"model", "model_reasoning_effort", "model_provider", "service_tier",
                    "forced_login_method", "chatgpt_base_url"}
    for index, arg in enumerate(tokens):
        if arg.split("=", 1)[0] in ("--model", "--profile") or arg.startswith(("-m", "-p")):
            raise ValueError("Existing model or profile override.")
        if arg in ("-c", "--config"):
            config = tokens[index + 1] if index + 1 < len(tokens) else ""
        elif arg.startswith("--config="):
            config = arg.removeprefix("--config=")
        elif arg.startswith("-c") and not arg.startswith("--"):
            config = arg.removeprefix("-c").lstrip("=")
        else:
            continue
        key, separator, _ = config.partition("=")
        if not separator or key.strip().strip("'\"") in routing_keys:
            raise ValueError("Missing config assignment or existing routing override.")
    plan = prepare_attempt(checkpoint, approval_sha256, base_commit, snapshot, **route_options)
    persist(deepcopy(plan.checkpoint))
    return plan, [*argv[:-1], *plan.exec_args, "-"]


def _exec_usage(exec_jsonl, effective_settings):
    observation = {"source": "codex exec --json", "thread_id": None,
                   "terminal_event": None, "tokens": None, "effective_settings": effective_settings}
    thread_id = None
    terminal = None
    tokens = None
    ambiguous = False
    for line in exec_jsonl.split("\n"):
        if not line.strip(" \t\r"):
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            return observation
        if not isinstance(event, dict):
            return observation
        if event.get("type") == "thread.started":
            value = event.get("thread_id")
            if (not _hash(value, r"[A-Za-z0-9_-]{1,128}") or terminal is not None
                    or (thread_id is not None and thread_id != value)):
                return observation
            thread_id = value
        if event.get("type") in ("turn.completed", "turn.failed"):
            ambiguous |= terminal is not None
            terminal = event["type"]
            tokens = None
            usage = event.get("usage")
            keys = ("input_tokens", "cached_input_tokens", "output_tokens")
            if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in keys):
                if usage["cached_input_tokens"] <= usage["input_tokens"]:
                    tokens = {key: usage[key] for key in keys}
    observation["thread_id"] = thread_id
    if not ambiguous:
        observation.update(terminal_event=terminal, tokens=tokens)
    return observation


def record_result(checkpoint, approval_sha256, number, status, *, duration_ms,
                  artifact_sha256=None, test_evidence_sha256=None, quota_after=None, exec_jsonl="",
                  effective_settings=None):
    """Close the pending attempt with independent verification and observed CLI metadata."""
    attempts = _history(checkpoint, approval_sha256)
    if not attempts or attempts[-1]["number"] != number or attempts[-1]["status"] != "running":
        raise RouteBlocked("BLOCKED_CHECKPOINT", "Result does not match the pending model attempt.")
    if status not in ("tests_passed", "tests_failed", "worker_error"):
        raise ValueError("Unknown attempt result.")
    if type(duration_ms) is not int or duration_ms < 0:
        raise ValueError("Duration must be a non-negative number of milliseconds.")
    if not isinstance(exec_jsonl, str):
        raise ValueError("CLI evidence must be decoded JSONL text.")
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
        if not isinstance(effective_settings, dict):
            raise ValueError("Effective settings must be a mapping.")
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
