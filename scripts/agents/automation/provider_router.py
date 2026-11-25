"""Unified multi-provider model router for TEL99 (local free + verified subscriptions).

Strictly separates zero-cost local inference, verified subscription-only CLIs,
opt-in subscription CLIs, and unverified/billed interfaces. Never allows
silent paid API usage.
"""
from __future__ import annotations

import argparse
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import local_model_routing
from scripts.agents.automation.antigravity_sdk_backend import (
    AntigravitySDKProvider,
    probe_sdk_backend,
)
from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.intelligence import catalog
from scripts.agents.native.provider import ProviderError

BILLING_LOCAL_FREE = "LOCAL_FREE"
BILLING_SUBSCRIPTION_VERIFIED = "SUBSCRIPTION_VERIFIED"
BILLING_SUBSCRIPTION_OPT_IN = "SUBSCRIPTION_OPT_IN"
BILLING_FREE_GATEWAY = "FREE_GATEWAY"
BILLING_UNVERIFIED = "BILLING_UNVERIFIED"
BILLING_NOT_INSTALLED = "NOT_INSTALLED"

PAID_ENV_PREFIXES = ("OPENAI_", "ANTHROPIC_", "GOOGLE_", "GEMINI_", "CODEX_", "AZURE_", "GH_", "GITHUB_")
PAID_ENV_SUFFIXES = ("_TOKEN", "_KEY", "_SECRET", "_PASSWORD")

SUBSCRIPTION_MODELS = {
    "agy": (
        {"id": "agy/gemini-4-hydrogen-medium", "model": "gemini-4-hydrogen-medium",
         "role_tier": "executor", "effort_tier": "medium",
         "quality_prior": 0.85, "latency_tier": "fast", "supports_tools": True, "context_tokens": 128_000},
        {"id": "agy/gemini-4-neon-medium", "model": "gemini-4-neon-medium",
         "role_tier": "orchestrator", "effort_tier": "medium",
         "quality_prior": 0.85, "latency_tier": "medium", "supports_tools": True, "context_tokens": 128_000},
        {"id": "agy/gemini-4-neon-high", "model": "gemini-4-neon-high",
         "role_tier": "hard_only", "effort_tier": "high",
         "quality_prior": 0.92, "latency_tier": "medium", "supports_tools": True, "context_tokens": 128_000},
    ),
}


