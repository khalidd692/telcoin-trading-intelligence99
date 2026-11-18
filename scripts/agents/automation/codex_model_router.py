"""Pure, fail-closed routing for an APPROVED Codex local mission.

No process is spawned by select_route. The Windows supervisor remains the only
owner of admission, CAS, workspace, quota re-check and codex exec.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

POLICY_PATH = Path(__file__).with_name("codex_model_policy.json")
SHA = re.compile(r"^[0-9a-f]{40}$")
EFFORTS = ("low", "medium", "high", "xhigh")


class RoutingBlocked(RuntimeError):
    """Fail closed; never start a model with ambiguous entitlements or quota."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Route:
    model: str
    effort: str
    tier: str
    attempt: int
    reason: str

    def cli_args(self) -> list[str]:
        # Pass as argv elements, not shell text. CLI authentication and sandbox
        # remain the responsibility of the existing supervisor.
        return ["--model", self.model, "-c", f"model_reasoning_effort={self.effort}"]

    def evidence(self) -> dict:
        return {"model": self.model, "effort": self.effort,
                "tier": self.tier, "attempt": self.attempt, "reason": self.reason}


def load_policy(path: Path = POLICY_PATH) -> dict:
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("schema") != 1:
        raise RoutingBlocked("BLOCKED_POLICY")
    if type(policy.get("max_attempts")) is not int or not 1 <= policy["max_attempts"] <= 3:
        raise RoutingBlocked("BLOCKED_POLICY")
    if type(policy.get("quota_reserve_percent")) is not int or not 10 <= policy["quota_reserve_percent"] <= 50:
        raise RoutingBlocked("BLOCKED_POLICY")
    for tier in ("small", "normal", "hard", "critical", "escalated", "last_resort"):
        choices = policy.get("routes", {}).get(tier)
        if not isinstance(choices, list) or not choices:
            raise RoutingBlocked("BLOCKED_POLICY")
        for choice in choices:
            if (not isinstance(choice, dict) or not isinstance(choice.get("model"), str)
                    or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{3,60}", choice["model"])
                    or choice.get("effort") not in EFFORTS):
                raise RoutingBlocked("BLOCKED_POLICY")
    return policy


def classify(mission: dict) -> str:
    """Only approved, structured mission metadata is considered, not prompt text."""
    if not isinstance(mission, dict) or not isinstance(mission.get("id"), str):
        raise RoutingBlocked("BLOCKED_MISSION")
    declared = mission.get("complexity")
    if declared is not None:
        if declared not in ("small", "normal", "hard", "critical"):
            raise RoutingBlocked("BLOCKED_MISSION")
        return declared
    paths = mission.get("files", [])
    if not isinstance(paths, list) or not all(isinstance(x, str) for x in paths):
        raise RoutingBlocked("BLOCKED_MISSION")
    # Security and distributed coordination require stronger reasoning, even
    # when an untrusted issue describes the job as 'easy'.
    if any(re.search(r"(^|/)(security|auth|local_coordination|cas|permissions)([/. _-]|$)", p.lower()) for p in paths):
        return "critical"
    if mission.get("kind") == "code":
        return "hard" if mission.get("priority") == "P0" else "normal"
    return "small"


