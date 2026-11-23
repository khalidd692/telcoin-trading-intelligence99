"""Native, loopback-only Ollama transport for bounded TEL99 code missions.

This is not a general-purpose agent tool runner. It returns one untrusted
completion; the separate Docker verifier decides whether to accept it.
"""

from __future__ import annotations

import json
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from scripts.agents.automation import local_model_routing
from scripts.agents.intelligence import catalog
from scripts.agents.native.provider import ProviderError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class OllamaNativeProvider:
    name = "ollama-native-code"

    def __init__(self, *, model: str, timeout: int = 80, max_tokens: int = 768):
        approved = [
            spec for spec in catalog.MODEL_CATALOG
            if spec.provider == "ollama" and spec.is_local and spec.is_free
            and model in spec.served_ids
        ]
        if len(approved) != 1 or not (1 <= max_tokens <= 1024) or not (1 <= timeout <= 90):
            raise ProviderError("unapproved Ollama model or generation limit")
        self.spec = approved[0]
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.last_metadata = {}

    def complete(self, *, system: str, prompt: str) -> str:
        self.last_metadata = {}
        if not local_model_routing.has_model_memory(self.spec, local_model_routing.available_memory_mib()):
            raise ProviderError("insufficient or unavailable physical memory for Ollama model and reserve")
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "0s",
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
                raw = response.read(65_537)
        except OSError as exc:
            raise ProviderError("Ollama native API unavailable") from exc
        if len(raw) > 65_536:
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
        self.last_metadata = {
            "done_reason": done_reason,
            "eval_count": count,
            "thinking_present": bool(result.get("thinking")),
        }
        return answer
