"""Read-only environment & readiness diagnostic for TEL99 autonomous campaigns."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import local_model_routing, local_team
from scripts.agents.automation.autonomy_runtime import LEGACY_STOP
from scripts.agents.automation.github_mission_source import gh_json, is_owner
from scripts.agents.automation.kilo_github_adapter import REPO
from scripts.agents.intelligence import catalog
from scripts.agents.native import sandbox

DEFAULT_SANDBOX_IMAGE = (
    "python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
)


def _probe_git(root: Path = ROOT) -> dict:
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root, text=True, timeout=5, stderr=subprocess.DEVNULL,
        ).strip()
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root, text=True, timeout=5, stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root, text=True, timeout=5, stderr=subprocess.DEVNULL,
        ).strip())
        return {"ok": True, "branch": branch, "head": head, "dirty": dirty}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def _probe_github(fetcher=gh_json) -> dict:
    try:
        user = fetcher("user")
        if not is_owner(user):
            return {"ok": False, "error": "gh session is not pinned repository owner"}
        repo = fetcher(f"repos/{REPO}")
        perms = repo.get("permissions") if isinstance(repo, dict) else None
        if not isinstance(perms, dict) or perms.get("push") is not True:
            return {"ok": False, "owner": user.get("login"), "error": "push permission missing"}
        return {"ok": True, "owner": user.get("login"), "push": True}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def _probe_ollama() -> dict:
    conn = HTTPConnection("127.0.0.1", 11434, timeout=3)
    try:
        conn.request("GET", "/api/tags")
        resp = conn.getresponse()
        if resp.status != 200:
            return {"ok": False, "error": f"HTTP {resp.status}"}
        payload = json.loads(resp.read(32_768))
        rows = payload.get("models") if isinstance(payload, dict) else None
        installed = sorted(
            row["name"] for row in (rows or [])
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        )
        expected = sorted({
            mid for spec in catalog.MODEL_CATALOG
            if spec.provider == "ollama" for mid in spec.served_ids
        })
        missing = [mid for mid in expected if mid not in installed]
        analyst_ready = local_team.ANALYST_MODEL in installed
        return {
            "ok": analyst_ready and len(installed) > 0,
            "installed": installed,
            "catalog_missing": missing,
            "analyst_ready": analyst_ready,
        }
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


def _probe_docker(image: str = DEFAULT_SANDBOX_IMAGE) -> dict:
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if info.returncode != 0:
            return {"ok": False, "error": "docker daemon unavailable"}
        sandbox.require_local_image(image)
        return {"ok": True, "server_version": info.stdout.strip(), "sandbox_image": image}
    except (OSError, subprocess.SubprocessError, Exception) as exc:
        return {"ok": False, "error": str(exc)}


def diagnose(*, state_dir: Path | None = None, auto_feed: bool = False,
             include_providers: bool = False,
             sandbox_image: str = DEFAULT_SANDBOX_IMAGE,
             git_probe=_probe_git, gh_probe=_probe_github,
             ollama_probe=_probe_ollama, docker_probe=_probe_docker,
             memory_probe=local_model_routing.available_memory_mib,
             autofeed_probe=None) -> dict:
    """Run read-only environment readiness checks without touching state."""
    checks: dict[str, dict] = {}
    blockers: list[str] = []

    checks["python"] = {"ok": sys.version_info >= (3, 11), "version": sys.version.split()[0]}
    if not checks["python"]["ok"]:
        blockers.append("PYTHON_VERSION_TOO_OLD")

    checks["git"] = git_probe()
    if not checks["git"].get("ok"):
        blockers.append("GIT_UNAVAILABLE")

    checks["github"] = gh_probe()
    if not checks["github"].get("ok"):
        blockers.append("GITHUB_AUTH_OR_PUSH_UNAVAILABLE")

    checks["ollama"] = ollama_probe()
    if not checks["ollama"].get("ok"):
        blockers.append("OLLAMA_OR_ANALYST_MODEL_UNAVAILABLE")

    checks["docker"] = docker_probe(sandbox_image)
    if not checks["docker"].get("ok"):
        blockers.append("DOCKER_OR_SANDBOX_IMAGE_UNAVAILABLE")

    avail_mib = memory_probe()
    mem_ok = avail_mib is not None and avail_mib >= local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB
    checks["memory"] = {
        "ok": mem_ok,
        "available_mib": avail_mib,
        "required_reserve_mib": local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB,
    }
    if not mem_ok:
        blockers.append("INSUFFICIENT_FREE_MEMORY")

    global_stop = LEGACY_STOP.exists()
    state_stop = False
    campaign_stops: list[str] = []
    if state_dir is not None:
        resolved = Path(state_dir).resolve()
        state_stop = (resolved / "stop.request").exists()
        if resolved.is_dir():
            campaign_stops = sorted(
                p.parent.name for p in resolved.glob("campaign-*/stop.request") if p.is_file()
            )
    stop_active = global_stop or state_stop or bool(campaign_stops)
    checks["stop_markers"] = {
        "ok": not stop_active,
        "global_stop": global_stop,
        "state_stop": state_stop,
        "campaign_stops": campaign_stops,
    }
    if stop_active:
        blockers.append("STOP_MARKER_ACTIVE")

    if auto_feed:
        try:
            if autofeed_probe is None:
                from scripts.agents.automation.github_owner_feed import discover_owner_pins
                pins = discover_owner_pins()
            else:
                pins = autofeed_probe()
            checks["autofeed"] = {
                "ok": True,
                "controllers": [pin["issue"] for pin in pins],
                "count": len(pins),
            }
        except (OSError, ValueError) as exc:
            checks["autofeed"] = {"ok": False, "error": str(exc)}
            blockers.append("AUTOFEED_DISCOVERY_ERROR")

    if include_providers:
        from scripts.agents.automation import provider_router
        checks["providers"] = provider_router.probe_all_providers()["providers"]

    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ready": not blockers,
        "blockers": blockers,
        "checks": checks,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--auto-feed", action="store_true")
    parser.add_argument("--include-providers", action="store_true")
    args = parser.parse_args(argv)
    report = diagnose(
        state_dir=args.state,
        auto_feed=args.auto_feed,
        include_providers=args.include_providers,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
