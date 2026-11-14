"""TEL99 multi-agent team configuration (single source of truth).

This module is deliberately stdlib-only so it can be imported both by the
launcher scripts and by the CI tests, without the OpenHands SDK installed.

The three pilot roles (dev, analyst, verifier) are ACTIVE. The remaining
specializations of the TEL99 role catalogue are RESERVED: their definitions
live in ``.agents/agents/reserve/`` and are never auto-discovered by the SDK
(which only reads top-level ``*.md`` files).
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

# Free model currently available in this environment. Override with
# TEL99_LLM_MODEL to switch to another saved profile without editing code.
DEFAULT_MODEL = os.environ.get("TEL99_LLM_MODEL", "openhands/deepseek-v4.1-flash")

# Consumption limits. Overridable per run via environment variables so a
# session can be cheap by default and larger only when explicitly requested.
DEFAULT_MAX_ITERATIONS = int(os.environ.get("TEL99_MAX_ITERATIONS", "30"))
DEFAULT_MAX_BUDGET_USD = float(os.environ.get("TEL99_MAX_BUDGET_USD", "1.0"))
DEFAULT_AGENT_MAX_ITERATIONS = int(os.environ.get("TEL99_AGENT_MAX_ITERATIONS", "10"))
DEFAULT_AGENT_MAX_BUDGET_USD = float(os.environ.get("TEL99_AGENT_MAX_BUDGET_USD", "0.25"))

# Hard safety floor: never let a run start with an unbounded budget.
MAX_BUDGET_CEILING_USD = float(os.environ.get("TEL99_MAX_BUDGET_CEILING_USD", "5.0"))

READ_ONLY_CONTRACT = (
    "CONTRAINTE DURE (non negociable): LECTURE SEULE. Interdiction de modifier un "
    "fichier du depot, de faire git commit/push/checkout/switch, de deployer, "
    "d'installer un paquet, de passer un ordre (reel ou simule), d'afficher ou de "
    "copier un secret. Autorise: ls/cat/grep/git log|show|status|rev-parse. "
    "Un garde-fou (hook PreToolUse) bloque au runtime toute commande interdite."
)


@dataclass(frozen=True)
class AgentSpec:
    """A single TEL99 agent definition (active or reserved)."""

    role: str
    name: str
    description: str
    system_prompt: str
    tools: tuple[str, ...] = ("terminal",)
    permission_mode: str = "confirm_risky"
    level: str = "project"
    active: bool = True
    extra_prompt: str = ""
    metadata: dict = field(default_factory=dict)

    def frontmatter(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "model": "inherit",
            "permission_mode": self.permission_mode,
            "tools": list(self.tools),
            "max_iteration_per_run": DEFAULT_AGENT_MAX_ITERATIONS,
            "max_budget_per_run": DEFAULT_AGENT_MAX_BUDGET_USD,
        }

    def full_prompt(self) -> str:
        parts = [self.system_prompt.strip()]
        if self.extra_prompt:
            parts.append(self.extra_prompt.strip())
        parts.append(READ_ONLY_CONTRACT)
        return "\n\n".join(parts)


# --- Active roles: the 3-agent pilot team ---------------------------------
_DEV = AgentSpec(
    role="development",
    name="tel99-dev",
    description=(
        "TEL99 Developer. Use for a read-only specialist review of Python/JS code "
        "with verifiable evidence."
    ),
    system_prompt=(
        "Investigate Python and JavaScript issues; propose minimal changes without "
        "applying them. Before starting, read AGENTS.md, issues #60/#61 and the "
        "required Smart View handovers. State which commands were actually run, cite "
        "paths and relevant logs, and distinguish findings from hypotheses."
    ),
)
_ANALYST = AgentSpec(
    role="quant",
    name="tel99-analyst",
    description=(
        "TEL99 Quant Analyst. Use for a read-only audit of market data freshness, "
        "signals, backtests and temporal leakage."
    ),
    system_prompt=(
        "Audit Kraken market data freshness, signals, backtests and temporal leakage; "
        "cite evidence. Never confuse an early alert with a confirmed buy. Distinguish "
        "facts from hypotheses and report uncertainties, permissions and costs."
    ),
)
_VERIFIER = AgentSpec(
    role="quality",
    name="tel99-verifier",
    description=(
        "TEL99 Independent Verifier. Use to independently reproduce evidence and "
        "challenge another agent's claims."
    ),
    system_prompt=(
        "Independently reproduce evidence and challenge claims; report proven, "
        "unproven or uncertain for each item. Do not accept a claim without "
        "reproducing it yourself with a command and its raw output."
    ),
)

ACTIVE_AGENTS: tuple[AgentSpec, ...] = (_DEV, _ANALYST, _VERIFIER)

# --- Reserved roles: prepared, never auto-discovered ----------------------
# These mirror the remaining specializations of docs/agents/ROLE_CATALOG.md.
# They live in .agents/agents/reserve/ (a subdirectory), which the SDK loader
# ignores, so they cannot be triggered until an operator moves them up.
RESERVED_ROLES: tuple[dict, ...] = (
    {"role": "coordination", "title": "Coordinator",
     "prompt": "Split a mission into independent tasks, assign each to one owner, "
               "and never declare work finished without verifiable results."},
    {"role": "cloud", "title": "Cloud & Reliability",
     "prompt": "Audit GitHub Actions, branches, schedules and publication. Require "
               "evidence of runs independent of the PC before claiming autonomy."},
    {"role": "security", "title": "Security",
     "prompt": "Review permissions, secrets and read-only guarantees. Report any "
               "capability that exceeds the declared scope."},
    {"role": "mobile", "title": "Mobile Experience",
     "prompt": "Review Android usability without redesigning the terminal."},
    {"role": "documentation", "title": "Documentation",
     "prompt": "Maintain handovers, decisions and traceability. Keep archives intact."},
    {"role": "evaluation", "title": "Evaluation",
     "prompt": "Measure prospective results and detect temporal leakage or look-ahead bias."},
    {"role": "market_data", "title": "Market Data",
     "prompt": "Check Kraken data freshness and candle quality. A stale snapshot must "
               "block any actionable decision."},
    {"role": "monitoring", "title": "Monitoring",
     "prompt": "Review logs, alerts and incidents. Do not infer delivery from display."},
    {"role": "release", "title": "Release",
     "prompt": "Compare before/after and control publication. Never merge by default."},
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def reserved_agents() -> tuple[AgentSpec, ...]:
    specs = []
    for item in RESERVED_ROLES:
        specs.append(
            AgentSpec(
                role=item["role"],
                name=f"tel99-{_slug(item['role'])}",
                description=(
                    f"TEL99 {item['title']}. Reserved specialization of the TEL99 "
                    "role catalogue; not active."
                ),
                system_prompt=item["prompt"],
                active=False,
            )
        )
    return tuple(specs)


def unique_names(suffix: str | None = None) -> dict[str, str]:
    """Return collision-free agent names for one run.

    The SDK keeps a process-global, first-wins agent registry, so reusing a
    name across runs silently applies the FIRST definition. A per-run suffix
    makes every registration distinct.
    """
    suffix = suffix or time.strftime("%H%M%S")
    return {spec.role: f"{spec.name}-{suffix}" for spec in ACTIVE_AGENTS}


def guard_command() -> str:
    """Shell command that runs the PreToolUse guard.

    Relative to the repository root, which is the working directory hooks run
    in (HookExecutor cwd = conversation workspace root).
    """
    return "python3 scripts/agents/guard/guard.py"


def hook_config() -> dict:
    """PreToolUse hook config (applied to the parent AND to each sub-agent)."""
    return {
        "pre_tool_use": [
            {
                "matcher": "terminal",
                "hooks": [
                    {
                        "type": "command",
                        "command": guard_command(),
                        "timeout": 20,
                    }
                ],
            }
        ]
    }


def validate() -> None:
    """Fail loudly on an unsafe or inconsistent configuration."""
    if DEFAULT_MAX_BUDGET_USD <= 0:
        raise ValueError("TEL99_MAX_BUDGET_USD must be positive")
    if DEFAULT_MAX_BUDGET_USD > MAX_BUDGET_CEILING_USD:
        raise ValueError(
            f"TEL99_MAX_BUDGET_USD ({DEFAULT_MAX_BUDGET_USD}) exceeds ceiling "
            f"({MAX_BUDGET_CEILING_USD})"
        )
    for spec in ACTIVE_AGENTS:
        if spec.tools != ("terminal",):
            raise ValueError(f"{spec.name} must be terminal-only, got {spec.tools}")
        if spec.permission_mode not in ("always_confirm", "never_confirm", "confirm_risky"):
            raise ValueError(f"{spec.name} has invalid permission_mode")
    names = {spec.name for spec in ACTIVE_AGENTS}
    if len(names) != len(ACTIVE_AGENTS):
        raise ValueError("duplicate base agent names")