def scrubbed_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of the environment stripped of API keys, tokens, and secrets."""
    source = os.environ if base_env is None else base_env
    return {
        k: v for k, v in source.items()
        if not k.upper().startswith(PAID_ENV_PREFIXES)
        and not k.upper().endswith(PAID_ENV_SUFFIXES)
    }


def _probe_ollama() -> dict:
    avail_mib = local_model_routing.available_memory_mib()
    conn = HTTPConnection("127.0.0.1", 11434, timeout=2.5)
    try:
        conn.request("GET", "/api/tags")
        resp = conn.getresponse()
        if resp.status != 200:
            return {
                "provider": "ollama", "installed": True, "available": False,
                "billing_class": BILLING_LOCAL_FREE, "quota_status": "UNAVAILABLE",
                "models": [], "reason": f"HTTP {resp.status}",
            }
        payload = json.loads(resp.read(32_768))
        rows = payload.get("models") if isinstance(payload, dict) else []
        installed_names = {
            row["name"] for row in (rows or [])
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        }
        models = []
        for spec in catalog.MODEL_CATALOG:
            if spec.provider != "ollama" or not spec.is_free or not spec.is_local:
                continue
            for served in spec.served_ids:
                if served in installed_names:
                    models.append({
                        "id": spec.id,
                        "served_model": served,
                        "provider": "ollama",
                        "quality_prior": spec.quality_prior,
                        "latency_tier": spec.latency_tier,
                        "supports_tools": spec.supports_tools,
                        "context_tokens": spec.context_tokens,
                        "memory_mib": spec.memory_mib,
                        "confidential_ok": True,
                    })
        mem_ok = avail_mib is not None and avail_mib >= local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB
        return {
            "provider": "ollama",
            "installed": True,
            "available": bool(models) and mem_ok,
            "billing_class": BILLING_LOCAL_FREE,
            "quota_status": "READY" if (models and mem_ok) else "LOW_MEMORY_OR_NO_MODELS",
            "available_memory_mib": avail_mib,
            "models": models,
            "reason": None if (models and mem_ok) else "no installed catalog models or low free memory",
        }
    except (OSError, ValueError) as exc:
        return {
            "provider": "ollama", "installed": shutil.which("ollama") is not None,
            "available": False, "billing_class": BILLING_LOCAL_FREE,
            "quota_status": "UNAVAILABLE", "models": [], "reason": str(exc),
        }
    finally:
        conn.close()


def _probe_codex() -> dict:
    cli = shutil.which("codex")
    if not cli:
        return {
            "provider": "codex", "installed": False, "available": False,
            "billing_class": BILLING_NOT_INSTALLED, "quota_status": "NOT_INSTALLED",
            "models": [], "reason": "codex CLI not found",
        }
    try:
        from scripts.agents.automation import codex_model_router as cmr
        snap = cmr.read_snapshot(cli, ROOT, scrubbed_env(), include_catalog=True)
        limits = (snap.limits or {}).get("rateLimits") or {}
        credits = limits.get("credits") or {}
        primary = (limits.get("primary") or {}).get("usedPercent")
        secondary = (limits.get("secondary") or {}).get("usedPercent")
        rate_type = limits.get("rateLimitReachedType")
        plan = ((snap.account or {}).get("account") or {}).get("planType")
        if credits.get("hasCredits") is not False or credits.get("unlimited") is not False:
            return {
                "provider": "codex", "installed": True, "available": False,
                "billing_class": BILLING_UNVERIFIED, "quota_status": "CREDITS_PRESENT",
                "models": [], "plan": plan, "reason": "credits flag not confirmed false",
            }
        quota_exhausted = (
            rate_type is not None
            or (type(primary) in (int, float) and primary >= 90)
            or (type(secondary) in (int, float) and secondary >= 90)
        )
        models = []
        for row in snap.models:
            if row.get("hidden") is not False:
                continue
            slug = row.get("model")
            if isinstance(slug, str) and slug:
                models.append({
                    "id": f"codex/{slug}",
                    "served_model": slug,
                    "provider": "codex",
                    "quality_prior": 0.85,
                    "latency_tier": "medium",
                    "supports_tools": True,
                    "context_tokens": 128_000,
                    "confidential_ok": False,
                })
        return {
            "provider": "codex",
            "installed": True,
            "available": not quota_exhausted and bool(models),
            "billing_class": BILLING_SUBSCRIPTION_VERIFIED,
            "quota_status": "WAITING_QUOTA" if quota_exhausted else "READY",
            "plan": plan,
            "primary_used_percent": primary,
            "secondary_used_percent": secondary,
            "models": models,
            "reason": "quota reserve reached" if quota_exhausted else None,
        }
    except Exception as exc:
        return {
            "provider": "codex", "installed": True, "available": False,
            "billing_class": BILLING_SUBSCRIPTION_VERIFIED,
            "quota_status": getattr(exc, "status", "UNAVAILABLE"),
            "models": [], "reason": str(exc),
        }


def _resolve_agy_cli() -> str | None:
    """Resolve the Antigravity CLI binary from PATH or user install location."""
    found = shutil.which("agy")
    if found:
        return found
    home = Path.home()
    for rel in (Path(".gemini") / "bin" / "agy.exe", Path(".gemini") / "bin" / "agy"):
        candidate = home / rel
        if candidate.is_file():
            return str(candidate)
    return None


def _probe_agy() -> dict:
    cli = _resolve_agy_cli()
    if not cli:
        return {
            "provider": "agy", "installed": False, "available": False,
            "billing_class": BILLING_NOT_INSTALLED, "quota_status": "NOT_INSTALLED",
            "models": [], "reason": "agy CLI not found",
        }
    try:
        ver = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=5,
            env=scrubbed_env(), check=False,
        )
        if ver.returncode != 0:
            raise OSError("agy --version failed")
        listed = subprocess.run(
            [cli, "models"], capture_output=True, text=True, timeout=12,
            env=scrubbed_env(), check=False,
        )
        available_ids = set()
        if listed.returncode == 0:
            for line in listed.stdout.splitlines():
                token = line.split("\t", 1)[0].strip()
                if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,80}", token):
                    available_ids.add(token)
        models = []
        for item in SUBSCRIPTION_MODELS["agy"]:
            if not available_ids or item["model"] in available_ids:
                models.append({
                    "id": item["id"],
                    "served_model": item["model"],
                    "provider": "agy",
                    "role_tier": item.get("role_tier"),
                    "effort_tier": item.get("effort_tier", "medium"),
                    "quality_prior": item["quality_prior"],
                    "latency_tier": item["latency_tier"],
                    "supports_tools": item["supports_tools"],
                    "context_tokens": item["context_tokens"],
                    "confidential_ok": False,
                })
        return {
            "provider": "agy",
            "installed": True,
            "available": bool(models),
            "billing_class": BILLING_SUBSCRIPTION_OPT_IN,
            "quota_status": "OPT_IN_NO_RPC_QUOTA",
            "version": ver.stdout.strip().splitlines()[0] if ver.stdout.strip() else "unknown",
            "models": models,
            "reason": None,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "provider": "agy", "installed": True, "available": False,
            "billing_class": BILLING_SUBSCRIPTION_OPT_IN,
            "quota_status": "UNAVAILABLE", "models": [], "reason": str(exc),
        }


def _probe_cmd_cli(name: str, billing_class: str, reason: str) -> dict:
    cli = shutil.which(name)
    if not cli:
        return {
            "provider": name, "installed": False, "available": False,
            "billing_class": BILLING_NOT_INSTALLED, "quota_status": "NOT_INSTALLED",
            "models": [], "reason": f"{name} CLI not found",
        }
    try:
        argv = ["cmd", "/c", name, "--version"] if os.name == "nt" and cli.lower().endswith((".ps1", ".cmd")) else [cli, "--version"]
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=6,
            env=scrubbed_env(), check=False,
        )
        version = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else None
        return {
            "provider": name,
            "installed": True,
            "available": False,
            "billing_class": billing_class,
            "quota_status": "EXCLUDED_BY_POLICY",
            "version": version,
            "models": [],
            "reason": reason,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "provider": name, "installed": True, "available": False,
            "billing_class": billing_class, "quota_status": "UNAVAILABLE",
            "models": [], "reason": str(exc),
        }


def probe_all_providers(*, probes: dict | None = None) -> dict:
    """Inspect all configured model/CLI providers in read-only mode."""
    p = probes or {}
    ollama = p["ollama"]() if "ollama" in p else _probe_ollama()
    codex = p["codex"]() if "codex" in p else _probe_codex()
    agy = p["agy"]() if "agy" in p else _probe_agy()
    claude = p["claude"]() if "claude" in p else _probe_cmd_cli(
        "claude", BILLING_UNVERIFIED, "no RPC subscription-only guarantee; excluded to prevent API billing"
    )
    gemini = p["gemini"]() if "gemini" in p else _probe_cmd_cli(
        "gemini", BILLING_NOT_INSTALLED, "gemini CLI not installed"
    )
    kilo = p["kilo"]() if "kilo" in p else _probe_cmd_cli(
        "kilo", BILLING_FREE_GATEWAY, "synthetic text gateway only; excluded from local code routing"
    )
    return {
        "schema_version": 1,
        "billing_policy": "no-extra-spend",
        "sdk_backend": probe_sdk_backend(),
        "providers": {
            "ollama": ollama,
            "codex": codex,
            "agy": agy,
            "claude": claude,
            "gemini": gemini,
            "kilo": kilo,
        },
    }


def _quality_score(model: dict, measured_quality: dict[str, float] | None) -> float:
    mid = model.get("id", "")
    served = model.get("served_model", "")
    if isinstance(measured_quality, dict):
        for key in (mid, served):
            val = measured_quality.get(key)
            if isinstance(val, dict):
                val = val.get("success_rate")
            if type(val) in (int, float) and 0.0 <= val <= 1.0:
                return float(val)
    return float(model.get("quality_prior", 0.5))


def select_executor(task_kind: str = "code", *, difficulty: str = "medium",
                    confidential: bool = True, allow_subscription_cli: bool = False,
                    measured_quality: dict | None = None,
                    preferred_provider: str | None = None,
                    exclude: tuple[str, ...] | list[str] = (),
                    inventory: dict | None = None) -> dict:
    """Select an eligible model executor while strictly enforcing no-extra-spend rules."""
    inv = inventory if inventory is not None else probe_all_providers()
    providers = inv.get("providers", {})
    excluded = set(exclude)
    candidates: list[dict] = []
    rejected: list[dict] = []

    min_quality = {"easy": 0.30, "medium": 0.50, "hard": 0.65}.get(difficulty, 0.50)

    for pname, pinfo in providers.items():
        bclass = pinfo.get("billing_class")
        if not pinfo.get("available"):
            rejected.append({"provider": pname, "reason": pinfo.get("reason") or pinfo.get("quota_status")})
            continue
        if bclass == BILLING_UNVERIFIED or bclass == BILLING_NOT_INSTALLED:
            rejected.append({"provider": pname, "reason": f"billing_class={bclass}"})
            continue
        if bclass == BILLING_FREE_GATEWAY and task_kind == "code":
            rejected.append({"provider": pname, "reason": "synthetic-only gateway cannot execute code"})
            continue
        if bclass == BILLING_SUBSCRIPTION_OPT_IN and not allow_subscription_cli:
            rejected.append({"provider": pname, "reason": "subscription CLI requires allow_subscription_cli=True"})
            continue
        if confidential and bclass != BILLING_LOCAL_FREE:
            rejected.append({"provider": pname, "reason": "confidential task requires LOCAL_FREE provider"})
            continue

        for model in pinfo.get("models", []):
            mid = model.get("id")
            served = model.get("served_model")
            if mid in excluded or served in excluded:
                rejected.append({"provider": pname, "id": mid, "reason": "excluded"})
                continue
            if model.get("effort_tier") == "high" and difficulty != "hard":
                rejected.append({"provider": pname, "id": mid, "reason": "high-effort model reserved for difficulty=hard"})
                continue
            q = _quality_score(model, measured_quality)
            if q < min_quality:
                rejected.append({"provider": pname, "id": mid, "reason": f"quality {q:.2f} < {min_quality:.2f}"})
                continue
            latency_bonus = {"fast": 0.15, "medium": 0.08, "slow": 0.0}.get(model.get("latency_tier"), 0.0)
            local_bonus = 0.20 if bclass == BILLING_LOCAL_FREE else 0.0
            pref_bonus = 0.25 if (preferred_provider and pname == preferred_provider) else 0.0
            role_tier = model.get("role_tier")
            role_bonus = 0.0
            if task_kind in ("orchestration", "planning") and role_tier == "orchestrator":
                role_bonus = 0.18
            elif task_kind in ("code", "execution") and role_tier == "executor":
                role_bonus = 0.18
            score = round(3.0 * q + local_bonus + latency_bonus + pref_bonus + role_bonus, 4)
            candidates.append({
                **model,
                "billing_class": bclass,
                "effective_quality": q,
                "score": score,
            })

    candidates.sort(key=lambda row: (-row["score"], row["id"]))
    chosen = candidates[0] if candidates else None
    fallbacks = candidates[1:] if chosen else []
    return {
        "ok": chosen is not None,
        "billing_policy": "no-extra-spend",
        "task_kind": task_kind,
        "difficulty": difficulty,
        "confidential": confidential,
        "chosen": chosen,
        "fallbacks": fallbacks,
        "rejected": rejected,
    }


class OllamaAdapter:
    """Adapter for local Ollama loopback inference."""

    def __init__(self, model: str, *, timeout: int = 80, max_tokens: int = 768):
        self.model = model
        self._provider = OllamaNativeProvider(model=model, timeout=timeout, max_tokens=max_tokens)

    def complete(self, *, system: str, prompt: str) -> str:
        return self._provider.complete(system=system, prompt=prompt)


class AntigravitySDKAdapter:
    """Opt-in adapter using Google Antigravity SDK over local Ollama with safe native fallback."""

    def __init__(self, model: str, *, timeout: int = 120, max_tokens: int = 768,
                 fallback_to_ollama_native: bool = True):
        self.model = model
        self._provider = AntigravitySDKProvider(
            model=model,
            timeout=timeout,
            max_tokens=max_tokens,
            fallback_to_ollama_native=fallback_to_ollama_native,
        )

    @property
    def last_metadata(self) -> dict:
        return dict(self._provider.last_metadata)

    def complete(self, *, system: str, prompt: str) -> str:
        return self._provider.complete(system=system, prompt=prompt)


class AgyPrintAdapter:
    """Opt-in adapter for Antigravity CLI subscription print mode (no API keys)."""

    def __init__(self, model: str, *, timeout: int = 90):
        self.model = model
        self.timeout = timeout
        self.cli = _resolve_agy_cli()
        self.last_metadata: dict = {}
        if not self.cli:
            raise ProviderError("agy CLI unavailable")

    def complete(self, *, system: str, prompt: str) -> str:
        self.last_metadata = {}
        combined = f"{system.strip()}\n\n{prompt.strip()}"
        proc = subprocess.run(
            [
                self.cli, "--model", self.model,
                "--output-format", "json", "--disable-slash-commands",
                "--print", combined,
            ],
            capture_output=True, text=True, timeout=self.timeout,
            env=scrubbed_env(), check=False,
        )
        if proc.returncode != 0:
            raise ProviderError(f"agy CLI failed (exit {proc.returncode})")
        raw = proc.stdout.strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                self.last_metadata = {
                    k: data.get(k) for k in ("conversation_id", "status", "duration_seconds", "usage")
                    if k in data
                }
                for key in ("result", "response", "text", "content"):
                    if isinstance(data.get(key), str):
                        return data[key]
        except ValueError:
            pass
        return raw


# Evidence-backed local specialty priors (updated from TEL99 57-min endurance & comparative benchmarks).
LOCAL_SPECIALTY_BONUS: dict[str, dict[str, float]] = {
    "local/ollama-gemma4-e4b": {
        "python": 0.14, "javascript": 0.14, "analysis": 0.16, "planning": 0.16,
        "repair": 0.14, "documentation": 0.18, "reasoning": 0.12, "tools": 0.04,
    },
    "local/ollama-qwen3.5-9b": {
        "python": 0.16, "javascript": 0.12, "analysis": 0.10, "planning": 0.10,
        "repair": 0.16, "documentation": 0.08, "reasoning": 0.18, "tools": 0.06,
    },
    "local/ollama-qwen2.5-coder-7b": {
        "python": 0.02, "javascript": 0.04, "analysis": 0.0, "planning": 0.0,
        "repair": 0.0, "documentation": 0.0, "reasoning": 0.0, "tools": 0.14,
    },
}


def select_executor_for_specialty(
    specialty: str,
    *,
    difficulty: str = "medium",
    confidential: bool = True,
    allow_subscription_cli: bool = False,
    measured_quality: dict | None = None,
    exclude: tuple[str, ...] | list[str] = (),
    inventory: dict | None = None,
) -> dict:
    """Select best eligible model for a specific specialty while strictly enforcing no-extra-spend."""
    task_kind = "orchestration" if specialty in ("planning", "coordination", "architecture") else "code"
    base = select_executor(
        task_kind=task_kind,
        difficulty=difficulty,
        confidential=confidential,
        allow_subscription_cli=allow_subscription_cli,
        measured_quality=measured_quality,
        exclude=exclude,
        inventory=inventory,
    )
    if not base.get("ok"):
        return {**base, "specialty": specialty}
    pool = [base["chosen"], *base["fallbacks"]]
    ranked = []
    for cand in pool:
        bonus = LOCAL_SPECIALTY_BONUS.get(cand.get("id", ""), {}).get(specialty, 0.0)
        ranked.append({**cand, "specialty_bonus": bonus, "score": round(cand["score"] + bonus, 4)})
    ranked.sort(key=lambda row: (-row["score"], row["id"]))
    return {
        **base,
        "specialty": specialty,
        "chosen": ranked[0],
        "fallbacks": ranked[1:],
    }


def select_fallback_model(
    failed_models: tuple[str, ...] | list[str],
    *,
    specialty: str = "python",
    difficulty: str = "medium",
    confidential: bool = True,
    measured_quality: dict | None = None,
    inventory: dict | None = None,
) -> dict:
    """Switch to another authorized LOCAL_FREE model when the primary model fails (never escalates to paid APIs)."""
    return select_executor_for_specialty(
        specialty,
        difficulty=difficulty,
        confidential=confidential,
        allow_subscription_cli=False,
        measured_quality=measured_quality,
        exclude=tuple(failed_models),
        inventory=inventory,
    )


def build_adapter(selection: dict, *, allow_subscription_cli: bool = False,
                  use_sdk_backend: bool = False):
    """Instantiate an authorized adapter from a router selection."""
    if not isinstance(selection, dict) or not selection.get("provider"):
        raise ValueError("valid provider selection required")
    provider = selection["provider"]
    model = selection.get("served_model") or selection.get("model")
    if provider == "ollama":
        if use_sdk_backend:
            return AntigravitySDKAdapter(model=model)
        return OllamaAdapter(model=model)
    if provider == "agy":
        if not allow_subscription_cli:
            raise PermissionError("subscription CLI adapter requires explicit allow_subscription_cli=True")
        return AgyPrintAdapter(model=model)
    raise PermissionError(f"provider {provider!r} has no authorized direct code adapter")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--task-kind", default="code")
    parser.add_argument("--difficulty", default="medium", choices=("easy", "medium", "hard"))
    parser.add_argument("--non-confidential", action="store_true")
    parser.add_argument("--allow-subscription-cli", action="store_true")
    args = parser.parse_args(argv)

    inventory = probe_all_providers()
    if args.select:
        decision = select_executor(
            task_kind=args.task_kind,
            difficulty=args.difficulty,
            confidential=not args.non_confidential,
            allow_subscription_cli=args.allow_subscription_cli,
            inventory=inventory,
        )
        print(json.dumps(decision, indent=2, ensure_ascii=False))
        return 0 if decision["ok"] else 2
    print(json.dumps(inventory, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