def model_catalog(pages: list[dict]) -> dict[str, frozenset[str]]:
    """Consume complete model/list pages; hidden, malformed or duplicate IDs block."""
    if not isinstance(pages, list) or not pages:
        raise RoutingBlocked("BLOCKED_MODEL")
    models = {}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("data"), list):
            raise RoutingBlocked("BLOCKED_MODEL")
        for item in page["data"]:
            if not isinstance(item, dict) or item.get("hidden") is True:
                continue
            model = item.get("model")
            if not isinstance(model, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{3,60}", model):
                raise RoutingBlocked("BLOCKED_MODEL")
            efforts = item.get("supportedReasoningEfforts")
            if not isinstance(efforts, list) or not efforts:
                raise RoutingBlocked("BLOCKED_MODEL")
            allowed = frozenset(
                e.get("reasoningEffort") for e in efforts if isinstance(e, dict)
                and e.get("reasoningEffort") in EFFORTS
            )
            if not allowed or model in models or item.get("id") not in (None, model):
                raise RoutingBlocked("BLOCKED_MODEL")
            models[model] = allowed
    if not models:
        raise RoutingBlocked("BLOCKED_MODEL")
    return models


def check_quota(snapshot: dict, reserve: int) -> dict:
    """Require explicit 5-hour AND weekly quota windows and no billable credits.

    If the server does not expose the window for the relevant model, stop. The
    caller also checks the quota before each retry and immediately after exec.
    """
    if not isinstance(snapshot, dict):
        raise RoutingBlocked("WAITING_QUOTA")
    credits = snapshot.get("credits")
    if not isinstance(credits, dict) or credits.get("hasCredits") is not False or credits.get("unlimited") is not False:
        raise RoutingBlocked("WAITING_QUOTA")
    buckets = snapshot.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict) or not buckets:
        single = snapshot.get("rateLimits")
        buckets = {"single": single} if isinstance(single, dict) else {}
    if not buckets:
        raise RoutingBlocked("WAITING_QUOTA")
    rows = {}
    for name, bucket in buckets.items():
        if not isinstance(bucket, dict) or bucket.get("rateLimitReachedType") not in (None, ""):
            raise RoutingBlocked("WAITING_QUOTA")
        windows = (bucket.get("primary"), bucket.get("secondary"))
        if not all(isinstance(w, dict) for w in windows):
            raise RoutingBlocked("WAITING_QUOTA")
        durations = {w.get("windowDurationMins") for w in windows}
        if durations != {300, 10080}:
            raise RoutingBlocked("WAITING_QUOTA")
        for w in windows:
            pct = w.get("usedPercent")
            if type(pct) not in (int, float) or not 0 <= pct < 100 - reserve:
                raise RoutingBlocked("WAITING_QUOTA")
        rows[name] = {str(w["windowDurationMins"]): w["usedPercent"] for w in windows}
    return rows


def validated_failures(proofs: list[dict], *, attempt: int) -> None:
    """An escalation requires one independent failing test per prior attempt."""
    if attempt == 0:
        if proofs:
            raise RoutingBlocked("BLOCKED_ESCALATION")
        return
    if not isinstance(proofs, list) or len(proofs) != attempt:
        raise RoutingBlocked("BLOCKED_ESCALATION")
    commits = set()
    for proof in proofs:
        if (not isinstance(proof, dict) or proof.get("verifier") != "independent"
                or proof.get("status") != "FAIL" or type(proof.get("tests_run")) is not int
                or proof["tests_run"] < 1 or not isinstance(proof.get("commit_sha"), str)
                or not SHA.fullmatch(proof["commit_sha"])):
            raise RoutingBlocked("BLOCKED_ESCALATION")
        commits.add(proof["commit_sha"])
    if len(commits) != attempt:
        raise RoutingBlocked("BLOCKED_ESCALATION")


def select_route(mission: dict, pages: list[dict], quota: dict,
                 *, attempt: int = 0, proofs: list[dict] | None = None,
                 policy: dict | None = None, approved: bool = False) -> tuple[Route, dict]:
    """Planning only, no mutation, no model call, no mission approval."""
    if approved is not True:
        raise RoutingBlocked("AWAITING_APPROVAL")
    policy = load_policy() if policy is None else policy
    # Revalidate even with injected policy; load_policy is the only trusted loader.
    if type(attempt) is not int or not 0 <= attempt < policy["max_attempts"]:
        raise RoutingBlocked("BLOCKED_ESCALATION")
    validated_failures(proofs or [], attempt=attempt)
    usage = check_quota(quota, policy["quota_reserve_percent"])
    available = model_catalog(pages)
    initial = classify(mission)
    tier = initial if attempt == 0 else ("escalated" if attempt == 1 else "last_resort")
    # Fail closed if no configured model+effort belongs to this account catalog.
    for choice in policy["routes"][tier]:
        if choice["effort"] in available.get(choice["model"], ()):
            reason = "policy:" + initial + (f":verified_failure_{attempt}" if attempt else ":initial")
            return Route(choice["model"], choice["effort"], tier, attempt, reason), usage
    raise RoutingBlocked("BLOCKED_MODEL")


