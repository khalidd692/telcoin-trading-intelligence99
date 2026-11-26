"""Native, loopback-only Ollama transport for bounded TEL99 code missions.

This is not a general-purpose agent tool runner. It returns one untrusted
completion; the separate Docker verifier decides whether to accept it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from scripts.agents.automation import ide_coordination
from scripts.agents.intelligence import catalog
from scripts.agents.native.provider import ProviderError


class ResourceUnavailableError(ProviderError):
    """Infrastructure/RAM/lease contention error (distinct from model logic errors)."""

    error_category = "ENVIRONMENT_ERROR"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


ALLOWED_KEEP_ALIVE = frozenset({"0s", "60s", "90s", "120s"})
TASK_PROFILE_LIMITS: dict[str, tuple[int, int]] = {
    "patch": (1024, 90),
    "module": (2048, 240),
    "large_module": (4096, 360),
}
MAX_RESPONSE_BYTES_CAP = 512 * 1024


def optimal_cpu_threads() -> int:
    """Use physical CPU cores (e.g., 8 on 16-thread Ryzen 7 5700U) to avoid SMT thrashing."""
    logical = os.cpu_count() or 8
    physical_est = logical // 2 if logical >= 8 else logical
    return max(2, min(12, physical_est))


def extract_code_block(reply: str) -> str:
    """Extract code cleanly from fenced markdown blocks, including truncated unclosed fences."""
    text = (reply or "").strip()
    if not text:
        return ""
    closed = re.findall(r"```[a-zA-Z0-9_-]*[ \t]*\r?\n(.*?)\r?\n```", text, re.DOTALL)
    if closed:
        return max(closed, key=len).strip() + "\n"
    unclosed = re.search(r"```[a-zA-Z0-9_-]*[ \t]*\r?\n(.*)$", text, re.DOTALL)
    if unclosed:
        return unclosed.group(1).strip() + "\n"
    return text + "\n"


def compute_adaptive_budget(
    model: str,
    *,
    task_profile: str = "patch",
    estimated_lines: int = 40,
    available_memory_mib: float | None = None,
    measured_tok_per_sec: float | None = None,
    model_is_resident: bool | None = None,
) -> dict:
    """Compute bounded adaptive max_tokens, num_ctx, threads & timeout.

    Explicitly distinguishes pre-load free RAM (model_is_resident=False) from
    already-resident model headroom (model_is_resident=True) on 16 GB hosts.
    """
    if task_profile not in TASK_PROFILE_LIMITS:
        raise ValueError(f"unknown task_profile: {task_profile!r}")
    max_cap, timeout_cap = TASK_PROFILE_LIMITS[task_profile]
    ram_clamped = False
    effective_profile = task_profile

    if model_is_resident is False:
        large_thresh, mod_thresh, min_safe = 2800.0, 2200.0, 1800.0
    elif model_is_resident is True:
        large_thresh, mod_thresh, min_safe = 1800.0, 700.0, 550.0
    else:
        # Backward-compatible default when caller does not specify residency
        large_thresh, mod_thresh, min_safe = 2200.0, 700.0, 550.0

    insufficient_ram = available_memory_mib is not None and available_memory_mib < min_safe
    if effective_profile == "large_module" and available_memory_mib is not None and available_memory_mib < large_thresh:
        effective_profile = "module"
        max_cap, timeout_cap = TASK_PROFILE_LIMITS[effective_profile]
        ram_clamped = True
    if effective_profile == "module" and available_memory_mib is not None and available_memory_mib < mod_thresh:
        effective_profile = "patch"
        max_cap, timeout_cap = TASK_PROFILE_LIMITS[effective_profile]
        ram_clamped = True

    est_tokens = max(256, int(max(10, estimated_lines) * 22))
    if effective_profile == "patch":
        chosen_tokens = min(max_cap, max(512, est_tokens))
    elif effective_profile == "module":
        chosen_tokens = min(max_cap, max(1024, 2048 if estimated_lines >= 75 else est_tokens))
    else:
        chosen_tokens = min(max_cap, max(2048, 4096 if estimated_lines >= 120 else est_tokens))

    tok_s = float(measured_tok_per_sec) if (measured_tok_per_sec and measured_tok_per_sec > 0.5) else (
        5.5 if "9b" in model.lower() else 9.5
    )
    cold_load_pad = 40 if model_is_resident is False else 0
    computed_timeout = int(round((chosen_tokens / tok_s) * 1.35 + 35 + cold_load_pad))
    chosen_timeout = max(30, min(timeout_cap, computed_timeout))
    num_ctx = 4096 if (effective_profile == "patch" and available_memory_mib is not None and available_memory_mib < 1400) else 8192

    ram_state = (
        "insufficient_ram" if insufficient_ram
        else ("clamped" if ram_clamped else ("resident_ok" if model_is_resident else "preload_ok"))
    )
    return {
        "model": model,
        "requested_profile": task_profile,
        "effective_profile": effective_profile,
        "max_tokens": chosen_tokens,
        "timeout": chosen_timeout,
        "num_ctx": num_ctx,
        "num_thread": optimal_cpu_threads(),
        "model_is_resident": model_is_resident,
        "ram_state": ram_state,
        "ram_clamped": ram_clamped,
        "insufficient_ram": insufficient_ram,
    }


class OllamaNativeProvider:
    name = "ollama-native-code"

    def __init__(
        self,
        *,
        model: str,
        timeout: int = 80,
        max_tokens: int = 768,
        keep_alive: str = "0s",
        task_profile: str = "patch",
        num_ctx: int = 8192,
        num_thread: int | None = None,
        coordination_state_root: Path | str | None = None,
        use_coordination_lease: bool = True,
        lease_wait_timeout: float = 120.0,
        priority: str = "background",
    ):
        approved = [
            spec for spec in catalog.MODEL_CATALOG
            if spec.provider == "ollama" and spec.is_local and spec.is_free
            and model in spec.served_ids
        ]
        if task_profile not in TASK_PROFILE_LIMITS:
            raise ProviderError("unapproved Ollama task profile")
        max_tok_limit, max_timeout_limit = TASK_PROFILE_LIMITS[task_profile]
        if (
            len(approved) != 1
            or not (1 <= max_tokens <= max_tok_limit)
            or not (1 <= timeout <= max_timeout_limit)
            or keep_alive not in ALLOWED_KEEP_ALIVE
        ):
            raise ProviderError("unapproved Ollama model or generation limit")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.keep_alive = keep_alive
        self.task_profile = task_profile
        self.num_ctx = max(2048, min(8192, int(num_ctx)))
        self.num_thread = optimal_cpu_threads() if num_thread is None else max(2, min(12, int(num_thread)))
        self.coordination_state_root = coordination_state_root
        self.use_coordination_lease = bool(use_coordination_lease) and os.environ.get("TEL99_DISABLE_INFERENCE_LEASE", "") != "1"
        self.lease_wait_timeout = float(lease_wait_timeout)
        self.priority = str(priority or "background")
        self.max_response_bytes = min(MAX_RESPONSE_BYTES_CAP, max(65_536, max_tokens * 32))
        self.last_metadata = {}

    def complete(self, *, system: str, prompt: str, response_format: str | dict | None = None) -> str:
        from contextlib import nullcontext

        self.last_metadata = {}
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.max_tokens,
                "num_thread": self.num_thread,
                "temperature": 0,
            },
        }
        if response_format is not None:
            if response_format != "json" and not isinstance(response_format, dict):
                raise ProviderError("invalid Ollama response_format; expected 'json' or JSON schema dict")
            payload["format"] = response_format
        # Request final code immediately for supported thinking models only.
        # Older code-only models need no thinking override.
        if self.model in ("gemma4:e4b-tel99-8k", "qwen3.5:9b-q4_K_M"):
            payload["think"] = False
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            "http://127.0.0.1:11434/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Prevent proxy settings or HTTP redirects from changing the destination.
        client = build_opener(ProxyHandler({}), _NoRedirect())
        lease_cm = (
            ide_coordination.local_inference_lease(
                "ollama",
                state_root=self.coordination_state_root,
                model=self.model,
                wait_timeout=self.lease_wait_timeout,
                ttl_seconds=max(120, self.timeout + 120),
                priority=self.priority,
            )
            if self.use_coordination_lease
            else nullcontext(None)
        )
        try:
            with lease_cm:
                with client.open(request, timeout=self.timeout) as response:
                    if response.status != 200:
                        raise ProviderError("Ollama returned a non-success HTTP status")
                    raw = response.read(self.max_response_bytes + 1)
        except ide_coordination.LeaseConflict as exc:
            raise ResourceUnavailableError(f"Local inference resource busy: {exc}") from exc
        except TimeoutError as exc:
            raise ResourceUnavailableError("Ollama request timed out") from exc
        except OSError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError) or "timed out" in str(exc).lower():
                raise ResourceUnavailableError("Ollama request timed out") from exc
            raise ProviderError("Ollama native API unavailable") from exc
        if len(raw) > self.max_response_bytes:
            raise ProviderError("Ollama response exceeds limit")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderError("Ollama response is not valid JSON") from exc
        if not isinstance(result, dict) or result.get("model") != self.model:
            raise ProviderError("Ollama reported an unapproved model")
        answer = result.get("response")
        if not isinstance(answer, str):
            raise ProviderError("Ollama response contains no text completion")
        # Store only bounded technical metadata. Never treat model thinking as code
        # and never write the raw thinking trace into a receipt or checkpoint.
        done_reason = result.get("done_reason")
        if done_reason not in ("stop", "length", "unload"):
            done_reason = "unknown"
        count = result.get("eval_count")
        if type(count) is not int or not 0 <= count <= 1_000_000:
            count = None
        eval_dur_ns = result.get("eval_duration")
        self.last_tokens_per_second = (
            round(count / (eval_dur_ns / 1e9), 2)
            if type(count) is int and type(eval_dur_ns) is int and eval_dur_ns > 0
            else None
        )
        self.last_metadata = {
            "done_reason": done_reason,
            "eval_count": count,
            "thinking_present": bool(result.get("thinking")),
        }
        if self.task_profile != "patch":
            self.last_metadata["task_profile"] = self.task_profile
            if self.last_tokens_per_second is not None:
                self.last_metadata["tokens_per_second"] = self.last_tokens_per_second
        return answer

    def complete_with_continuation(
        self,
        *,
        system: str,
        prompt: str,
        max_continuations: int = 1,
    ) -> str:
        """Complete a prompt and perform at most `max_continuations` bounded continuations on length truncation."""
        if not 0 <= max_continuations <= 2:
            raise ValueError("max_continuations must be 0..2")
        answer = self.complete(system=system, prompt=prompt)
        continuations = 0
        while continuations < max_continuations and self.last_metadata.get("done_reason") == "length":
            tail = answer[-1000:]
            cont = self.complete(
                system=system,
                prompt=(
                    "Your previous output hit the token limit. Continue seamlessly from the exact last line "
                    "without repeating earlier lines or prose:\n" + tail
                ),
            )
            if not cont or not cont.strip():
                break
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*[ \t]*\r?\n?", "", cont)
            cleaned = re.sub(r"\r?\n?```\s*$", "", cleaned)
            sep = " " if (not answer.endswith("\n") and answer.rstrip().endswith((",", "(", "=", "+", ".", "\\"))) else "\n"
            answer = answer.rstrip("\r\n") + sep + cleaned.lstrip("\r\n")
            continuations += 1
        self.last_metadata["continuations"] = continuations
        return answer
