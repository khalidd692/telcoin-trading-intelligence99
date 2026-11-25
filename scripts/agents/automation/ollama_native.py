"""Native, loopback-only Ollama transport for bounded TEL99 code missions.

This is not a general-purpose agent tool runner. It returns one untrusted
completion; the separate Docker verifier decides whether to accept it.
"""

from __future__ import annotations

import json
import re
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from scripts.agents.intelligence import catalog
from scripts.agents.native.provider import ProviderError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


ALLOWED_KEEP_ALIVE = frozenset({"0s", "60s", "90s", "120s"})
TASK_PROFILE_LIMITS: dict[str, tuple[int, int]] = {
    "patch": (1024, 90),
    "module": (2048, 180),
    "large_module": (4096, 300),
}
MAX_RESPONSE_BYTES_CAP = 512 * 1024


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
) -> dict:
    """Compute bounded adaptive max_tokens & timeout from task profile, RAM headroom & speed."""
    if task_profile not in TASK_PROFILE_LIMITS:
        raise ValueError(f"unknown task_profile: {task_profile!r}")
    max_cap, timeout_cap = TASK_PROFILE_LIMITS[task_profile]
    ram_clamped = False
    effective_profile = task_profile

    # Protect 16 GB host: clamp large_module (4096) down to module (2048) if free RAM < 2500 MiB.
    if effective_profile == "large_module" and available_memory_mib is not None and available_memory_mib < 2500:
        effective_profile = "module"
        max_cap, timeout_cap = TASK_PROFILE_LIMITS[effective_profile]
        ram_clamped = True
    if effective_profile == "module" and available_memory_mib is not None and available_memory_mib < 1400:
        effective_profile = "patch"
        max_cap, timeout_cap = TASK_PROFILE_LIMITS[effective_profile]
        ram_clamped = True

    est_tokens = max(256, int(max(10, estimated_lines) * 22))
    if effective_profile == "patch":
        chosen_tokens = min(max_cap, max(512, est_tokens))
    elif effective_profile == "module":
        chosen_tokens = min(max_cap, max(1024, 2048 if estimated_lines >= 60 else est_tokens))
    else:
        chosen_tokens = min(max_cap, max(2048, 4096 if estimated_lines >= 120 else est_tokens))

    tok_s = float(measured_tok_per_sec) if (measured_tok_per_sec and measured_tok_per_sec > 0.5) else (
        6.0 if "9b" in model.lower() else 14.0
    )
    computed_timeout = int(round((chosen_tokens / tok_s) * 1.45 + 25))
    chosen_timeout = max(30, min(timeout_cap, computed_timeout))

    return {
        "model": model,
        "requested_profile": task_profile,
        "effective_profile": effective_profile,
        "max_tokens": chosen_tokens,
        "timeout": chosen_timeout,
        "num_ctx": 8192,
        "ram_clamped": ram_clamped,
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
        self.max_response_bytes = min(MAX_RESPONSE_BYTES_CAP, max(65_536, max_tokens * 32))
        self.last_metadata = {}

    def complete(self, *, system: str, prompt: str) -> str:
        self.last_metadata = {}
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": 8192,
                "num_predict": self.max_tokens,
                "temperature": 0,
            },
        }
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
        try:
            with client.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ProviderError("Ollama returned a non-success HTTP status")
                raw = response.read(self.max_response_bytes + 1)
        except OSError as exc:
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
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*[ \t]*\r?\n?", "", cont.strip())
            cleaned = re.sub(r"\r?\n?```$", "", cleaned)
            answer = answer.rstrip() + "\n" + cleaned
            continuations += 1
        self.last_metadata["continuations"] = continuations
        return answer
