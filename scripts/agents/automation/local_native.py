"""Pinned #110 native worker contract for approved synthetic Windows tickets."""

import hashlib
import json
import re
import sys

NATIVE_REF = "codex/native-kilo-free-20261118"
NATIVE_SHA = "982f5e22297694f122d87a1419c12d13a6aa7188"
IMAGE = "docker.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
OBJECTIVE = (
    "Créer un gestionnaire de tâches jouet. Dans README.md, donner cinq exemples fictifs "
    "avec tasks.py --db demo.json en texte simple, sans blocs Markdown imbriqués."
)
STRUCTURED_OBJECTIVE = (
    OBJECTIVE + " Répondre uniquement avec deux blocs complets, au début des lignes. "
    "Ouvrir le premier par une ligne exactement ```tasks.py puis le code Python, "
    "et le fermer par une ligne exactement ```. Ouvrir le second par une ligne exactement "
    "```README.md puis la documentation en texte simple et le fermer par une ligne exactement ```. "
    "Ne pas utiliser les étiquettes python ou markdown, ni ajouter de commentaire hors des deux blocs."
)
FILES = ("README.md", "tasks.py")


def native_scope(mission):
    return (
        re.fullmatch(r"CODEX110-[A-Z0-9-]+", mission["id"])
        and mission.get("base_sha") == NATIVE_SHA
        and mission.get("objective") in (OBJECTIVE, STRUCTURED_OBJECTIVE)
        and mission.get("synthetic_data") is True
        and type(mission.get("call_budget")) is int and mission["call_budget"] == 1
    )


def native_digest(mission):
    scope = {key: mission[key] for key in (
        "id", "issue", "role", "assignee", "base_sha", "objective", "priority",
        "dependencies", "expires_at", "synthetic_data", "call_budget",
    )}
    scope["dependency_evidence"] = mission.get("dependency_evidence", {})
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def storage_root(checkout, issue):
    if type(issue) is not int or issue < 1:
        raise ValueError("Numéro de ticket natif invalide.")
    state = checkout.parent if checkout.parent.name == ".tel99-automation-state" else checkout / ".tel99-automation-state"
    target = state / "n" / str(issue)
    if len(str(target / "_native_state/artifacts/tel99-windows/.attempts-12345678/1")) > 190:
        raise ValueError("Chemin de staging natif trop long pour py_compile sous Windows.")
    return target


def args_for(workspace, issue, command, *, objective=OBJECTIVE, data_root=None):
    data = data_root or workspace
    argv = [sys.executable, "-B", "-m", "scripts.agents.native.cli",
            "--state", str(data / "_native_state"),
            "--memory", str(data / "_native_memory")]
    if command == "run":
        # Engine quota bookkeeping, with exactly one permitted POST and zero repairs.
        argv += ["--quota", "12"]
    argv += [command, "--project", "tel99-windows", "--mission-id", f"github-{issue}"]
    if command == "run":
        if objective not in (OBJECTIVE, STRUCTURED_OBJECTIVE):
            raise ValueError("Consigne native non autorisée.")
        argv += ["--synthetic-data", "--profile", "tasks", "--sandbox-image", IMAGE,
                 "--max-repairs", "0", "--mission", objective]
    return argv


def result_evidence(report):
    """Allowlist terminal fields. Never publish worker text, output or paths."""
    if not isinstance(report, dict):
        raise ValueError("Rapport natif invalide.")
    verdict = report.get("verdict")
    details = {"verdict": verdict if verdict in ("PASS", "FAIL", "NEEDS_HUMAN") else "UNKNOWN"}
    calls = report.get("provider_calls")
    if type(calls) is int and 0 <= calls <= 1:
        details["provider_calls"] = calls
    hashes = report.get("artifact_digests")
    if isinstance(hashes, dict):
        details["artifact_digests"] = {name: hashes[name] for name in FILES if
                                      isinstance(hashes.get(name), str) and re.fullmatch(r"[0-9a-f]{64}", hashes[name])}
    last = report["attempts"][-1] if isinstance(report.get("attempts"), list) and report["attempts"] else {}
    if not isinstance(last, dict):
        last = {}
    missing = last.get("missing_artifacts")
    if isinstance(missing, list):
        details["missing_artifacts"] = [name for name in FILES if name in missing]
    checks = report.get("checks")
    if isinstance(checks, list):
        details["checks"] = []
        for check in checks:
            if not isinstance(check, dict) or check.get("name") not in ("syntax", "task-app-acceptance"):
                continue
            row = {"name": check["name"], "ok": check.get("ok") is True}
            if type(check.get("exit")) is int:
                row["exit"] = check["exit"]
            if (check["name"] == "syntax" and not row["ok"]
                    and "__pycache__" in str(check.get("detail", ""))):
                row["cause"] = "BYTECODE_IO"
            details["checks"].append(row)
    received = last.get("provider_evidence")
    if isinstance(received, dict):
        evidence = {key: received[key] for key in ("catalog_sha256", "response_sha256")
                    if isinstance(received.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", received[key])}
        if type(received.get("http_status")) is int and 100 <= received["http_status"] < 600:
            evidence["http_status"] = received["http_status"]
        if received.get("cost_usd") == "0":
            evidence["cost_usd"] = "0"
        details["provider_evidence"] = evidence
    return details
