"""Pure, network-free logic for the TEL99 Agent Mission Control cockpit.

This module contains every non-trivial decision the cockpit makes, so those
decisions can be unit-tested without a browser, a network or a token. The
build script (``cockpit/build_data.py``) fetches raw inputs and calls these
functions; the browser only renders the resulting JSON.

Design invariants enforced here and covered by ``tests/test_cockpit.py``:

  * An unknown quota is NEVER turned into "sufficient" or a number.
  * An agent is "running" only when an explicit, sourced start event has no
    later completion -- otherwise the cockpit shows "dernière activité
    connue", never a fabricated live stream.
  * Every section carries a ``source`` so a claim can be re-checked.
"""

from __future__ import annotations

from typing import Any

# The three active roles of the TEL99 team (see .agents/agents/*.md).
ROLES: tuple[str, ...] = ("analyst", "developer", "verifier")

AGENT_LABELS: dict[str, str] = {
    "analyst": "Analyste",
    "developer": "Développeur",
    "verifier": "Vérificateur",
}

# Minimum free conversations that must remain before a real launch is allowed.
# Issue #86 "safe night" policy: keep 10 in reserve out of a 20/day cap.
MIN_QUOTA_REQUIRED: int = 12

# Mission phases, most specific first.
PHASES = ("bloquee", "en_cours", "terminee", "en_attente", "inconnue")

PHASE_LABELS: dict[str, str] = {
    "en_attente": "En attente",
    "en_cours": "En cours",
    "terminee": "Terminée",
    "bloquee": "Bloquée",
    "inconnue": "Inconnue",
}


def quota_view(quota: dict[str, Any] | None,
               min_required: int = MIN_QUOTA_REQUIRED) -> dict[str, Any]:
    """Normalise a raw quota reading into a display-safe view.

    ``quota`` is ``None`` when the API could not be read, or a dict with at
    least ``remaining`` when it could. When ``remaining`` is missing the view
    is explicitly ``unknown`` -- the UI then prints "INCONNU — lancement
    interdit" and never a fabricated number.
    """
    src = (quota or {}).get("source", "non interrogé")
    if not quota or quota.get("remaining") is None:
        return {
            "status": "unknown",
            "verdict": "unknown",
            "label": "INCONNU",
            "remaining": None,
            "daily_limit": (quota or {}).get("daily_limit"),
            "used_today": (quota or {}).get("used_today"),
            "measured_at": (quota or {}).get("measured_at"),
            "reset_at": (quota or {}).get("reset_at"),
            "credits": (quota or {}).get("credits"),
            "source": src,
            "min_required": min_required,
            "message": "INCONNU — lancement interdit (quota non lisible).",
        }

    remaining = int(quota["remaining"])
    verdict = "sufficient" if remaining >= min_required else "insufficient"
    if verdict == "sufficient":
        message = (f"Quota suffisant : {remaining} conversation(s) libre(s) "
                   f"(≥ {min_required} requis).")
    else:
        message = (f"Quota insuffisant : {remaining} conversation(s) libre(s) "
                   f"(< {min_required} requis) — lancement interdit.")
    return {
        "status": "known",
        "verdict": verdict,
        "label": f"{remaining} / {quota.get('daily_limit', '?')}",
        "remaining": remaining,
        "daily_limit": quota.get("daily_limit"),
        "used_today": quota.get("used_today"),
        "measured_at": quota.get("measured_at"),
        "reset_at": quota.get("reset_at"),
        "credits": quota.get("credits"),
        "source": src,
        "min_required": min_required,
        "message": message,
    }