def read_live_state(cli: str, cwd: Path, env: dict, timeout: int = 30) -> tuple[list[dict], dict]:
    """Read model/list and account/rateLimits/read without starting a model.

    Call only from Codex 1 under its existing local lock, ChatGPT login check,
    and safe environment. Never accepts an endpoint or API token override.
    """
    import queue
    import subprocess
    from threading import Thread
    import time

    if not cli or not Path(cli).is_file():
        raise RoutingBlocked("BLOCKED_CLI")
    try:
        help_result = subprocess.run([cli, "exec", "--help"], cwd=cwd, env=env,
                                     capture_output=True, text=True, timeout=10)
        login = subprocess.run([cli, "login", "status"], cwd=cwd, env=env,
                               capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        raise RoutingBlocked("BLOCKED_CLI") from None
    if help_result.returncode or "--model" not in help_result.stdout or "-c" not in help_result.stdout:
        raise RoutingBlocked("BLOCKED_CLI")
    if login.returncode or "Logged in using ChatGPT" not in login.stdout + login.stderr:
        raise RoutingBlocked("BLOCKED_AUTH")
    try:
        with subprocess.Popen([cli, "app-server"], cwd=cwd, env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, encoding="utf-8") as proc:
            incoming = queue.Queue()

            def read_stdout():
                for line in proc.stdout:
                    incoming.put(line)
                incoming.put(None)

            thread = Thread(target=read_stdout, daemon=True)
            thread.start()
            deadline = time.monotonic() + timeout
            request_id = 0

            def send(method, params=None, notify=False):
                nonlocal request_id
                request_id += 1
                msg = {"method": method}
                if not notify:
                    msg["id"] = request_id
                if params is not None:
                    msg["params"] = params
                proc.stdin.write(json.dumps(msg) + "\n")
                proc.stdin.flush()
                return request_id

            def receive(expected_id):
                while time.monotonic() < deadline:
                    try:
                        line = incoming.get(timeout=max(0.001, deadline - time.monotonic()))
                    except queue.Empty:
                        break
                    if line is None:
                        break
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        raise RoutingBlocked("BLOCKED_CLI") from None
                    if event.get("id") == expected_id:
                        if "error" in event or not isinstance(event.get("result"), dict):
                            raise RoutingBlocked("BLOCKED_CLI")
                        return event["result"]
                raise RoutingBlocked("BLOCKED_CLI")

            initialize = send("initialize", {"clientInfo": {"name": "tel99-model-router", "version": "1"}})
            receive(initialize)
            send("initialized", notify=True)
            pages, cursor = [], None
            for _ in range(8):
                params = {"limit": 100, "includeHidden": False}
                if cursor:
                    params["cursor"] = cursor
                response = receive(send("model/list", params))
                pages.append(response)
                cursor = response.get("nextCursor")
                if not cursor:
                    break
            else:
                raise RoutingBlocked("BLOCKED_MODEL")
            result = receive(send("account/rateLimits/read"))
            snapshot = dict(result)
            limits = result.get("rateLimits")
            if isinstance(limits, dict) and "credits" not in snapshot:
                snapshot["credits"] = limits.get("credits")
            proc.kill()
            proc.wait(timeout=5)
            return pages, snapshot
    except (OSError, subprocess.TimeoutExpired, BrokenPipeError):
        raise RoutingBlocked("BLOCKED_CLI") from None
    finally:
        if "proc" in locals() and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
