#!/usr/bin/env python3
"""Interchangeable model-provider contract for the TEL99 native mission runner.

The point of this module (owner directive, issue #86) is that the project owns
a *native* way to run a bounded agent mission whose model provider can be
swapped **without touching the kernel**. Hermes Desktop, Kilo Agent Manager and
OpenHands Cloud are development tools; none of them is a runtime dependency of
this package.

Two implementations share one tiny contract (``ModelProvider``):

  * :class:`ScriptedProvider` — deterministic, offline, used by tests and the
    demo. It returns a fixed list of scripted responses; it never reaches the
    network. This is what makes the mission verdict reproducible in CI.
  * :class:`OpenAICompatibleProvider` — a real HTTP adapter (stdlib ``urllib``)
    for any OpenAI-compatible ``/chat/completions`` endpoint. The endpoint, key
    and model are read at call time and are **never** written to disk or logs.

Fail-closed rules, enforced in code and not by convention:

  * only models on ``team_config.FREE_MODEL_IDS`` may be used (no-spend rule);
  * an endpoint must be an ``http(s)`` URL; a non-local endpoint requires a key;
  * an error never echoes the API key or the request headers.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol, runtime_checkable

_AGENTS_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

import team_config as cfg  # noqa: E402

# Hosts for which an empty API key is acceptable (a local model server).
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class ProviderError(RuntimeError):
    """Raised when a provider cannot be used. Fail-closed: callers must stop."""


class ProviderConfigError(ProviderError):
    """Raised when a provider is configured unsafely or incompletely."""


@runtime_checkable
class ModelProvider(Protocol):
    """The single contract the mission kernel depends on.

    Any object with a ``name`` attribute and a ``complete`` method is a valid
    provider. Swapping providers never requires a change to ``mission.py``.
    """

    name: str

    def complete(self, *, system: str, prompt: str) -> str:
        """Return the model's completion as plain text."""


class ScriptedProvider:
    """Deterministic, offline provider for tests and the demo.

    ``responses`` is consumed in order; the provider is exhausted when the list
    is empty and then raises, so a test can assert the exact number of calls.
    """

    def __init__(self, responses: list[str] | tuple[str, ...], *,
                 name: str = "scripted") -> None:
        self._responses = list(responses)
        self.name = name
        self.calls = 0

    def complete(self, *, system: str, prompt: str) -> str:
        self.calls += 1
        if not self._responses:
            raise ProviderError("scripted provider exhausted (no response left)")
        return self._responses.pop(0)


class OpenAICompatibleProvider:
    """Real adapter for any OpenAI-compatible chat-completions endpoint."""

    def __init__(self, *, model: str, base_url: str, api_key: str = "",
                 timeout: int = 60, name: str = "openai-compatible") -> None:
        if model not in cfg.FREE_MODEL_IDS:
            raise ProviderConfigError(
                f"model {model!r} is not on the free allowlist "
                f"({sorted(cfg.FREE_MODEL_IDS)})"
            )
        if not isinstance(base_url, str) or not base_url.startswith(
                ("http://", "https://")):
            raise ProviderConfigError("base_url must be an http(s) URL")
        host = urllib.parse.urlsplit(base_url).hostname or ""
        if not api_key and host not in LOCAL_HOSTS:
            raise ProviderConfigError(
                "api_key is required for a non-local endpoint (fail-closed)"
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout = int(timeout)
        self.name = name

    def complete(self, *, system: str, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if self._api_key:
            req.add_header("Authorization", f"Bearer {self._api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            # Never include headers (they carry the key).
            raise ProviderError(f"provider HTTP {exc.code}") from None
        except Exception as exc:  # noqa: BLE001 - a provider must never leak detail
            raise ProviderError(f"provider unreachable: {type(exc).__name__}") from None
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("provider returned an unexpected payload") from None


def free_model_ids() -> list[str]:
    """The free, no-spend model allowlist (single source: team_config)."""
    return sorted(cfg.FREE_MODEL_IDS)


def get_provider(name: str, **config) -> ModelProvider:
    """Build a provider by name. Unknown names fail closed."""
    key = (name or "").lower()
    if key == "scripted":
        return ScriptedProvider(config.get("responses") or [],
                                name=config.get("as_name", "scripted"))
    if key in ("openai", "openai-compatible"):
        return OpenAICompatibleProvider(
            model=config["model"],
            base_url=config["base_url"],
            api_key=config.get("api_key", ""),
            timeout=int(config.get("timeout", 60)),
        )
    raise ProviderConfigError(f"unknown provider {name!r}")


def provider_from_env() -> ModelProvider:
    """Build the real provider from environment variables.

    Variables (none committed to the repository):
        TEL99_NATIVE_MODEL     must be on the free allowlist
        TEL99_NATIVE_BASE_URL  OpenAI-compatible base URL
        TEL99_NATIVE_API_KEY   key (optional for localhost)
    """
    model = os.environ.get("TEL99_NATIVE_MODEL", "")
    base_url = os.environ.get("TEL99_NATIVE_BASE_URL", "")
    api_key = os.environ.get("TEL99_NATIVE_API_KEY", "")
    if not model or not base_url:
        raise ProviderConfigError(
            "TEL99_NATIVE_MODEL and TEL99_NATIVE_BASE_URL are required to build "
            "the real provider (none committed to the repository)"
        )
    return OpenAICompatibleProvider(model=model, base_url=base_url, api_key=api_key)