def agent_view(role: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive one agent's display state from real, sourced events only.

    Returns a dict whose ``state`` is one of ``running``/``done``/``blocked``/
    ``unknown``. ``current_task`` is non-null ONLY when the last event for that
    role is an uncompleted start -- i.e. the events prove the agent is busy.
    Otherwise the cockpit shows ``last_activity`` and the wording "dernière
    activité connue".
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")

    relevant = [e for e in events if e.get("agent") == role]
    view: dict[str, Any] = {
        "role": role,
        "label": AGENT_LABELS[role],
        "state": "unknown",
        "state_source": None,
        "current_task": None,
        "last_activity": None,
        "last_activity_at": None,
        "duration_s": None,
        "evidence": [],
    }
    if not relevant:
        return view

    last = relevant[-1]
    view["state_source"] = last.get("source")
    view["last_activity"] = last.get("summary")
    view["last_activity_at"] = last.get("at")
    view["evidence"] = [e for e in relevant if e.get("kind") in
                        ("task_start", "task_end", "blocked", "evidence")][-4:]

    kind = last.get("kind")
    if kind == "task_start":
        view["state"] = "running"
        view["current_task"] = last.get("summary")
    elif kind == "blocked":
        view["state"] = "blocked"
    else:  # task_end / comment / memory_* etc.
        view["state"] = "done"

    if last.get("duration_s") is not None:
        view["duration_s"] = last["duration_s"]
    return view


def mission_phase(events: list[dict[str, Any]]) -> str:
    """Return the mission phase proven by the events, most severe last.

    A ``blocked`` event wins; otherwise an uncompleted start means the mission
    is running; otherwise a terminal event means finished; with no events the
    phase is ``en_attente`` (queued), not a fabricated success.
    """
    if not events:
        return "en_attente"
    kinds = [e.get("kind") for e in events]
    if "blocked" in kinds[-1:]:
        return "bloquee"
    if "blocked" in kinds:
        return "bloquee"
    if kinds and kinds[-1] in ("task_start", "run_start"):
        return "en_cours"
    if any(k in ("task_end", "run_end", "done") for k in kinds):
        return "terminee"
    if "run_start" in kinds:
        return "en_cours"
    return "en_attente"


def delegation_graph(agents: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a delegation graph from the real agent states.

    Nodes are the coordinator plus the three roles; edges are coordinator ->
    role, present only when that role has sourced evidence. Edge ``state``
    mirrors the agent state so the graph never claims more than the events do.
    """
    nodes = [{"id": "coordinator", "label": "Coordinateur", "kind": "coordinator"}]
    edges = []
    for a in agents:
        nodes.append({"id": a["role"], "label": a["label"], "kind": "agent",
                      "state": a["state"]})
        if a["state"] != "unknown":
            edges.append({"from": "coordinator", "to": a["role"],
                          "state": a["state"]})
    return {"nodes": nodes, "edges": edges}


def controls_view(controls: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise the control panel.

    Launch/Stop buttons are emitted ONLY when a real, authorised API is wired
    (``actions[].wired is True``). Otherwise the cockpit stays read-only and
    says why, so a dead button is never shown as if it worked.
    """
    controls = controls or {}
    actions = []
    for action in controls.get("actions", []):
        wired = bool(action.get("wired"))
        actions.append({
            "id": action.get("id"),
            "label": action.get("label"),
            "wired": wired,
            "enabled": wired and bool(action.get("enabled", True)),
            "reason": action.get("reason") or (
                "Relié à une API autorisée." if wired else
                "Lecture seule : aucune API de lancement autorisée n'est "
                "raccordée. Aucun bouton simulé."),
            "url": action.get("url"),
        })
    return {
        "lock": controls.get("lock") or {"state": "inconnu", "source": None},
        "emergency_stop": controls.get("emergency_stop")
        or {"state": "inconnu", "source": None},
        "automation": controls.get("automation")
        or {"state": "INCONNU", "source": None},
        "max_duration_s": controls.get("max_duration_s"),
        "actions": actions,
        "read_only": not any(a["enabled"] for a in actions),
    }


def build_dataset(raw: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full cockpit dataset from already-fetched raw inputs.

    ``raw`` keys: ``generated_at``, ``quota`` (dict|None), ``memory``,
    ``events`` (list), ``mission``, ``runs``, ``controls``. Nothing here
    performs I/O, so the whole transformation is deterministic and testable.
    """
    events = list(raw.get("events") or [])
    agents = [agent_view(role, events) for role in ROLES]
    phase = mission_phase(events)
    mission = dict(raw.get("mission") or {})
    mission["phase"] = phase
    mission["phase_label"] = PHASE_LABELS.get(phase, "Inconnue")

    live = any(a["state"] == "running" for a in agents)
    return {
        "generated_at": raw.get("generated_at"),
        "live": live,
        "mission": mission,
        "agents": agents,
        "timeline": sorted(events, key=lambda e: e.get("at") or ""),
        "delegation_graph": delegation_graph(agents),
        "quota": quota_view(raw.get("quota")),
        "memory": raw.get("memory") or {"entries": [], "source": None},
        "controls": controls_view(raw.get("controls")),
        "provenance": raw.get("provenance") or {},
    }
