#!/usr/bin/env python3
"""Build the cockpit dataset (``cockpit/data.json``) from real, sourced inputs.

Run server-side only. The GitHub/OpenHands tokens are read from the
environment here and are NEVER written into the output: the browser receives
only the curated dataset produced by :func:`cockpit.model.build_dataset`.

Usage::

    python3 cockpit/build_data.py                 # live: GitHub + quota API
    python3 cockpit/build_data.py --offline       # no network; INCONNU quota

The output is deterministic given the same inputs, so it can be diffed and
reviewed. Nothing in this script starts a conversation, spends credit, or
writes outside ``cockpit/data.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from cockpit import model  # noqa: E402

REPO = "khalidd692/telcoin-trading-intelligence99"
CLOUD_API = os.environ.get("OPENHANDS_CLOUD_API_URL",
                           "https://app.all-hands.dev").rstrip("/")
GITHUB_API = "https://api.github.com"
HERE = pathlib.Path(__file__).resolve().parent
MEMORY_STORE = HERE.parent / "memory" / "projects" / "tel99.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _get_json(url: str, token: str | None, accept: str = "application/vnd.github+json"):
    """GET a URL and return (status, parsed_body). Never raises on HTTP errors."""
    headers = {"User-Agent": "tel99-cockpit", "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


# --------------------------------------------------------------------------- #
# Fetchers (each returns already-curated data plus its provenance string)
# --------------------------------------------------------------------------- #
def fetch_quota() -> dict:
    """Read the free-conversation quota. Returns an 'unknown' view on failure."""
    key = os.environ.get("OPENHANDS_API_KEY") or os.environ.get("TEL99_CLOUD_API_KEY")
    source = f"GET {CLOUD_API}/api/quota/status"
    if not key:
        return {"source": source + " (aucune clé en environnement)"}
    status, body = _get_json(f"{CLOUD_API}/api/quota/status", key,
                             accept="application/json")
    if status == 200 and isinstance(body, dict):
        return {
            "remaining": body.get("remaining"),
            "daily_limit": body.get("daily_limit"),
            "used_today": body.get("used_today"),
            "reset_at": body.get("reset_at"),
            "credits": body.get("credits"),
            "measured_at": _utcnow(),
            "source": source,
        }
    return {"source": f"{source} (HTTP {status})"}


def fetch_issue(number: int) -> dict | None:
    token = os.environ.get("GITHUB_TOKEN")
    status, body = _get_json(f"{GITHUB_API}/repos/{REPO}/issues/{number}", token)
    if status == 200 and isinstance(body, dict):
        return {
            "number": number,
            "title": body.get("title"),
            "state": body.get("state"),
            "html_url": body.get("html_url"),
            "updated_at": body.get("updated_at"),
        }
    return None


def fetch_issue_comments(number: int) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    status, body = _get_json(
        f"{GITHUB_API}/repos/{REPO}/issues/{number}/comments?per_page=100", token)
    if status == 200 and isinstance(body, list):
        return body
    return []


def fetch_pull(number: int) -> dict | None:
    token = os.environ.get("GITHUB_TOKEN")
    status, body = _get_json(f"{GITHUB_API}/repos/{REPO}/pulls/{number}", token)
    if status == 200 and isinstance(body, dict):
        return {
            "number": number,
            "title": body.get("title"),
            "state": body.get("state"),
            "draft": body.get("draft"),
            "merged": body.get("merged"),
            "html_url": body.get("html_url"),
            "head": (body.get("head") or {}).get("ref"),
        }
    return None


def read_memory() -> dict:
    """Read the versioned memory store; report the most recent entry as proof."""
    try:
        data = json.loads(MEMORY_STORE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"entries": [], "source": f"{MEMORY_STORE} illisible: {exc}"}
    entries = data.get("entries", [])
    curated = [{
        "id": e.get("id"),
        "project": e.get("project"),
        "kind": e.get("kind"),
        "title": e.get("title"),
        "version": e.get("version"),
        "verified": e.get("verified"),
        "verified_by": e.get("verified_by"),
        "source": e.get("source"),
        "commit": e.get("commit"),
        "created_at": e.get("created_at"),
        "tags": e.get("tags"),
    } for e in entries]
    latest = max(curated, key=lambda e: e.get("created_at") or "", default=None)
    return {
        "entries": curated,
        "latest": latest,
        "source": f"{MEMORY_STORE.relative_to(MEMORY_STORE.parent.parent.parent)}"
                  f" (schema {data.get('schema')})",
    }


# --------------------------------------------------------------------------- #
# Provenance-carrying event assembly
# --------------------------------------------------------------------------- #
def build_events(issues: dict[int, dict], comments: dict[int, list[dict]]) -> list[dict]:
    """Turn real issue/PR facts into timeline events, each with its source URL.

    We only emit events that a GitHub issue or comment actually supports: a
    bot 'on it' comment becomes a ``run_start``; a coordinator report becomes a
    ``task_end``; an explicit BLOCKED report becomes ``blocked``. No event is
    invented, and each carries the URL it came from.
    """
    events: list[dict] = []
    role_markers = {
        "analyst": ("analyst", "analyste"),
        "developer": ("dev", "développeur", "developpeur"),
        "verifier": ("verifier", "vérificateur", "verificateur"),
    }

    for number in sorted(issues):
        issue = issues[number]
        if not issue:
            continue
        for c in comments.get(number, []):
            body = (c.get("body") or "")
            low = body.lower()
            at = c.get("created_at")
            url = c.get("html_url")
            author = (c.get("user") or {}).get("login")
            is_bot = author and author.endswith("[bot]")
            if "conversations/" in low and is_bot:
                events.append({
                    "at": at, "agent": "coordinator", "kind": "run_start",
                    "summary": f"Conversation ouverte pour #{number}",
                    "source": url, "issue": number,
                })
            elif "blocked_quota" in low or "bloquee" in low or "bloqué" in low:
                events.append({
                    "at": at, "agent": "coordinator", "kind": "blocked",
                    "summary": f"Blocage déclaré sur #{number}",
                    "source": url, "issue": number,
                })
            elif "mission #" in low or "mission terminée" in low or "verdict" in low:
                events.append({
                    "at": at, "agent": "coordinator", "kind": "task_end",
                    "summary": f"Rapport de mission sur #{number}",
                    "source": url, "issue": number,
                })
            for role, keys in role_markers.items():
                if any(k in low for k in keys):
                    events.append({
                        "at": at, "agent": role, "kind": "evidence",
                        "summary": f"Mention {role} dans #{number}",
                        "source": url, "issue": number,
                    })
                    break
    # Deduplicate identical (at, agent, kind, source).
    seen = set()
    unique = []
    for e in sorted(events, key=lambda x: x.get("at") or ""):
        key = (e["at"], e["agent"], e["kind"], e["source"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def build_live(offline: bool) -> dict:
    """Assemble the raw dataset from live sources (or offline stubs)."""
    issues_meta: dict[int, dict] = {}
    comments: dict[int, list[dict]] = {}
    pulls: dict[int, dict] = {}
    wanted_issues = [77, 80, 84, 86]
    wanted_pulls = [76, 79, 85]

    quota = {"source": "non interrogé (mode hors-ligne)"}
    if not offline:
        quota = fetch_quota()
        for n in wanted_issues:
            issues_meta[n] = fetch_issue(n) or {}
            comments[n] = fetch_issue_comments(n)
        for n in wanted_pulls:
            pulls[n] = fetch_pull(n) or {}

    memory = read_memory()
    events = build_events(issues_meta, comments) if not offline else []

    # Mission: the cockpit's own mission is issue #86 (the current one).
    mission_issue = issues_meta.get(86) or {}
    mission = {
        "number": 86,
        "title": mission_issue.get("title")
        or "Cockpit Android + autonomie nocturne économe",
        "objective": "Voir les 3 agents travailler depuis un téléphone Android, "
                     "sans copier-coller, sans brûler le quota.",
        "issue_url": mission_issue.get("html_url")
        or f"https://github.com/{REPO}/issues/86",
        "openhands_url": "https://app.all-hands.dev/canvas/conversations/"
                         "045089f6e33746639d488453de214c7c",
        "timestamp": _utcnow(),
    }

    runs = {
        "quota_used_today": quota.get("used_today"),
        "prs": pulls,
    }

    controls = {
        "lock": {"state": "inconnu",
                 "source": "Aucun backend KV interrogé depuis le cockpit (lecture seule)."},
        "emergency_stop": {"state": "inconnu",
                           "source": "Kill-switch non interrogé (lecture seule)."},
        "automation": {"state": "INACTIVE",
                       "source": "Issue #86 : aucune automation récurrente activée ; "
                                 "2 automatisations de test laissées INACTIVE."},
        "max_duration_s": 1800,
        "actions": [
            {"id": "launch", "label": "Lancer une mission",
             "wired": False, "url": f"https://github.com/{REPO}/issues/new"},
            {"id": "stop", "label": "Arrêt d'urgence",
             "wired": False},
        ],
    }

    provenance = {
        "quota": quota.get("source"),
        "memory": memory.get("source"),
        "issues": [f"https://github.com/{REPO}/issues/{n}" for n in wanted_issues],
        "pulls": [f"https://github.com/{REPO}/pull/{n}" for n in wanted_pulls],
        "events": "commentaires GitHub réels (voir source de chaque entrée)",
        "generator": "cockpit/build_data.py",
    }

    raw = {
        "generated_at": _utcnow(),
        "quota": quota,
        "memory": memory,
        "events": events,
        "mission": mission,
        "runs": runs,
        "controls": controls,
        "provenance": provenance,
    }
    return model.build_dataset(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the TEL99 cockpit dataset.")
    parser.add_argument("--offline", action="store_true",
                        help="No network calls; quota becomes INCONNU.")
    parser.add_argument("--out", default=str(HERE / "data.json"))
    args = parser.parse_args(argv)

    dataset = build_live(offline=args.offline)
    pathlib.Path(args.out).write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    q = dataset["quota"]
    print(f"[cockpit] wrote {args.out}")
    print(f"[cockpit] quota: {q['label']} ({q['verdict']}) source={q['source']}")
    print(f"[cockpit] agents: " + ", ".join(
        f"{a['label']}={a['state']}" for a in dataset["agents"]))
    print(f"[cockpit] events: {len(dataset['timeline'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
