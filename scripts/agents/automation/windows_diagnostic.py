"""Collect read-only TEL99 workstation evidence without starting a runtime."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

LOCAL_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE",
             "HOME", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP")
VERSION = r"[0-9]{1,4}(?:\.[0-9]{1,4}){2,3}"
VERSION_PATTERNS = {
    "git": rf"git version ({VERSION}(?:\.windows\.[0-9]{{1,4}})?)$",
    "gh": rf"gh version ({VERSION})(?:[ \t]|$)",
    "pwsh": rf"PowerShell ({VERSION}(?:-(?:preview|rc)\.[0-9]{{1,4}})?)$",
    "kilo": rf"(?:kilo(?: version)? )?({VERSION})$",
}
KILO_FLAGS = ("--agent", "--auto", "--continue", "--format", "--model", "--session", "--tool")


def local_probe(argv, cwd):
    env = {name: os.environ[name] for name in LOCAL_ENV if name in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", POWERSHELL_TELEMETRY_OPTOUT="1",
               OPENCODE_DISABLE_AUTOUPDATE="true", KILO_DISABLE_AUTOUPDATE="true")
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace", timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def tool_obs(name, executable):
    if not executable:
        return {"source": "PATH", "status": "ABSENT", "version": None}
    flags = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Version"] if name == "pwsh" else ["--version"]
    output = local_probe([executable, *flags], ROOT) or ""
    match = re.search("^" + VERSION_PATTERNS[name], output, re.MULTILINE | re.IGNORECASE)
    return {"source": f"{name} version command", "status": "OBSERVED" if match else "UNVERIFIED",
            "version": match[1] if match else None}


def kilo_help(executable):
    if not executable:
        return {"source": "kilo run --help", "status": "ABSENT", "flags": []}
    output = local_probe([executable, "run", "--help"], ROOT)
    if not output:
        return {"source": "kilo run --help", "status": "UNVERIFIED", "flags": []}
    flags = [flag for flag in KILO_FLAGS if re.search(rf"(?m)^[ \t]*(?:-[a-zA-Z], )?{flag}(?:[ ,=\t]|$)", output)]
    return {"source": "kilo run --help", "status": "OBSERVED", "flags": flags}


def presence(path, *, directory=False):
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return "ABSENT"
    except (OSError, ValueError):
        return "UNAVAILABLE"
    return "PRESENT" if not directory or stat.S_ISDIR(mode) else "NOT_DIRECTORY"


def git_changes(output):
    counts = {"staged": 0, "unstaged": 0, "untracked": 0, "conflicts": 0}
    fields = iter(output.split("\0"))
    for row in fields:
        if not row:
            continue
        if not re.match(r"^[ MADRCU?T]{2} ", row):
            return None
        index, worktree = row[:2]
        if (index in "RC" or worktree in "RC") and not next(fields, ""):
            return None
        if index + worktree == "??":
            counts["untracked"] += 1
        elif index + worktree in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}:
            counts["conflicts"] += 1
        elif "T" in index or "T" in worktree:
            counts["staged"] += index != " "
            counts["unstaged"] += worktree != " "
        else:
            counts["staged"] += index != " "
            counts["unstaged"] += worktree != " "
    return counts


def worktree_status(root):
    git = shutil.which("git")
    report = {"source": "git worktree list, rev-parse and status", "count": None, "head": None,
              "changes": None, "primary_worktree_stop": "UNAVAILABLE"}
    if not git:
        return report
    base = [git, "--no-optional-locks", "-c", "core.fsmonitor=false"]
    listing = local_probe([*base, "worktree", "list", "--porcelain", "-z"], root)
    if listing is not None:
        locations = [row[9:] for row in listing.split("\0") if row.startswith("worktree ") and row[9:]]
        report["count"] = len(locations)
        if locations:
            report["primary_worktree_stop"] = presence(Path(locations[0]) / ".kilo" / "STOP")
    head = local_probe([*base, "rev-parse", "--verify", "HEAD"], root)
    if head and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head.strip()):
        report["head"] = head.strip()
    output = local_probe([*base, "status", "--porcelain=v1", "-z", "--untracked-files=normal",
                          "--ignore-submodules=all"], root)
    if output is not None:
        report["changes"] = git_changes(output)
    return report


def state_status(state, issue, mandate, campaign):
    name = f"kilo-campaign-{issue}-{mandate or 0}" if campaign else f"kilo-github-{issue}" if issue else "kilo"
    default = Path(".tel99-automation-state") / name
    location = default.as_posix() if state.absolute() == ROOT / default else "operator-supplied --state"
    # FileStore reads on Windows create lock files. Observe only the expected paths here.
    return {"source": "filesystem metadata", "location": location,
            "directory": presence(state, directory=True),
            "stop_request": presence(state / "stop.request"),
            "checkout_stop": presence(ROOT / ".kilo" / "STOP"),
            "heartbeat_file": presence(state / "ledger" / "github" / "heartbeat.json")}


def github_get(endpoint):
    # All callers use fixed endpoints or the pinned adapter's bounded queries.
    gh = shutil.which("gh")
    if not gh:
        raise OSError("GitHub CLI unavailable")
    proc = subprocess.run([gh, "api", "--hostname", "github.com", "--method", "GET", endpoint],
                          cwd=ROOT, env={**os.environ, "GH_PROMPT_DISABLED": "1", "GH_DEBUG": ""},
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          encoding="utf-8", timeout=8, check=False)
    if proc.returncode:
        raise OSError("GitHub read unavailable")
    return json.loads(proc.stdout)


def github_status(issue, mandate, digest, campaign):
    from scripts.agents.automation.github_mission_source import OWNER_ID, OWNER_LOGIN, is_owner
    from scripts.agents.automation.kilo_github_adapter import KiloGitHubHandoff, REPO

    report = {"source": "GitHub REST GET via gh", "status": "BLOCKED", "identity": {"status": "UNAVAILABLE"},
              "permissions": None, "core_rate_limit": None, "mandate": {"status": "UNVERIFIED"}}

    def metadata(endpoint):
        try:
            response = github_get(endpoint)
        except (OSError, ValueError, RecursionError, subprocess.TimeoutExpired):
            return {}
        return response if isinstance(response, dict) else {}

    identity = metadata("user")
    if not is_owner(identity):
        if identity:
            report["identity"]["status"] = "UNEXPECTED_IDENTITY"
        return report
    report["identity"] = {"status": "PINNED_OWNER", "login": OWNER_LOGIN, "id": OWNER_ID}
    permissions = metadata(f"repos/{REPO}").get("permissions")
    if isinstance(permissions, dict):
        report["permissions"] = {key: permissions[key] for key in ("pull", "triage", "push", "maintain", "admin")
                                 if type(permissions.get(key)) is bool} or None
    resources = metadata("rate_limit").get("resources")
    core = resources.get("core") if isinstance(resources, dict) else None
    keys = ("limit", "remaining", "reset")
    if isinstance(core, dict) and all(type(core.get(key)) is int and core[key] >= 0 for key in keys):
        if core["remaining"] <= core["limit"]:
            report["core_rate_limit"] = {key: core[key] for key in keys}
    try:
        adapter = KiloGitHubHandoff(None, issue, mandate, digest, campaign=campaign, fetcher=github_get)
        missions = adapter.preflight()
    except (OSError, ValueError, TypeError, RecursionError, subprocess.TimeoutExpired):
        report["mandate"]["status"] = "BLOCKED"
    else:
        admitted = len(missions)
        has_queue = admitted == 2 if campaign else admitted > 0
        report["status"] = "OBSERVED"
        report["mandate"] = {"status": "VERIFIED" if has_queue else "WAITING_APPROVALS",
                             "issue": issue, "comment": mandate, "approved_count": admitted}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--mandate-comment", type=int)
    parser.add_argument("--mandate-sha256")
    parser.add_argument("--campaign", action="store_true")
    args = parser.parse_args(argv)
    github_requested = args.mandate_comment is not None or args.mandate_sha256 is not None
    valid_pin = ((args.issue or 0) > 0 and (args.mandate_comment or 0) > 0
                 and re.fullmatch(r"[0-9a-f]{64}", args.mandate_sha256 or ""))
    if github_requested and not valid_pin:
        parser.error("GitHub reads require a positive issue, mandate comment ID and pinned SHA-256")

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    commands = {name: shutil.which(name) for name in VERSION_PATTERNS}
    versions = {name: tool_obs(name, executable) for name, executable in commands.items()}
    versions["python"] = {"source": "running Python interpreter", "status": "OBSERVED",
                          "version": ".".join(str(n) for n in sys.version_info[:3])}
    windows = sys.getwindowsversion() if sys.platform == "win32" else None
    platform = {"source": "running Python interpreter", "status": "OBSERVED" if windows else "WINDOWS_PENDING",
                "windows_build": windows.build if windows else None}
    hermes_home = os.environ.get("HERMES_HOME")
    hermes_home = Path(hermes_home) if hermes_home else Path.home() / "AppData" / "Local" / "hermes"
    hermes_installed = bool(shutil.which("hermes")) or bool(
        os.environ.get("HERMES_CLI_EXE") and presence(Path(os.environ["HERMES_CLI_EXE"])) == "PRESENT")
    openhands_installed = bool(shutil.which("openhands"))
    report = {
        "status": "BLOCKED",
        "timestamp_utc": started,
        "platform": platform,
        "versions": versions,
        "kilo": {"source": "local CLI help only", "run_help": kilo_help(commands["kilo"]),
                 "agent_manager_sessions": "WINDOWS_PENDING", "session_tool_permissions": "WINDOWS_PENDING",
                 "provider_quota": "UNVERIFIED"},
        "hermes": {"source": "configured CLI path and local filesystem metadata", "cli_detected": hermes_installed,
                   "home": "$HERMES_HOME" if os.environ.get("HERMES_HOME") else "~/AppData/Local/hermes",
                   "state_db": presence(hermes_home / "state.db"), "runtime_status": "WINDOWS_PENDING",
                   "provider_quota": "UNVERIFIED"},
        "openhands": {"source": "local PATH and checkout metadata", "cli_detected": openhands_installed,
                      "repo_directory": presence(ROOT / ".openhands", directory=True),
                      "connection": "WINDOWS_PENDING", "provider_quota": "UNVERIFIED"},
        "worktree": worktree_status(ROOT),
        "state": state_status(args.state, args.issue, args.mandate_comment, args.campaign),
        "github": (github_status(args.issue, args.mandate_comment, args.mandate_sha256, args.campaign)
                   if github_requested else {"source": "operator opt-in", "status": "NOT_REQUESTED"}),
        "blockers": ["KILO_AGENT_MANAGER_SESSION_AND_TOOL_PERMISSIONS_UNVERIFIED",
                     "HERMES_RUNTIME_UNVERIFIED", "OPENHANDS_CONNECTION_UNVERIFIED",
                     "NO_VERIFIED_PROVIDER_QUOTA"],
    }
    if not windows:
        report["blockers"].insert(0, "WINDOWS_WORKSTATION_NOT_OBSERVED")
    if "PRESENT" in (report["state"]["stop_request"], report["state"]["checkout_stop"],
                     report["worktree"]["primary_worktree_stop"]):
        report["blockers"].insert(0, "STOP_MARKER_PRESENT")
    print(json.dumps(report, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
