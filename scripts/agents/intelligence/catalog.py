#!/usr/bin/env python3
"""Declared model catalogue for the TEL99 router.

Every field carries its own evidence. This matters because issue #67 forbids
inventing model availability: a model that was never probed is marked
``verified = False`` and the router treats an unverified *availability* as
unavailable for a real run (fail-closed), while still allowing it in a dry run.

Nothing here is a price list of a paid service: the project is under a
no-spend rule, so ``cost_tier`` is either ``free`` or ``unknown``; the router
refuses anything that is not explicitly free.

The quality numbers are *priors*, not measured results. ``evidence`` says where
each number comes from, and ``verified`` says whether it was measured in this
repository. The controlled-improvement loop (``improvement.py``) replaces the
prior with a measured success rate once real outcomes exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A model is only usable when it is free AND its availability was probed.
COST_FREE = "free"
COST_UNKNOWN = "unknown"

LOCAL = "local"
CLOUD = "cloud"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    location: str            # LOCAL or CLOUD
    cost_tier: str           # COST_FREE or COST_UNKNOWN
    supports_tools: bool
    context_tokens: int
    latency_tier: str        # "fast" | "medium" | "slow"
    quality_prior: float     # 0..1, a PRIOR, not a measurement
    evidence: str            # where the numbers come from
    verified: bool = False   # was availability actually probed in this repo?
    tags: tuple[str, ...] = field(default_factory=tuple)
    endpoint: str = ""

    @property
    def is_free(self) -> bool:
        return self.cost_tier == COST_FREE

    @property
    def is_local(self) -> bool:
        return self.location == LOCAL


# --- Catalogue -------------------------------------------------------------
# Sources (all read from this repository, no invented availability):
#  * ``openhands/deepseek-v4.1-flash`` — ``scripts/agents/team_config.py``
#    DEFAULT_MODEL, documented as "free model currently available in this
#    environment". Availability NOT probed here => verified = False.
#  * LM Studio / Ollama endpoints — ``docs/agents/LOCAL_FREE_MODELS.md``,
#    documented as "not tested in this environment" => verified = False.
#  * ``gpt-5.6`` — observed as the agent-server's configured model in
#    ``/api/settings`` on 2026-11-15. Cost is unknown, so it is excluded from a
#    real run (the project may not spend).
MODEL_CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(
        id="openhands/deepseek-v4.1-flash",
        provider="openhands",
        location=CLOUD,
        cost_tier=COST_FREE,
        supports_tools=True,
        context_tokens=128_000,
        latency_tier="fast",
        quality_prior=0.60,
        evidence=(
            "team_config.py DEFAULT_MODEL; comment states it is the free model "
            "available in this environment. No benchmark run in this repo."
        ),
        verified=False,
        tags=("free", "cloud", "tools", "default"),
    ),
    ModelSpec(
        id="local/qwen2.5-coder-7b",
        provider="lmstudio",
        location=LOCAL,
        cost_tier=COST_FREE,
        supports_tools=True,
        context_tokens=32_000,
        latency_tier="fast",
        quality_prior=0.40,
        evidence=(
            "docs/agents/LOCAL_FREE_MODELS.md (LM Studio, Qwen2.5-Coder 7B Q4). "
            "Documented as a lead, explicitly not tested in this environment."
        ),
        verified=False,
        tags=("free", "local", "tools", "code"),
        endpoint="http://localhost:1234/v1",
    ),
    ModelSpec(
        id="local/ollama-qwen2.5-coder-7b",
        provider="ollama",
        location=LOCAL,
        cost_tier=COST_FREE,
        supports_tools=True,
        context_tokens=32_000,
        latency_tier="fast",
        quality_prior=0.40,
        evidence=(
            "docs/agents/LOCAL_FREE_MODELS.md (Ollama, qwen2.5-coder:7b). "
            "Documented as a lead, explicitly not tested in this environment."
        ),
        verified=False,
        tags=("free", "local", "tools", "code"),
        endpoint="http://localhost:11434/v1",
    ),
    ModelSpec(
        id="gpt-5.6",
        provider="openhands-runtime",
        location=CLOUD,
        cost_tier=COST_UNKNOWN,
        supports_tools=True,
        context_tokens=128_000,
        latency_tier="medium",
        quality_prior=0.75,
        evidence=(
            "Observed as the agent-server's configured model in /api/settings "
            "on 2026-11-15. Cost tier unknown => excluded from a real run."
        ),
        verified=False,
        tags=("cloud", "tools", "runtime-default"),
    ),
)


def by_id(model_id: str) -> ModelSpec | None:
    for spec in MODEL_CATALOG:
        if spec.id == model_id:
            return spec
    return None


def free_models() -> list[ModelSpec]:
    return [m for m in MODEL_CATALOG if m.is_free]
