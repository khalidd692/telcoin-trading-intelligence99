"""Unified multi-provider model router for TEL99 (local free + verified subscriptions).

Strictly separates zero-cost local inference, verified subscription-only CLIs,
opt-in subscription CLIs, and unverified/billed interfaces. Never allows
silent paid API usage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import ide_coordination, local_model_routing
from scripts.agents.automation.antigravity_sdk_backend import (
    AntigravitySDKProvider,
    probe_sdk_backend,
)
from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.intelligence import catalog
from scripts.agents.native.provider import ProviderError

BILLING_LOCAL_FREE = "LOCAL_FREE"
BILLING_FREE_CLOUD_VERIFIED = "FREE_CLOUD_VERIFIED"
BILLING_SUBSCRIPTION_VERIFIED = "SUBSCRIPTION_VERIFIED"
BILLING_SUBSCRIPTION_OPT_IN = "SUBSCRIPTION_OPT_IN"
BILLING_FREE_GATEWAY = "FREE_GATEWAY"
BILLING_UNVERIFIED = "BILLING_UNVERIFIED"
BILLING_NOT_INSTALLED = "NOT_INSTALLED"

PAID_ENV_PREFIXES = ("OPENAI_", "ANTHROPIC_", "GOOGLE_", "GEMINI_", "CODEX_", "AZURE_", "GH_", "GITHUB_", "GROQ_", "OPENROUTER_")
PAID_ENV_SUFFIXES = ("_TOKEN", "_KEY", "_SECRET", "_PASSWORD")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Strict zero-spend allowlists (models must ALSO be confirmed present in live /models catalog).
GROQ_FREE_ALLOWLIST: dict[str, dict] = {
    "openai/gpt-oss-120b": {
        "quality_prior": 0.94, "latency_tier": "fast", "role_tier": "hard_only",
        "effort_tier": "high", "context_tokens": 131_072, "supports_tools": True,
    },
    "qwen/qwen3.8-27b": {
        "quality_prior": 0.91, "latency_tier": "fast", "role_tier": "executor",
        "effort_tier": "medium", "context_tokens": 131_072, "supports_tools": True,
    },
    "openai/gpt-oss-20b": {
        "quality_prior": 0.87, "latency_tier": "fast", "role_tier": "executor",
        "effort_tier": "medium", "context_tokens": 131_072, "supports_tools": True,
    },
    "qwen/qwen3-32b": {
        "quality_prior": 0.89, "latency_tier": "fast", "role_tier": "executor",
        "effort_tier": "medium", "context_tokens": 131_072, "supports_tools": True,
    },
    "llama-3.3-70b-versatile": {
        "quality_prior": 0.88, "latency_tier": "fast", "role_tier": "executor",
        "effort_tier": "medium", "context_tokens": 131_072, "supports_tools": True,
    },
}

DEFAULT_CLOUD_DAILY_BUDGETS: dict[str, dict[str, int]] = {
    "groq": {"max_requests_per_day": 950, "max_tokens_per_day": 450_000},
    "openrouter": {"max_requests_per_day": 45, "max_tokens_per_day": 45_000},
}

_CLOUD_SECRET_PATTERNS = (
    re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9\-_]{16,}|gsk_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z\-_]{20,})"),
    re.compile(r"(?i)(api[_-]?key|secret|password|private[_-]?key|seed[_ ]?phrase|mnemonic|wallet[_-]?key)\s*[:=]\s*['\"]?[^\s'\",;]{6,}"),
)

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


def load_local_provider_key(env_name: str, *, config_paths: tuple[Path, ...] | None = None) -> str | None:
    """Read an API key strictly from local env/registry or user-private file outside any git repo."""
    direct = os.environ.get(env_name, "").strip()
    if direct:
        return direct
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg_key:
                val, _ = winreg.QueryValueEx(reg_key, env_name)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        except OSError:
            pass
    paths = config_paths or (
        Path.home() / ".tel99" / "providers.env",
        Path.home() / ".tel99" / ".env",
    )
    for path in paths:
        if not path.is_file():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == env_name:
                    val = v.strip().strip("\"'")
                    if val:
                        return val
        except OSError:
            continue
    return None


def validate_cloud_egress_safe(system: str, prompt: str, *, confidential: bool) -> tuple[bool, str | None]:
    """Hard gate preventing confidential data or secret tokens from ever reaching a cloud endpoint."""
    if confidential:
        return False, "confidential task is forbidden on cloud providers"
    blob = f"{system or ''}\n{prompt or ''}"
    for pat in _CLOUD_SECRET_PATTERNS:
        if pat.search(blob):
            return False, "potential secret or sensitive credential detected in outbound cloud prompt"
    return True, None


class CloudBudgetLedger:
    """Durable daily request/token budget and 429 cooldown tracker for free cloud providers."""

    def __init__(self, path: Path | str | None = None, *, budgets: dict[str, dict[str, int]] | None = None):
        if path is None:
            path = ide_coordination.default_coordination_state_root() / "cloud_free_budgets.json"
        self.path = Path(path)
        self.budgets = budgets or DEFAULT_CLOUD_DAILY_BUDGETS

    @staticmethod
    def _today_utc() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"schema_version": 1, "providers": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("providers"), dict):
                return data
        except (OSError, ValueError):
            pass
        return {"schema_version": 1, "providers": {}}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def _provider_state(self, data: dict, provider: str) -> dict:
        today = self._today_utc()
        st = data["providers"].get(provider)
        if not isinstance(st, dict) or st.get("date_utc") != today:
            st = {
                "date_utc": today,
                "requests_today": 0,
                "tokens_today": 0,
                "cooldown_until_ts": 0.0,
                "rate_limit_hits": 0,
                "last_headers": {},
            }
            data["providers"][provider] = st
        return st

    def status(self, provider: str, *, now: float | None = None) -> dict:
        ts = time.time() if now is None else float(now)
        data = self._load()
        st = self._provider_state(data, provider)
        lim = self.budgets.get(provider, {"max_requests_per_day": 50, "max_tokens_per_day": 50_000})
        cooldown_rem = round(max(0.0, float(st.get("cooldown_until_ts") or 0.0) - ts), 1)
        return {
            **st,
            "max_requests_per_day": lim["max_requests_per_day"],
            "max_tokens_per_day": lim["max_tokens_per_day"],
            "remaining_requests_budget": max(0, lim["max_requests_per_day"] - int(st["requests_today"])),
            "remaining_tokens_budget": max(0, lim["max_tokens_per_day"] - int(st["tokens_today"])),
            "cooldown_remaining_s": cooldown_rem,
        }

    def can_call(self, provider: str, *, estimated_tokens: int = 1500, now: float | None = None) -> tuple[bool, str]:
        st = self.status(provider, now=now)
        if st["cooldown_remaining_s"] > 0:
            return False, f"provider in 429 cooldown for {st['cooldown_remaining_s']}s"
        if st["remaining_requests_budget"] <= 0:
            return False, "daily free request budget exhausted"
        if st["remaining_tokens_budget"] < max(1, estimated_tokens):
            return False, "daily free token budget exhausted"
        return True, "ok"

    def record_usage(self, provider: str, *, prompt_tokens: int = 0, completion_tokens: int = 0, headers: dict | None = None) -> dict:
        data = self._load()
        st = self._provider_state(data, provider)
        st["requests_today"] = int(st.get("requests_today") or 0) + 1
        st["tokens_today"] = int(st.get("tokens_today") or 0) + max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
        if isinstance(headers, dict):
            tracked = {
                k.lower(): str(v)[:80]
                for k, v in headers.items()
                if k.lower().startswith("x-ratelimit-") or k.lower() == "retry-after"
            }
            if tracked:
                st["last_headers"] = tracked
        self._save(data)
        return st

    def record_rate_limit(self, provider: str, *, retry_after_s: float = 60.0, now: float | None = None) -> dict:
        ts = time.time() if now is None else float(now)
        data = self._load()
        st = self._provider_state(data, provider)
        st["rate_limit_hits"] = int(st.get("rate_limit_hits") or 0) + 1
        st["cooldown_until_ts"] = max(float(st.get("cooldown_until_ts") or 0.0), ts + max(5.0, float(retry_after_s)))
        self._save(data)
        return st


def _parse_reset_seconds(header_val: str | None, default: float = 60.0) -> float:
    if not header_val:
        return default
    raw = str(header_val).strip().lower()
    try:
        return max(5.0, float(raw))
    except ValueError:
        pass
    total = 0.0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", raw):
        val = float(num)
        if unit == "ms":
            total += val / 1000.0
        elif unit == "s":
            total += val
        elif unit == "m":
            total += val * 60.0
        elif unit == "h":
            total += val * 3600.0
    return max(5.0, total) if total > 0 else default


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


def _probe_groq(*, budget_ledger: CloudBudgetLedger | None = None) -> dict:
    """Verify Groq free-tier catalog & budget strictly without exposing GROQ_API_KEY."""
    key = load_local_provider_key("GROQ_API_KEY")
    ledger = budget_ledger or CloudBudgetLedger()
    bstat = ledger.status("groq")
    if not key:
        return {
            "provider": "groq",
            "installed": True,
            "configured": False,
            "available": False,
            "billing_class": BILLING_FREE_CLOUD_VERIFIED,
            "quota_status": "KEY_NOT_CONFIGURED",
            "budget": bstat,
            "models": [],
            "reason": "GROQ_API_KEY not configured in local env or ~/.tel99/providers.env",
        }
    can_use, budget_reason = ledger.can_call("groq", estimated_tokens=512)
    try:
        req = Request(
            f"{GROQ_BASE_URL}/models",
            headers={"Authorization": f"Bearer {key}", "User-Agent": "TEL99-Router/1.0"},
        )
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise OSError(f"HTTP {resp.status}")
            payload = json.loads(resp.read(256_000).decode("utf-8", errors="replace"))
        served_ids = {
            row["id"] for row in (payload.get("data") or [])
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        models = []
        for mid, meta in GROQ_FREE_ALLOWLIST.items():
            if mid in served_ids:
                models.append({
                    "id": f"groq/{mid}",
                    "served_model": mid,
                    "provider": "groq",
                    **meta,
                    "confidential_ok": False,
                })
        ok = bool(models) and can_use
        return {
            "provider": "groq",
            "installed": True,
            "configured": True,
            "available": ok,
            "billing_class": BILLING_FREE_CLOUD_VERIFIED,
            "quota_status": "READY" if ok else ("COOLDOWN_OR_BUDGET" if not can_use else "NO_ALLOWLISTED_MODELS"),
            "catalog_total_models": len(served_ids),
            "budget": bstat,
            "models": models,
            "reason": None if ok else (budget_reason if not can_use else "no allowlisted free models in live Groq catalog"),
        }
    except (OSError, HTTPError, URLError, ValueError) as exc:
        return {
            "provider": "groq",
            "installed": True,
            "configured": True,
            "available": False,
            "billing_class": BILLING_UNVERIFIED,
            "quota_status": "UNVERIFIED_FAIL_CLOSED",
            "budget": bstat,
            "models": [],
            "reason": f"Groq catalog probe failed (fail-closed): {type(exc).__name__}",
        }


def _probe_openrouter(*, budget_ledger: CloudBudgetLedger | None = None) -> dict:
    """Verify OpenRouter strictly `:free` + `$0/$0` pricing models from live catalog."""
    key = load_local_provider_key("OPENROUTER_API_KEY")
    ledger = budget_ledger or CloudBudgetLedger()
    bstat = ledger.status("openrouter")
    if not key:
        return {
            "provider": "openrouter",
            "installed": True,
            "configured": False,
            "available": False,
            "billing_class": BILLING_FREE_CLOUD_VERIFIED,
            "quota_status": "KEY_NOT_CONFIGURED",
            "budget": bstat,
            "models": [],
            "reason": "OPENROUTER_API_KEY not configured in local env or ~/.tel99/providers.env",
        }
    can_use, budget_reason = ledger.can_call("openrouter", estimated_tokens=512)
    try:
        req = Request(
            f"{OPENROUTER_BASE_URL}/models",
            headers={"Authorization": f"Bearer {key}", "User-Agent": "TEL99-Router/1.0"},
        )
        with urlopen(req, timeout=12) as resp:
            if resp.status != 200:
                raise OSError(f"HTTP {resp.status}")
            payload = json.loads(resp.read(2_000_000).decode("utf-8", errors="replace"))
        models = []
        for row in (payload.get("data") or []):
            if not isinstance(row, dict):
                continue
            mid = str(row.get("id") or "")
            pricing = row.get("pricing") or {}
            # Fail-closed: MUST end with ':free' AND explicitly declare 0 prompt and 0 completion cost
            if not mid.endswith(":free"):
                continue
            if str(pricing.get("prompt", "1")) != "0" or str(pricing.get("completion", "1")) != "0":
                continue
            if any(k in mid.lower() for k in ("qwen", "gpt-oss", "llama-3.3", "deepseek", "gemma")):
                models.append({
                    "id": f"openrouter/{mid}",
                    "served_model": mid,
                    "provider": "openrouter",
                    "quality_prior": 0.86,
                    "latency_tier": "medium",
                    "role_tier": "executor",
                    "effort_tier": "medium",
                    "supports_tools": True,
                    "context_tokens": int(row.get("context_length") or 32_768),
                    "confidential_ok": False,
                })
        models = models[:8]
        ok = bool(models) and can_use
        return {
            "provider": "openrouter",
            "installed": True,
            "configured": True,
            "available": ok,
            "billing_class": BILLING_FREE_CLOUD_VERIFIED,
            "quota_status": "READY" if ok else ("COOLDOWN_OR_BUDGET" if not can_use else "NO_FREE_MODELS"),
            "budget": bstat,
            "models": models,
            "reason": None if ok else (budget_reason if not can_use else "no verified $0/:free models in OpenRouter catalog"),
        }
    except (OSError, HTTPError, URLError, ValueError) as exc:
        return {
            "provider": "openrouter",
            "installed": True,
            "configured": True,
            "available": False,
            "billing_class": BILLING_UNVERIFIED,
            "quota_status": "UNVERIFIED_FAIL_CLOSED",
            "budget": bstat,
            "models": [],
            "reason": f"OpenRouter catalog probe failed (fail-closed): {type(exc).__name__}",
        }


def probe_all_providers(*, probes: dict | None = None) -> dict:
    """Inspect all configured model/CLI providers in read-only mode."""
    p = probes or {}
    ollama = p["ollama"]() if "ollama" in p else _probe_ollama()
    groq = p["groq"]() if "groq" in p else _probe_groq()
    openrouter = p["openrouter"]() if "openrouter" in p else _probe_openrouter()
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
            "groq": groq,
            "openrouter": openrouter,
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
                    allow_free_cloud: bool = False, is_repair: bool = False,
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
        if bclass == BILLING_FREE_CLOUD_VERIFIED and not allow_free_cloud:
            rejected.append({"provider": pname, "reason": "free cloud requires allow_free_cloud=True"})
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
            if model.get("effort_tier") == "high" and difficulty != "hard" and not is_repair:
                rejected.append({"provider": pname, "id": mid, "reason": "high-effort model reserved for difficulty=hard or repair"})
                continue
            q = _quality_score(model, measured_quality)
            if q < min_quality:
                rejected.append({"provider": pname, "id": mid, "reason": f"quality {q:.2f} < {min_quality:.2f}"})
                continue
            latency_bonus = {"fast": 0.15, "medium": 0.08, "slow": 0.0}.get(model.get("latency_tier"), 0.0)
            # Hybrid policy (§3): local models win routine/easy tasks to preserve cloud quota;
            # free cloud (Groq priority, OpenRouter backup) wins hard reasoning & difficult repairs when non-confidential.
            if bclass == BILLING_LOCAL_FREE:
                local_bonus = 0.90 if (difficulty == "easy" and not is_repair) else 0.20
                cloud_bonus = 0.0
            elif bclass == BILLING_FREE_CLOUD_VERIFIED:
                local_bonus = 0.0
                if difficulty == "easy" and not is_repair:
                    cloud_bonus = 0.0
                else:
                    base_cloud = 0.22 if pname == "groq" else 0.10
                    cloud_bonus = base_cloud + (0.25 if (difficulty == "hard" or is_repair) else 0.0)
            else:
                local_bonus = 0.0
                cloud_bonus = 0.0
            pref_bonus = 0.25 if (preferred_provider and pname == preferred_provider) else 0.0
            role_tier = model.get("role_tier")
            role_bonus = 0.0
            if task_kind in ("orchestration", "planning") and role_tier == "orchestrator":
                role_bonus = 0.18
            elif task_kind in ("code", "execution") and role_tier == "executor":
                role_bonus = 0.18
            score = round(3.0 * q + local_bonus + cloud_bonus + latency_bonus + pref_bonus + role_bonus, 4)
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


# Evidence-backed local specialty priors (updated from TEL99 57-min endurance & A-E functional ablation).
LOCAL_SPECIALTY_BONUS: dict[str, dict[str, float]] = {
    "local/ollama-gemma4-e4b": {
        "python": 0.18, "javascript": 0.16, "analysis": 0.16, "planning": 0.16,
        "repair": 0.16, "documentation": 0.18, "reasoning": 0.14, "tools": 0.06,
    },
    "local/ollama-qwen3.5-9b": {
        "python": 0.14, "javascript": 0.12, "analysis": 0.10, "planning": 0.10,
        "repair": 0.14, "documentation": 0.08, "reasoning": 0.16, "tools": 0.06,
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


class OpenAICompatFreeCloudAdapter:
    """Zero-spend adapter for allowlisted Groq / OpenRouter `:free` endpoints with auto-Ollama fallback."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        timeout: int = 60,
        max_tokens: int = 2048,
        confidential: bool = False,
        fallback_ollama_model: str | None = "gemma4:e4b-tel99-8k",
        budget_ledger: CloudBudgetLedger | None = None,
    ):
        if provider == "groq":
            if model not in GROQ_FREE_ALLOWLIST:
                raise PermissionError(f"Groq model {model!r} is not in TEL99 zero-spend allowlist")
            self.base_url = GROQ_BASE_URL
            self.env_name = "GROQ_API_KEY"
        elif provider == "openrouter":
            if not model.endswith(":free"):
                raise PermissionError(f"OpenRouter model {model!r} must end with ':free'")
            self.base_url = OPENROUTER_BASE_URL
            self.env_name = "OPENROUTER_API_KEY"
        else:
            raise ValueError(f"unsupported free cloud provider: {provider!r}")

        self.provider = provider
        self.model = model
        self.timeout = max(10, min(180, int(timeout)))
        self.max_tokens = max(64, min(4096, int(max_tokens)))
        self.confidential = bool(confidential)
        self.fallback_ollama_model = fallback_ollama_model
        self.budget = budget_ledger or CloudBudgetLedger()
        self.last_metadata: dict = {}

    def _fallback_to_ollama(self, *, system: str, prompt: str, reason: str, response_format=None) -> str:
        if not self.fallback_ollama_model:
            raise ProviderError(f"{self.provider} unavailable ({reason}) and no local fallback configured")
        ol = OllamaNativeProvider(
            model=self.fallback_ollama_model,
            timeout=180,
            max_tokens=min(2048, self.max_tokens),
            keep_alive="120s",
            task_profile="module",
        )
        ans = ol.complete(system=system, prompt=prompt, response_format=response_format)
        self.last_metadata = {
            "provider_used": "ollama",
            "model_used": self.fallback_ollama_model,
            "fallback_used": True,
            "fallback_reason": reason,
            "cost_usd": 0.0,
            "native_metadata": ol.last_metadata,
        }
        return ans

    def complete(self, *, system: str, prompt: str, response_format: str | dict | None = None) -> str:
        self.last_metadata = {}
        safe, egress_err = validate_cloud_egress_safe(system, prompt, confidential=self.confidential)
        if not safe:
            return self._fallback_to_ollama(system=system, prompt=prompt, reason=egress_err or "egress_blocked", response_format=response_format)

        key = load_local_provider_key(self.env_name)
        if not key:
            return self._fallback_to_ollama(system=system, prompt=prompt, reason=f"{self.env_name} missing", response_format=response_format)

        est_tok = max(256, (len(system) + len(prompt)) // 4 + self.max_tokens // 2)
        can_call, b_reason = self.budget.can_call(self.provider, estimated_tokens=est_tok)
        if not can_call:
            return self._fallback_to_ollama(system=system, prompt=prompt, reason=b_reason, response_format=response_format)

        # Gentle TPM pacing based on real provider headers (avoids unnecessary 429s on 8k TPM free tiers)
        bstat = self.budget.status(self.provider)
        last_hdrs = bstat.get("last_headers") or {}
        try:
            rem_tok = int(last_hdrs.get("x-ratelimit-remaining-tokens", "999999"))
            if rem_tok < max(1200, est_tok):
                reset_s = _parse_reset_seconds(last_hdrs.get("x-ratelimit-reset-tokens"), default=4.0)
                time.sleep(min(15.0, max(1.5, reset_s)))
        except (ValueError, TypeError):
            pass

        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "TEL99-Hybrid/1.0",
        }
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/khalidd692/telcoin-trading-intelligence99"
            headers["X-Title"] = "TEL99-Free-Hybrid"

        req = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        t0 = time.monotonic()
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(512_000).decode("utf-8", errors="replace")
                resp_headers = dict(resp.headers.items())
        except HTTPError as exc:
            if exc.code == 429:
                retry_hdr = (
                    (exc.headers.get("Retry-After") or exc.headers.get("x-ratelimit-reset-tokens"))
                    if exc.headers
                    else None
                )
                wait_s = min(65.0, _parse_reset_seconds(retry_hdr, default=30.0))
                self.budget.record_rate_limit(self.provider, retry_after_s=wait_s)
                return self._fallback_to_ollama(
                    system=system, prompt=prompt, reason=f"HTTP 429 cooldown {wait_s:.0f}s", response_format=response_format
                )
            return self._fallback_to_ollama(
                system=system, prompt=prompt, reason=f"HTTP {exc.code}", response_format=response_format
            )
        except (URLError, OSError, TimeoutError) as exc:
            return self._fallback_to_ollama(
                system=system, prompt=prompt, reason=f"network:{type(exc).__name__}", response_format=response_format
            )

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("empty content")
        except (ValueError, KeyError, IndexError, TypeError):
            return self._fallback_to_ollama(system=system, prompt=prompt, reason="invalid cloud response JSON", response_format=response_format)

        usage = data.get("usage") or {}
        p_tok = int(usage.get("prompt_tokens") or 0)
        c_tok = int(usage.get("completion_tokens") or 0)
        self.budget.record_usage(self.provider, prompt_tokens=p_tok, completion_tokens=c_tok, headers=resp_headers)
        self.last_metadata = {
            "provider_used": self.provider,
            "model_used": self.model,
            "fallback_used": False,
            "duration_seconds": round(time.monotonic() - t0, 2),
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "cost_usd": 0.0,
        }
        return content


def build_adapter(selection: dict, *, allow_subscription_cli: bool = False,
                  allow_free_cloud: bool = False, confidential: bool = True,
                  use_sdk_backend: bool = False, fallback_ollama_model: str | None = "gemma4:e4b-tel99-8k"):
    """Instantiate an authorized adapter from a router selection."""
    if not isinstance(selection, dict) or not selection.get("provider"):
        raise ValueError("valid provider selection required")
    provider = selection["provider"]
    model = selection.get("served_model") or selection.get("model")
    if provider == "ollama":
        if use_sdk_backend:
            return AntigravitySDKAdapter(model=model)
        return OllamaAdapter(model=model)
    if provider in ("groq", "openrouter"):
        if not allow_free_cloud or confidential:
            raise PermissionError(f"free cloud provider {provider!r} requires allow_free_cloud=True and confidential=False")
        return OpenAICompatFreeCloudAdapter(
            provider=provider,
            model=model,
            confidential=confidential,
            fallback_ollama_model=fallback_ollama_model,
        )
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
