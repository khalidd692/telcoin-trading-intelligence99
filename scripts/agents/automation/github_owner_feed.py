"""Read-only discovery of new owner-authorized TEL99 GitHub controllers.

No issue, approval, mandate, label or PR is ever created here. Agents may
suggest work elsewhere; this module only admits human-owner-authored, unedited
mandates whose full child approvals pass LocalCodeCampaign.preflight().
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from scripts.agents.automation.github_mission_source import (
    approval_is_current, fetch_comments, fenced_json, gh_json, is_owner,
)
from scripts.agents.automation.github_local_code_campaign import MANDATE, LocalCodeCampaign
from scripts.agents.automation.kilo_github_adapter import REPO
from scripts.agents.automation.local_code_pr import valid_campaign_base
from scripts.agents.protocol.store import FileStore, StoreError

OWNER_MARKER = "tel99-autofeed-controller/v1"
CUTOFF_ISSUE = 203  # Historical controllers #178/#191/#192/#199 are never replayed.
MAX_DISCOVERY_PAGES = 3
MAX_CONTROLLERS = 10
PIN_KEY = "owner-feed/controller-pins"


def default_fetch(endpoint):
    return gh_json(endpoint, timeout=8)


def _owner_controller(row):
    return (
        isinstance(row, dict) and type(row.get("number")) is int
        and row["number"] > CUTOFF_ISSUE and row.get("state") == "open"
        and "pull_request" not in row and is_owner(row.get("user"))
        and isinstance(row.get("body"), str)
        and OWNER_MARKER in row["body"].splitlines()
    )


def discover_owner_pins(*, fetcher=default_fetch):
    """Only owner-marked issues with one immutable owner-authored mandate qualify.

    This merely discovers candidate pins. The separate receiver independently
    re-reads GitHub, verifies permissions, all mission approvals and immutable
    base SHA before any worker can run.
    """
    if not is_owner(fetcher("user")):
        raise ValueError("GitHub session is not the pinned repository owner")
    selected = []
    numbers = set()
    ended = False
    for page in range(1, MAX_DISCOVERY_PAGES + 1):
        endpoint = (f"repos/{REPO}/issues?state=open&sort=created"
                    f"&direction=desc&per_page=100&page={page}")
        rows = fetcher(endpoint)
        if not isinstance(rows, list):
            raise ValueError("invalid GitHub owner-feed issue list")
        for row in rows:
            if _owner_controller(row):
                issue = row["number"]
                if issue in numbers:
                    raise ValueError("duplicate controller in GitHub discovery")
                numbers.add(issue)
                comments = fetch_comments(REPO, issue, fetcher=fetcher, max_pages=3)
                mandates = []
                for c in comments:
                    if not (isinstance(c, dict) and is_owner(c.get("user"))
                            and type(c.get("id")) is int and c["id"] > 0
                            and c.get("issue_url") == f"https://api.github.com/repos/{REPO}/issues/{issue}"
                            and isinstance(c.get("created_at"), str)
                            and c["created_at"] == c.get("updated_at")):
                        continue
                    scope = fenced_json(c.get("body"), MANDATE)
                    if scope is not None:
                        mandates.append((c, scope))
                if len(mandates) != 1:
                    raise ValueError(f"controller #{issue} must have exactly one immutable owner mandate")
                comment, scope = mandates[0]
                if (set(scope) != {"repo", "issue", "label", "expires_at", "base", "base_sha", "contracts"}
                        or scope["repo"] != REPO or scope["issue"] != issue
                        or scope["label"] != "enhancement"
                        or not approval_is_current(scope, datetime.now(timezone.utc))
                        or not valid_campaign_base(scope["base"], scope["base_sha"])
                        or not isinstance(scope["contracts"], dict)
                        or not 2 <= len(scope["contracts"]) <= 10
                        or any(not isinstance(mid, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,48}", mid)
                               or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                               for mid, digest in scope["contracts"].items())):
                    raise ValueError(f"controller #{issue} has an invalid approved mandate")
                selected.append({
                    "issue": issue,
                    "mandate_comment": comment["id"],
                    "mandate_sha256": hashlib.sha256(comment["body"].encode("utf-8")).hexdigest(),
                    "base_ref": scope["base"], "base_sha": scope["base_sha"],
                })
                if len(selected) > MAX_CONTROLLERS:
                    raise ValueError("owner-approved controller queue exceeds limit")
        if len(rows) < 100 or (rows and min(
                (row["number"] for row in rows if isinstance(row, dict)
                 and type(row.get("number")) is int), default=0) <= CUTOFF_ISSUE):
            ended = True
            break
    if not ended:
        raise ValueError("GitHub owner-feed pagination cap; refusing to miss a controller")
    return sorted(selected, key=lambda item: item["issue"])


def pinned_owner_feed(root, *, fetcher=default_fetch):
    """Persist the first trusted pins before scheduling; never silently re-pin."""
    root = Path(root).resolve()
    remote = discover_owner_pins(fetcher=fetcher)
    store = FileStore(root / "feed-ledger")
    record = store.get(PIN_KEY)
    if record is None:
        record = {"version": 1, "pins": []}
    if (not isinstance(record, dict) or set(record) != {"version", "pins"}
            or record["version"] != 1 or not isinstance(record["pins"], list)):
        raise ValueError("invalid durable owner-feed pin ledger")
    existing = {item["issue"]: item for item in record["pins"]}
    if len(existing) != len(record["pins"]):
        raise ValueError("duplicate controller in durable owner-feed")
    discovered = {item["issue"]: item for item in remote}
    # A previously pinned controller that vanishes must never silently disappear.
    for issue, previous in existing.items():
        if discovered.get(issue) != previous:
            raise ValueError(f"controller #{issue} disappeared or its signed mandate changed")
    added = [spec for spec in remote if spec["issue"] not in existing]
    if added:
        next_record = {"version": 1, "pins": sorted([*record["pins"], *added],
                                                      key=lambda item: item["issue"])}
        try:
            if not store.put_cas(PIN_KEY, next_record, None if not existing else record):
                raise ValueError("owner-feed CAS conflict; reload before retry")
        except StoreError as exc:
            raise ValueError("owner-feed CAS persistence unavailable") from exc
        record = next_record
    return record["pins"]
