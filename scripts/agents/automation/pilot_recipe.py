"""Exact, reviewable configuration for the single TEL99 OpenHands *pilot*
automation, plus pure decision helpers.

This module is read-only and fully offline: it performs **no** network call,
starts **no** conversation and writes **no** file. It only *describes* the one
"Custom automation" the owner asked for in issue #86 and validates it against
the hard safety rules of that issue, so the recipe can be reviewed and unit
tested before any human creates it.

Design rules encoded here (issue #86, "nuit sûre"):

  * exactly ONE pilot automation -- never a fleet;
  * created INACTIVE and driven only by an explicit manual dispatch
    (``enabled=false``, ``state=INACTIVE``); no cron, ever;
  * ``dry_run=true`` for the first test: a mission is selected and validated
    but NO conversation is started (enforced in ``orchestrator.py`` before the
    only ``POST /api/conversations``);
  * a real launch is refused below a free-conversation floor of 12/20;
  * the free model only -- any paid model id is a hard refusal;
  * at most one mission at a time (schema + code);
  * the automation never writes to GitHub (a single GET), so it cannot loop.

Nothing here installs, deploys, enables or dispatches anything.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# --------------------------------------------------------------------------
# Fixed, reviewable constants
# --------------------------------------------------------------------------

# The plugin source already referenced by the account's existing automations,
# i.e. the repo's own plugin manifest at ``.plugin/plugin.json``.
PLUGIN_SOURCE = "github:khalidd692/telcoin-trading-intelligence99"
PLUGIN_REPO_PATH = ".plugin"

# The only repository the recipe is allowed to serve (mirrors
# ``policy.ALLOWED_REPOSITORIES``); kept here so the recipe is self-checking.
ALLOWED_REPOSITORY = "khalidd692/telcoin-trading-intelligence99"

# The single automation's human name.
PILOT_NAME = "TEL99 pilot - single manual mission (dry_run, no cron)"

# Free-model ids only. The profile name (underscore) and the API model id
# (slash) are both accepted; anything else is a paid model and is refused.
FREE_MODEL_IDS = frozenset(
    {
        "openhands/deepseek-v4.1-flash",
        "openhands_deepseek-v4.1-flash",
    }
)

# Free conversations that must remain before a real launch (10 in reserve out
# of a 20/day cap). Below this, a real launch is refused. ``dry_run`` is not a
# launch, so it is not subject to the floor.
MIN_QUOTA_REQUIRED = 12

# Branches the automation must never branch from or push to.
PROTECTED_BRANCHES = frozenset(
    {"main", "master", "tel99-live-data", "tel99-evaluation-data"}
)
PROTECTED_PREFIXES = ("tel99-",)

# Hard cap: one mission at a time.
MAX_CONCURRENT_MISSIONS = 1


def pilot_recipe() -> dict[str, Any]:
    """Return the exact ``config`` object for the single pilot automation.

    The keys match ``.plugin/plugin.json -> automation.config_schema`` exactly
    (``additionalProperties: false``), so the object can be sent as the
    ``config`` of a ``POST /api/automation/v1/plugin-spec`` request without any
    transformation.
    """
    return {
        "repository": ALLOWED_REPOSITORY,
        "mission_label": "tel99-mission",
        # NOT a protected branch: work is cut from the team branch.
        "base_branch": "agents/hermes-simple-team-20261114",
        "work_branch_prefix": "agent/mission-",
        "max_concurrent_missions": MAX_CONCURRENT_MISSIONS,
        # 20 minutes maximum per the owner's "safe night" policy.
        "max_runtime_seconds": 1200,
        "max_iterations": 30,
        "max_budget_usd": 1.0,
        "agent_max_iterations": 10,
        "agent_max_budget_usd": 0.25,
        # Owner's floor: never start a real mission with fewer than 12 left.
        "quota_min_remaining": MIN_QUOTA_REQUIRED,
        # The first test is a rehearsal: select + validate, start nothing.
        "dry_run": True,
        "require_durable_bus": True,
        "emergency_stop": False,
        "authorized_approvers": [],
    }


def plugin_spec_request(recipe: dict[str, Any] | None = None,
                        ref: str = "main") -> dict[str, Any]:
    """Return the full ``POST /api/automation/v1/plugin-spec`` request body.

    This is a *description*, not a call. It shows exactly what a human would
    send (or what the UI form would fill) to create the pilot. The automation
    is created INACTIVE; ``manual_only`` is realised by the lifecycle, not by a
    trigger field, because the platform has no "manual" trigger type.
    """
    config = dict(recipe) if recipe is not None else pilot_recipe()
    return {
        "name": PILOT_NAME,
        "plugin": {
            "source": PLUGIN_SOURCE,
            "repo_path": PLUGIN_REPO_PATH,
            "ref": ref,
        },
        "config": config,
    }


def lifecycle() -> dict[str, Any]:
    """The lifecycle that makes the pilot manual-only and inert.

    ``enabled=false`` + ``state=INACTIVE`` means the automation never runs on
    its own; the only way to start a run is an explicit
    ``POST /api/automation/v1/{id}/dispatch``. There is no cron.
    """
    return {
        "enabled": False,
        "state": "INACTIVE",
        "manual_dispatch_only": True,
        "cron": None,
    }


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _is_paid_model(model_id: str | None) -> bool:
    if not model_id:
        return True
    return model_id not in FREE_MODEL_IDS


def validate_recipe(recipe: dict[str, Any] | None = None,
                    model_id: str = "openhands/deepseek-v4.1-flash") -> list[str]:
    """Return the list of reasons the recipe must NOT be created (empty = ok).

    Every reason is a plain, quotable string so it can be written verbatim to
    the report. The check is deliberately strict: a single violation blocks.
    """
    r = dict(recipe) if recipe is not None else pilot_recipe()
    reasons: list[str] = []

    if r.get("repository") not in {ALLOWED_REPOSITORY}:
        reasons.append(f"repository {r.get('repository')!r} is not the allowlisted one")

    if r.get("dry_run") is not True:
        reasons.append(
            "dry_run must be true for the pilot: the first test starts no conversation"
        )

    if r.get("max_concurrent_missions") != MAX_CONCURRENT_MISSIONS:
        reasons.append(
            f"max_concurrent_missions must be {MAX_CONCURRENT_MISSIONS}, "
            f"got {r.get('max_concurrent_missions')!r}"
        )

    floor = r.get("quota_min_remaining")
    if not isinstance(floor, int) or floor < MIN_QUOTA_REQUIRED:
        reasons.append(
            f"quota_min_remaining must be >= {MIN_QUOTA_REQUIRED}, got {floor!r}"
        )

    runtime = r.get("max_runtime_seconds")
    if not isinstance(runtime, int) or runtime > 1800:
        reasons.append(
            f"max_runtime_seconds must be <= the platform ceiling 1800, got {runtime!r}"
        )

    if r.get("require_durable_bus") is not True:
        reasons.append("require_durable_bus must be true for a cloud run")

    if r.get("emergency_stop") not in (False, None):
        reasons.append("emergency_stop must be false in the stored recipe")

    base = str(r.get("base_branch", ""))
    if base in PROTECTED_BRANCHES or base.startswith(PROTECTED_PREFIXES):
        reasons.append(f"base_branch {base!r} is protected")

    if _is_paid_model(model_id):
        reasons.append(f"model {model_id!r} is not in the free allowlist")

    # The recipe must not carry an unknown key (schema is additionalProperties:false).
    known = set(pilot_recipe().keys())
    extra = set(r.keys()) - known
    if extra:
        reasons.append(f"unknown config keys: {sorted(extra)}")

    return reasons


# --------------------------------------------------------------------------
# Launch decision (pure)
# --------------------------------------------------------------------------

def launch_decision(quota_remaining: int | None,
                    *,
                    dry_run: bool = True,
                    min_remaining: int = MIN_QUOTA_REQUIRED) -> dict[str, Any]:
    """Decide whether a launch is allowed, fail-closed.

    * ``dry_run`` starts no conversation, so it is always allowed (the floor
      protects real launches only).
    * A real launch with an UNKNOWN quota is refused ("INCONNU - lancement
      interdit").
    * A real launch below ``min_remaining`` is refused.
    """
    if dry_run:
        return {
            "allowed": True,
            "status": "dry_run",
            "reason": "dry_run starts no conversation",
            "quota_remaining": quota_remaining,
            "min_remaining": min_remaining,
        }
    if quota_remaining is None:
        return {
            "allowed": False,
            "status": "unknown",
            "reason": "quota unknown: launch forbidden",
            "quota_remaining": None,
            "min_remaining": min_remaining,
        }
    if quota_remaining < min_remaining:
        return {
            "allowed": False,
            "status": "blocked_quota",
            "reason": f"{quota_remaining} left, minimum {min_remaining} required",
            "quota_remaining": quota_remaining,
            "min_remaining": min_remaining,
        }
    return {
        "allowed": True,
        "status": "allowed",
        "reason": f"{quota_remaining} left, minimum {min_remaining} satisfied",
        "quota_remaining": quota_remaining,
        "min_remaining": min_remaining,
    }


# --------------------------------------------------------------------------
# Inventory view (pure)
# --------------------------------------------------------------------------

def inventory_view(automations: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Normalise the raw ``GET /api/automation/v1`` payload for reporting.

    Makes the "No automations yet" question answerable from data: the count and
    each entry's lifecycle are surfaced, and any *active* automation is flagged
    because the owner asked for none.
    """
    items = list(automations or [])
    view: list[dict[str, Any]] = []
    for a in items:
        state = a.get("state") or ("ACTIVE" if a.get("enabled") else "INACTIVE")
        view.append(
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "state": state,
                "enabled": bool(a.get("enabled")),
                "manual_only": (not a.get("enabled")) and a.get("trigger", {}).get("type") != "cron",
                "trigger_type": (a.get("trigger") or {}).get("type"),
                "model": a.get("model"),
                "ref": ((a.get("plugin_spec") or {}).get("plugin") or {}).get("ref"),
                "dry_run": ((a.get("plugin_spec") or {}).get("config") or {}).get("dry_run"),
            }
        )
    active = [v["id"] for v in view if v["enabled"]]
    return {
        "count": len(view),
        "automations": view,
        "active_count": len(active),
        "active_ids": active,
        "note": (
            "an inactive automation is not shown as active in the UI; "
            "the count here is what the API returns"
        ),
    }


def dedup_key(repository: str, issue_number: int, title: str) -> str:
    """A stable anti-duplicate key for one mission (same input -> same key)."""
    stem = f"{repository}#{issue_number}:{(title or '').strip().lower()}"
    return hashlib.sha256(stem.encode("utf-8")).hexdigest()[:16]


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", action="store_true",
                        help="print the exact pilot config as JSON")
    parser.add_argument("--request", action="store_true",
                        help="print the full plugin-spec create request as JSON")
    parser.add_argument("--validate", action="store_true",
                        help="validate the pilot recipe (exit 0 ok, 2 violations)")
    args = parser.parse_args(argv)

    if args.request:
        print(json.dumps(plugin_spec_request(), indent=2, ensure_ascii=False))
        return 0
    if args.recipe:
        print(json.dumps(pilot_recipe(), indent=2, ensure_ascii=False))
        return 0
    # default / --validate
    problems = validate_recipe()
    if problems:
        print("INVALID pilot recipe:")
        for p in problems:
            print(f"  - {p}")
        return 2
    print("Pilot recipe valid: dry_run=true, manual-only, max 1 mission, "
          f"quota floor {MIN_QUOTA_REQUIRED}, free model only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
