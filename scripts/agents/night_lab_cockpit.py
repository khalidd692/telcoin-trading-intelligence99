"""Bounded browser projection of the existing GitHub local-code campaign ledger."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from scripts.agents.automation import local_codegen, local_model_routing, local_team
from scripts.agents.automation.autonomy_runtime import fingerprint, validate_contract
from scripts.agents.automation.github_local_code_campaign import CONFIG_KEY, REPO, TRANSPORT
from scripts.agents.automation.local_code_pr import EVENT, REQUIRED
from scripts.agents.protocol.store import FileStore
from scripts.agents.team_config import role_catalog


ASSETS = Path(__file__).with_name("night_lab_ui")
MAX_RECORD_BYTES = 256_000
HEARTBEAT_AGE_SECONDS = 30
GITHUB = f"https://github.com/{REPO}"
ID = re.compile(r"[A-Za-z0-9-]{1,48}")
DIGEST = re.compile(r"[0-9a-f]{64}")
CHECKPOINTS = {"PREPARING", "ACK", "RUNNING", "WORKER_EXITED", "ACCEPTED", "REJECTED",
               "BLOCKED", "AWAITING_HUMAN"}
BLOCKERS = {"GITHUB_RATE_LIMIT", "GITHUB_RECEIPT_OR_APPROVAL_UNCONFIRMED",
            "SOURCE_UNAVAILABLE_OR_INVALID"}
TESTS = ("bounded-model-receipt", "approved-function-diff", "baseline-fails", "candidate-passes")
ROLE_INFO = {
    "tel99-analyst": ("Analyste", "LLM", "Lecture de la fonction approuvée", ["Ollama"]),
    "tel99-dev": ("Développement", "LLM", "Proposition bornée à la fonction approuvée", ["Ollama"]),
    "tel99-verifier": ("Vérification", "DETERMINISTIC", "Contrôle indépendant de la preuve", ["Docker"]),
    "tel99-coordination": ("Coordination", "DETERMINISTIC", "Contrôle de la transmission", ["Contrat local"]),
    "tel99-security": ("Sécurité", "DETERMINISTIC", "Contrôle statique du périmètre", ["Analyse Python"]),
    "tel99-cloud": ("Cloud et fiabilité", None, None, []),
    "tel99-mobile": ("Expérience mobile", None, None, []),
    "tel99-documentation": ("Documentation", None, None, []),
    "tel99-evaluation": ("Évaluation", None, None, []),
    "tel99-market-data": ("Données de marché", None, None, []),
    "tel99-monitoring": ("Surveillance", None, None, []),
    "tel99-release": ("Publication", None, None, []),
}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _digest(value):
    return value if isinstance(value, str) and DIGEST.fullmatch(value) else None


def _positive(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def _at(value):
    if type(value) in (int, float) and 0 < value < 4_102_444_800:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    return None


def _read(root, key):
    path = root / "ledger" / (key + ".json")
    if path.resolve() != path:
        raise ValueError("redirected campaign record")
    try:
        def read_bytes():
            with path.open("rb") as handle:
                return handle.read(MAX_RECORD_BYTES + 1)
        # The writer replaces each record atomically. On Windows this reuses
        # the existing sharing retry without creating per-record lock files.
        raw = FileStore._retry_file_access(read_bytes)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError("campaign record exceeds bound")
    return json.loads(raw)


def _pid_alive(pid):
    if type(pid) is not int or not 0 < pid <= 2**31 - 1:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only.
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT.
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # Signal 0 is a read-only existence check on POSIX.
        stat = Path(f"/proc/{pid}/stat")
        if stat.is_file() and stat.read_text(encoding="utf-8", errors="replace").rsplit(") ", 1)[-1].startswith("Z "):
            return False
    except OSError:
        return False
    return True


def _supervisor(root, now, configured):
    row = _dict(_read(root, "github/heartbeat")) if configured else {}
    timestamp = row.get("HEARTBEAT")
    age = None
    if isinstance(timestamp, str) and len(timestamp) <= 40:
        try:
            seen = datetime.fromisoformat(timestamp)
            age = (now - seen).total_seconds()
            timestamp = seen.astimezone(timezone.utc).isoformat(timespec="seconds")
        except (TypeError, ValueError, OverflowError):
            timestamp = None
    else:
        timestamp = None
    fresh = age is not None and 0 <= age <= HEARTBEAT_AGE_SECONDS
    stopped = row.get("STATE") == "STOPPED"
    alive = fresh and not stopped and _pid_alive(row.get("PID"))
    marker = root / "stop.request"
    stop_requested = marker.exists() or marker.is_symlink()
    blocker = row.get("BLOCKER")
    blocker = blocker if isinstance(blocker, str) and blocker in BLOCKERS else None
    state = row.get("STATE")
    phase = row.get("PHASE")
    task = row.get("ACTIVE_TASK")
    role = row.get("ACTIVE_ROLE")
    stage = "WAITING"
    status = "WAITING"
    if stopped:
        status, stage = "STOPPED", "STOPPED"
    elif alive and stop_requested:
        status, stage = "WAITING", "STOP_REQUESTED"
    elif alive and (state == "BLOCKED" or blocker):
        status, stage = "BLOCKED", "RECONCILIATION"
    elif alive and state == "RUNNING":
        status, stage = "ACTIVE", "WORKER"
    elif alive and state == "WORKER_EXITED" and phase == "VERIFICATION":
        status, stage = "ACTIVE", "VERIFICATION"
    elif alive and phase == "PUBLICATION":
        status, stage = "ACTIVE", "PUBLICATION"
    elif row and not alive:
        status, stage = "UNAVAILABLE", "RECONCILIATION"
    return {
        "status": status, "stage": stage,
        "freshness": "fresh" if fresh else "stale" if timestamp else "unavailable",
        "heartbeat": timestamp, "pid": row["PID"] if alive else None,
        "active_task": task if status == "ACTIVE" and isinstance(task, str) and ID.fullmatch(task) else None,
        "active_role": role if status == "ACTIVE" and role in local_team.TEAM else None,
        "blocker": blocker if alive else None,
        "alive": alive, "stop_requested": stop_requested,
    }


def _comment_url(issue, comment=None):
    return f"{GITHUB}/issues/{issue}" + (f"#issuecomment-{comment}" if comment is not None else "")


def _receipt(root, mid, issue, contract_sha256, phase):
    row = _dict(_read(root, f"kilo-github/outbox/{mid}/{phase}"))
    event = _dict(row.get("event"))
    if (event.get("event"), event.get("phase"), event.get("issue"), event.get("mission_id"),
            event.get("scope"), event.get("contract_sha256")) != (
                EVENT, phase, issue, mid, "approved-python-function", contract_sha256):
        return {}
    url = row.get("url")
    prefix = _comment_url(issue) + "#issuecomment-"
    if isinstance(url, str) and url.startswith(prefix) and re.fullmatch(r"[1-9][0-9]{0,19}", url[len(prefix):]):
        return {"state": "CONFIRMED", "url": url, "event": event}
    return {"state": "NOT_SENT" if row.get("not_sent") is True else "PENDING_RECONCILIATION"}


def _test_results(verification):
    rows = verification.get("checks")
    if not isinstance(rows, list):
        return []
    by_name = {row["name"]: row for row in rows
               if isinstance(row, dict) and isinstance(row.get("name"), str)
               and row["name"] in REQUIRED and type(row.get("ok")) is bool}
    return [{"name": name, "ok": by_name[name]["ok"],
             "exit_code": by_name[name]["exit_code"] if type(by_name[name].get("exit_code")) is int
             and 0 <= by_name[name]["exit_code"] <= 255 else None}
            for name in TESTS if name in by_name]


def _role_proofs(mission, result, verification, checkpoint, checks):
    proofs = []
    artifact = result.get("artifact")
    trace = _dict(result.get("agent_trace"))
    if (isinstance(artifact, str) and 0 < len(artifact) <= 16_000
            and _digest(result.get("sha256")) == hashlib.sha256(artifact.encode("utf-8")).hexdigest()
            and result.get("provider") == local_codegen.PROVIDER
            and local_team.valid_trace(mission, result)):
        proofs += [
            {"role": "tel99-analyst", "model": local_team.ANALYST_MODEL,
             "sha256": trace["analyst"]["sha256"], "ok": True},
            {"role": "tel99-dev", "model": mission["model"], "sha256": result["sha256"], "ok": True},
        ]
    independent = _dict(verification.get("verification_role"))
    verified = (len(proofs) == 2 and verification.get("verifier") == local_codegen.VERIFIER
                and independent.get("role") == "tel99-verifier"
                and independent.get("analyst_sha256") == proofs[0]["sha256"]
                and verification.get("artifact_sha256") == result.get("sha256")
                and verification.get("test_sha256") == hashlib.sha256(mission["test"].encode("utf-8")).hexdigest()
                and all(verification.get(key) == mission[key] for key in ("base_sha", "path", "function", "model")))
    if verified:
        passed = (verification.get("ok") is True and _dict(checkpoint.get("verdict")).get("validated") is True
                  and len(checks) == len(TESTS) and all(test["ok"] for test in checks)
                  and checks[-2]["exit_code"] == 1 and checks[-1]["exit_code"] == 0)
        proofs.append({"role": "tel99-verifier", "model": None,
                       "sha256": _digest(verification.get("test_sha256")), "ok": passed})
    for key, name in (("coordination_role", "tel99-coordination"), ("security_role", "tel99-security")):
        proof = _dict(verification.get(key))
        if (proof.get("role") == name and proof.get("engine") == "deterministic"
                and type(proof.get("ok")) is bool and (name != "tel99-coordination" or len(proofs) >= 2)):
            proofs.append({"role": name, "model": None, "sha256": None, "ok": proof["ok"]})
    return proofs


def _mission(root, mid, binding, config, supervisor):
    mission = _dict(binding.get("mission"))
    issue, comment = binding.get("issue"), binding.get("comment_id")
    pin = _digest(binding.get("contract_sha256"))
    if (not pin or not _positive(issue) or issue <= config["issue"] or not _positive(comment)
            or mission.get("id") != mid or mission.get("team") != local_team.TEAM
            or mission.get("base_sha") != binding.get("base_sha")):
        raise ValueError("invalid local approval")
    validate_contract(mission, {mid: pin})
    checkpoint_value = _read(root, f"kilo-local/{mid}")
    checkpoint = _dict(checkpoint_value)
    proposal = checkpoint.get("status")
    if checkpoint_value is not None and (proposal not in CHECKPOINTS or checkpoint.get("id") != mid
            or checkpoint.get("project") != "tel99" or checkpoint.get("contract_sha256") != pin):
        raise ValueError("mismatched mission checkpoint")

    result = _dict(checkpoint.get("result"))
    verification = _dict(checkpoint.get("verification"))
    checks = _test_results(verification)
    proof = _role_proofs(mission, result, verification, checkpoint, checks)
    receipts = {phase: _receipt(root, mid, issue, pin, phase) for phase in ("ACK", "EVIDENCE", "RESULT")}
    publication = _dict(_read(root, f"github-local-code/PR/{issue}/{mid}"))
    intent = _dict(publication.get("intent"))
    pr = publication.get("pr_url")
    docker_accepted = any(row["role"] == "tel99-verifier" and row["ok"] for row in proof)
    published = (proposal == "ACCEPTED" and docker_accepted and intent.get("contract_sha256") == pin
                 and intent.get("evidence_url") == receipts["EVIDENCE"].get("url")
                 and bool(receipts["EVIDENCE"].get("url"))
                 and receipts["EVIDENCE"]["event"].get("status") == "ACCEPTED"
                 and receipts["EVIDENCE"]["event"].get("verification_sha256") == fingerprint(verification)
                 and receipts["EVIDENCE"]["event"].get("artifact_sha256") == result["sha256"]
                 and isinstance(pr, str) and re.fullmatch(re.escape(GITHUB) + r"/pull/[1-9][0-9]{0,19}", pr))
    result_event = receipts["RESULT"].get("event", {})
    delivered = (published and bool(receipts["ACK"].get("url")) and result_event.get("status") == "ACCEPTED"
                 and result_event.get("evidence_url") == receipts["EVIDENCE"].get("url")
                 and result_event.get("pull_request_url") == pr)
    active = supervisor["status"] == "ACTIVE" and supervisor["active_task"] == mid
    if proposal == "ACCEPTED" and not docker_accepted:
        status, stage = "BLOCKED", "EVIDENCE_UNAVAILABLE"
    elif proposal == "ACCEPTED":
        status, stage = "ACCEPTED", "COMPLETE" if delivered else "PUBLICATION"
    elif proposal in {"BLOCKED", "REJECTED", "AWAITING_HUMAN"}:
        status, stage = "BLOCKED", proposal
    elif proposal == "RUNNING":
        status, stage = ("ACTIVE", "WORKER") if active and supervisor["stage"] == "WORKER" else ("BLOCKED", "RECONCILIATION")
    elif proposal == "WORKER_EXITED" and active and supervisor["stage"] == "VERIFICATION":
        status, stage = "ACTIVE", "VERIFICATION"
    elif proposal == "WORKER_EXITED":
        status, stage = "WAITING", "VERIFICATION_PENDING"
    elif proposal in {"PREPARING", "ACK"}:
        status, stage = "WAITING", proposal
    else:
        status, stage = "WAITING", "DEPENDENCIES" if mission["dependencies"] else "QUEUED"

    attempt = checkpoint.get("attempt")
    measurements = {}
    for name in ("generation_seconds", "verification_seconds", "host_memory_before_mib", "host_memory_after_mib"):
        value = verification.get(name, result.get(name))
        if type(value) in (int, float) and 0 <= value <= 16_777_216:
            measurements[name] = value
    return {
        "id": mid, "issue": issue, "issue_url": _comment_url(issue),
        "approval_url": _comment_url(issue, comment), "contract_sha256": pin,
        "path": mission["path"], "function": mission["function"], "dependencies": mission["dependencies"],
        "base_sha": mission["base_sha"], "model": mission["model"], "at": _at(checkpoint.get("at")),
        "status": status, "stage": stage, "checkpoint": proposal,
        "attempt": attempt if type(attempt) is int and 1 <= attempt <= mission.get("max_attempts", 1) else None,
        "max_attempts": mission.get("max_attempts", 1), "checks": checks, "handoffs": proof,
        "pull_request": pr if published else None,
        "receipts": {phase: {key: value for key, value in receipt.items() if key != "event"}
                     for phase, receipt in receipts.items()},
        "measurements": measurements,
        "publication_pending": not published and publication.get("pr_pending") is True,
    }


def _roles(missions, supervisor):
    by_role = {spec.name: spec for spec in role_catalog().values()}
    active_role = supervisor.pop("active_role")
    active_task = supervisor["active_task"]
    active_mission = next((mission for mission in missions if mission["id"] == active_task), None)
    if active_mission and active_mission["status"] == "ACTIVE" and active_mission["stage"] == "VERIFICATION":
        active_role = "tel99-verifier"
    elif (not active_mission or active_mission["status"] != "ACTIVE" or active_role not in local_team.TEAM[:2]):
        active_role = None
    rows = []
    for name, spec in by_role.items():
        label, engine, scope, tools = ROLE_INFO[name]
        history = [
            {**proof, "mission": mission["id"], "at": mission["at"], "issue_url": mission["issue_url"]}
            for mission in missions for proof in mission["handoffs"] if proof["role"] == name
        ]
        enabled = name in local_team.TEAM or bool(history)
        rows.append({"id": name, "label": label, "catalogue_active": spec.active,
                     "status": "ACTIVE" if name == active_role else "WAITING" if enabled else "UNAVAILABLE",
                     "engine": engine if enabled else None, "tools": tools if enabled else [],
                     "scope": scope if enabled else None, "history": history,
                     "active_mission": active_task if name == active_role else None})
    return rows


def snapshot(root, *, allow_stop=False):
    """Read public-safe fields from one explicitly selected campaign directory."""
    now = datetime.now(timezone.utc)
    config_value = _read(root, CONFIG_KEY)
    config = _dict(config_value)
    if config_value is not None and (
            config.get("repo") != REPO or config.get("profile") != TRANSPORT
            or config.get("campaign") is not True or not _positive(config.get("issue"))
            or not _positive(config.get("mandate_id")) or not _digest(config.get("mandate_sha256"))
            or _read(root, "runtime-config/transport") != TRANSPORT):
        raise ValueError("directory is not a GitHub code campaign")
    supervisor = _supervisor(root, now, bool(config))
    missions = []
    if config:
        approval_dir = root / "ledger/kilo-github/approvals"
        if approval_dir.resolve() != approval_dir:
            raise ValueError("redirected campaign approvals")
        keys = sorted(path.stem for path in approval_dir.glob("*.json") if ID.fullmatch(path.stem))
        if len(keys) > 20:
            raise ValueError("campaign queue exceeds bound")
        for mid in keys:
            binding = _dict(_read(root, f"kilo-github/approvals/{mid}"))
            if binding:
                missions.append(_mission(root, mid, binding, config, supervisor))
    missions.sort(key=lambda row: row["issue"])
    if (supervisor["stage"] in {"WORKER", "VERIFICATION"}
            and not any(mission["status"] == "ACTIVE" for mission in missions)):
        supervisor.update(status="WAITING", stage="WAITING", active_task=None)
    roles = _roles(missions, supervisor)
    can_stop = bool(allow_stop and config and supervisor["alive"])
    del supervisor["alive"]
    if supervisor["active_task"] not in {mission["id"] for mission in missions}:
        supervisor["active_task"] = None
    return {
        "source": "github-local-code", "read_at": now.isoformat(timespec="seconds"),
        "supervisor": supervisor, "roles": roles, "missions": missions,
        "campaign": {"issue": config["issue"], "url": _comment_url(config["issue"], config["mandate_id"]),
                     "sha256": config["mandate_sha256"]} if config else None,
        "resources": {"memory_available_mib": local_model_routing.available_memory_mib(),
                      "logical_cpus": os.cpu_count()},
        "stop_enabled": can_stop and not supervisor["stop_requested"],
    }


def request_stop(root):
    """Create the exact stop marker consumed by the established supervisor."""
    status = snapshot(root, allow_stop=True)
    if not status["stop_enabled"]:
        return False
    marker = root / "stop.request"
    try:
        with marker.open("xb"):
            pass
    except FileExistsError:
        return True
    return True
