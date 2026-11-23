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

  * models must be allowlisted or explicitly approved for a loopback runtime;
  * a remote endpoint requires an HTTPS URL and a key, with one exception
    for the pinned Kilo Auto Free gateway and synthetic data;
  * an error never echoes the API key or the request headers.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol, runtime_checkable

_AGENTS_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

import team_config as cfg  # noqa: E402

_MAX_REPLY_BYTES = 1024 * 1024
_MAX_CATALOG_BYTES = 4 * 1024 * 1024
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
KILO_HOST = "ai-gateway.kilo.ai"
KILO_BASE_URL = f"https://{KILO_HOST}/api/v1"


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_zero_price(value) -> bool:
    if type(value) not in (str, int, Decimal):
        return False
    try:
        return Decimal(value).is_zero()
    except InvalidOperation:
        return False


class OpenAICompatibleProvider:
    """Adapter for an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, *, model: str, base_url: str, api_key: str = "",
                 timeout: int = 60, name: str = "openai-compatible",
                 included_local_model: str = "", synthetic_data: bool = False,
                 max_tokens: int | None = None) -> None:
        if not isinstance(base_url, str):
            raise ProviderConfigError("base_url must be an http(s) URL")
        try:
            endpoint = urllib.parse.urlsplit(base_url)
            host = endpoint.hostname
            endpoint.port  # Validate the host's port, if supplied.
        except ValueError:
            raise ProviderConfigError("invalid compatible provider URL") from None
        local = host in LOCAL_HOSTS
        if (not host or endpoint.scheme not in ("http", "https") or endpoint.username is not None
                or endpoint.query or endpoint.fragment or (not local and endpoint.scheme != "https")):
            raise ProviderConfigError("provider requires HTTPS or an explicit loopback URL")
        self._kilo_free = model == cfg.KILO_FREE_MODEL_ID
        if self._kilo_free or host == KILO_HOST:
            if not self._kilo_free or base_url.rstrip("/") != KILO_BASE_URL:
                raise ProviderConfigError("Kilo Auto Free requires the exact official HTTPS gateway and model")
            if api_key or synthetic_data is not True:
                raise ProviderConfigError("Kilo Auto Free requires anonymous use and explicit synthetic data")
        listed = model in cfg.NATIVE_FREE_MODEL_IDS
        if not listed and not (model and local and model == included_local_model):
            raise ProviderConfigError("model is outside the free allowlist or approved loopback runtime")
        if not api_key and not (local or self._kilo_free):
            raise ProviderConfigError("api_key is required for a non-local endpoint")
        self.requires_explicit_quota = self._kilo_free or not listed
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout = int(timeout)
        self.max_tokens = max_tokens
        self.name = "kilo-auto-free" if self._kilo_free else name
        self.last_completion_evidence: dict | None = None
        handlers = [urllib.request.ProxyHandler({})] if local or self._kilo_free else []
        self._opener = urllib.request.build_opener(_NoRedirect(), *handlers)

    def _read_json(self, request, limit: int) -> tuple[int, dict, bytes]:
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ProviderError("provider reply exceeds the byte limit")
                return response.status, json.loads(raw, parse_float=Decimal), raw
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"provider HTTP {exc.code}") from None
        except ProviderError:
            raise
        except Exception as exc:  # A provider exception may contain credentials.
            raise ProviderError(f"provider response unavailable: {type(exc).__name__}") from None

    def _verify_kilo_catalog(self) -> dict:
        request = urllib.request.Request(f"{KILO_BASE_URL}/models")
        status, catalog, raw = self._read_json(request, _MAX_CATALOG_BYTES)
        models = catalog.get("data") if isinstance(catalog, dict) else None
        matches = [entry for entry in models if isinstance(entry, dict)
                   and entry.get("id") == cfg.KILO_FREE_MODEL_ID] if isinstance(models, list) else []
        if status != 200 or len(matches) != 1:
            raise ProviderError("Kilo Auto Free is unavailable in the catalog")
        model = matches[0]
        pricing = model.get("pricing")
        may_train = model.get("mayTrainOnYourPrompts")
        if (model.get("isFree") is not True or type(may_train) is not bool
                or not isinstance(pricing, dict) or not {"prompt", "completion"} <= pricing.keys()
                or not all(_is_zero_price(value) for value in pricing.values())):
            raise ProviderError("Kilo Auto Free catalog does not attest zero price and privacy metadata")
        return {"catalog_sha256": hashlib.sha256(raw).hexdigest(),
                "may_train_on_prompts": may_train}

    def complete(self, *, system: str, prompt: str) -> str:
        self.last_completion_evidence = None
        catalog = self._verify_kilo_catalog() if self._kilo_free else None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        if self._kilo_free:
            payload["max_tokens"] = 8192
        elif self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if self._api_key:
            req.add_header("Authorization", f"Bearer {self._api_key}")
        status, body, raw = self._read_json(req, _MAX_REPLY_BYTES)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("provider returned an unexpected payload") from None
        if catalog is not None:
            usage = body.get("usage")
            response_model = body.get("model")
            if (status != 200 or not isinstance(usage, dict) or not _is_zero_price(usage.get("cost"))
                    or not isinstance(response_model, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", response_model)
                    or not isinstance(content, str) or not content.strip()):
                raise ProviderError("Kilo Auto Free completion has no valid zero-cost proof")
            self.last_completion_evidence = {
                **catalog, "http_status": status, "response_model": response_model,
                "cost_usd": "0", "response_sha256": hashlib.sha256(raw).hexdigest(),
            }
        return content


def free_model_ids() -> list[str]:
    """The native runner's free model allowlist (single source: team_config)."""
    return sorted(cfg.NATIVE_FREE_MODEL_IDS)


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
            included_local_model=config.get("included_local_model", ""),
            synthetic_data=config.get("synthetic_data", False),
        )
    raise ProviderConfigError(f"unknown provider {name!r}")


def provider_from_env(*, synthetic_data: bool = False) -> ModelProvider:
    """Build the real provider from environment variables.

    Variables (none committed to the repository):
        TEL99_NATIVE_MODEL     must be on the free allowlist
        TEL99_NATIVE_BASE_URL  OpenAI-compatible base URL
        TEL99_NATIVE_API_KEY   key (empty for anonymous Kilo Auto Free)
        TEL99_NATIVE_INCLUDED_MODEL  operator-approved model for a loopback endpoint
    """
    model = os.environ.get("TEL99_NATIVE_MODEL", "")
    base_url = os.environ.get("TEL99_NATIVE_BASE_URL", "")
    api_key = os.environ.get("TEL99_NATIVE_API_KEY", "")
    if not model or not base_url:
        raise ProviderConfigError(
            "TEL99_NATIVE_MODEL and TEL99_NATIVE_BASE_URL are required to build "
            "the real provider (none committed to the repository)"
        )
    return OpenAICompatibleProvider(
        model=model, base_url=base_url, api_key=api_key, synthetic_data=synthetic_data,
        included_local_model=os.environ.get("TEL99_NATIVE_INCLUDED_MODEL", ""),
    )
