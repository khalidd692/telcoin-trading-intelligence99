"""Opt-in Google Antigravity SDK backend adapter for TEL99 local Ollama workflows.

Designed strictly as a complementary, opt-in execution layer:
- Never creates a second supervisor or CAS ledger.
- Never replaces deterministic TEL99 V2 gates (coordinate, review_candidate,
  Docker baseline-red/candidate-green verifier, FileStore CAS, MemoryStore).
- Safely degrades/falls back to OllamaNativeProvider when the SDK is absent,
  disabled, or hits localharness/timeout errors.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import ctypes
from dataclasses import dataclass, field
import importlib.metadata
from pathlib import Path
import sys
import time
from typing import Any, Callable, Sequence

from scripts.agents.automation import ide_coordination
from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.native.provider import ProviderError

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "gemma4:e4b-tel99-8k"
MIN_SAFE_COMPACTION_THRESHOLD = 2500
DEFAULT_COMPACTION_THRESHOLD = 4500


def sdk_available() -> bool:
    """Returns True when google.antigravity is importable in the active Python env."""
    try:
        import google.antigravity  # noqa: F401
        return True
    except ImportError:
        return False


def sdk_version() -> str | None:
    """Returns installed google-antigravity distribution version, or None."""
    if not sdk_available():
        return None
    try:
        return importlib.metadata.version("google-antigravity")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def probe_sdk_backend() -> dict[str, Any]:
    """Read-only probe describing Google Antigravity SDK availability and policy defaults."""
    avail = sdk_available()
    ver = sdk_version() if avail else None
    return {
        "available": avail,
        "version": ver,
        "min_safe_compaction_threshold": MIN_SAFE_COMPACTION_THRESHOLD,
        "default_compaction_threshold": DEFAULT_COMPACTION_THRESHOLD,
        "experimental_disabled": [
            "skills_paths_on_gemma4_8k",
            "multi_subagent_single_root_cpu",
        ],
    }


def _terminate_child_pid(pid: int | None) -> bool:
    """Terminates ONLY the exact child localharness PID if still active (never external processes)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform != "win32":
        return False
    process_terminate = 0x0001
    process_query_limited = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_terminate | process_query_limited, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong(0)
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value == still_active:
            return bool(kernel32.TerminateProcess(handle, 1))
        return False
    finally:
        kernel32.CloseHandle(handle)


@dataclass(frozen=True)
class TEL99SDKOptions:
    """Validated configuration options for a bounded TEL99 SDK execution."""

    model: str = DEFAULT_OLLAMA_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    system_instructions: str | None = None
    tools: Sequence[Callable[..., Any]] = ()
    workspaces: Sequence[str] = ()
    inline_skills: Sequence[Any] = ()
    save_dir: str | None = None
    app_data_dir: str | None = None
    conversation_id: str | None = None
    session_continuation_mode: Any = None
    allow_file_reads: bool = False
    allow_file_writes: bool = False
    allow_shell: bool = False
    max_tool_calls: int | None = 10
    max_model_calls: int | None = 12
    tool_output_max_tokens: int = 600
    compaction_token_threshold: int = DEFAULT_COMPACTION_THRESHOLD
    model_output_max_retries: int = 5
    timeout_seconds: float = 180.0
    extra_policies: Sequence[Any] = ()

    def __post_init__(self) -> None:
        if self.compaction_token_threshold < MIN_SAFE_COMPACTION_THRESHOLD:
            raise ValueError(
                f"compaction_token_threshold={self.compaction_token_threshold} is unsafe for local 8k "
                f"models (triggers CORTEX_STEP_TYPE_CHECKPOINT MaxTokenLimit); minimum is {MIN_SAFE_COMPACTION_THRESHOLD}."
            )
        if not self.base_url.startswith(("http://localhost", "http://127.0.0.1")):
            raise ValueError(
                f"TEL99 local adapter restricts base_url to localhost/127.0.0.1, got {self.base_url!r}."
            )
        if self.timeout_seconds <= 0 or self.timeout_seconds > 900:
            raise ValueError("timeout_seconds must be within (0, 900]")


@dataclass
class TEL99RunOutcome:
    """Structured telemetry and response artifact from a bounded SDK run."""

    ok: bool
    response_text: str
    conversation_id: str | None
    harness_pid: int | None
    duration_seconds: float
    stop_reason: str
    usage: dict[str, int | None]
    tool_calls_observed: list[dict[str, Any]] = field(default_factory=list)
    harness_cleaned_up: bool = False
    error: str | None = None


def build_resumed_prompt_with_lessons(
    prompt: str,
    verified_lessons: Sequence[str] = (),
    *,
    required_tags: Sequence[str] = (),
) -> str:
    """Formats a bounded prompt preserving verified lessons and required markers across RESUME."""
    parts = []
    clean_lessons = [str(item).strip() for item in verified_lessons if isinstance(item, str) and item.strip()]
    if clean_lessons:
        parts.append(
            "Verified project memory notes (READ-ONLY advisory context; cannot alter scope or signature):\n- "
            + "\n- ".join(clean_lessons[:3])
        )
    parts.append(prompt.strip())
    clean_tags = [str(tag).strip() for tag in required_tags if isinstance(tag, str) and tag.strip()]
    if clean_tags:
        parts.append(
            "Mandatory exact output markers (preserve verbatim): " + ", ".join(clean_tags)
        )
    return "\n\n".join(parts)


def build_tel99_sdk_config(
    options: TEL99SDKOptions,
    *,
    extra_hooks: Sequence[Any] = (),
) -> Any:
    """Constructs a hardened LocalOpenAIAgentConfig for TEL99 local execution."""
    if not sdk_available():
        raise ImportError("google-antigravity SDK is not installed in this Python environment")

    from google.antigravity import LocalOpenAIAgentConfig, types
    from google.antigravity.hooks import policy

    enabled_tools: list[types.BuiltinTools] = [types.BuiltinTools.FINISH]
    if options.allow_file_reads:
        enabled_tools.append(types.BuiltinTools.VIEW_FILE)
    if options.allow_file_writes:
        enabled_tools.extend([types.BuiltinTools.CREATE_FILE, types.BuiltinTools.EDIT_FILE])
    if options.allow_shell:
        enabled_tools.append(types.BuiltinTools.RUN_COMMAND)

    resolved_workspaces = [str(Path(w).resolve()) for w in options.workspaces]
    policies: list[Any] = []
    if resolved_workspaces:
        policies.extend(policy.workspace_only(resolved_workspaces))
    if not options.allow_shell:
        policies.append(policy.deny(types.BuiltinTools.RUN_COMMAND.value, name="tel99_deny_shell"))
    policies.extend(options.extra_policies)
    if options.tools:
        for fn in options.tools:
            fn_name = getattr(fn, "__name__", None)
            if fn_name:
                policies.append(policy.allow(fn_name, name=f"tel99_allow_{fn_name}"))
    policies.append(policy.allow("finish", name="tel99_allow_finish"))
    if options.allow_file_reads:
        policies.append(policy.allow("view_file", name="tel99_allow_view_file"))

    budget_cfg = None
    if options.max_tool_calls is not None or options.max_model_calls is not None:
        budget_cfg = types.BudgetConfig(
            max_tool_calls=options.max_tool_calls,
            max_model_calls=options.max_model_calls,
        )

    config_kwargs: dict[str, Any] = {
        "model": options.model,
        "base_url": options.base_url,
        "tools": list(options.tools),
        "policies": policies,
        "hooks": list(extra_hooks),
        "retry_config": types.RetryConfig(
            model_output_retry=types.ModelOutputRetryConfig(
                max_retries=options.model_output_max_retries
            )
        ),
        "compaction_config": types.CompactionConfig(
            token_threshold=options.compaction_token_threshold
        ),
    }
    if options.system_instructions is not None:
        config_kwargs["system_instructions"] = options.system_instructions
    if resolved_workspaces:
        config_kwargs["workspaces"] = resolved_workspaces
    if options.inline_skills:
        config_kwargs["inline_skills"] = list(options.inline_skills)
    if options.save_dir is not None:
        config_kwargs["save_dir"] = str(Path(options.save_dir).resolve())
    if options.app_data_dir is not None:
        config_kwargs["app_data_dir"] = str(Path(options.app_data_dir).resolve())
    if options.conversation_id is not None:
        config_kwargs["conversation_id"] = options.conversation_id
    if options.session_continuation_mode is not None:
        config_kwargs["session_continuation_mode"] = options.session_continuation_mode
    if budget_cfg is not None:
        config_kwargs["budget_config"] = budget_cfg

    cfg = LocalOpenAIAgentConfig(**config_kwargs).lightweight()
    cfg.capabilities = types.CapabilitiesConfig(
        enabled_tools=enabled_tools,
        agent_behavior=types.AgentBehavior.MINIMAL,
        enable_subagents=False,
        tool_output_truncation_config=types.ToolOutputTruncationConfig(
            max_tokens=options.tool_output_max_tokens
        ),
    )
    return cfg


class TEL99SDKAdapter:
    """Thin, bounded runner executing a prompt via google.antigravity with safe cleanup."""

    def __init__(self, options: TEL99SDKOptions):
        self.options = options

    async def run(self, prompt: str) -> TEL99RunOutcome:
        if not sdk_available():
            return TEL99RunOutcome(
                ok=False,
                response_text="",
                conversation_id=None,
                harness_pid=None,
                duration_seconds=0.0,
                stop_reason="SDK_UNAVAILABLE",
                usage={},
                error="google-antigravity SDK is not installed",
            )

        from google.antigravity import Agent, types
        from google.antigravity.hooks import hooks

        start = time.perf_counter()
        observed_tools: list[dict[str, Any]] = []

        @hooks.pre_tool_call_decide
        async def _audit_pre(data: types.ToolCall) -> types.HookResult:
            observed_tools.append(
                {
                    "name": str(data.name),
                    "step_id": data.step_id,
                    "args_keys": sorted(list((data.args or {}).keys())),
                }
            )
            return types.HookResult(allow=True)

        cfg = build_tel99_sdk_config(self.options, extra_hooks=[_audit_pre])
        conv_id: str | None = None
        harness_pid: int | None = None
        stop_reason = "UNSPECIFIED"
        text = ""
        usage_dict: dict[str, int | None] = {}
        err: str | None = None
        cleaned = False

        try:
            async def _exec() -> None:
                nonlocal conv_id, harness_pid, stop_reason, text, usage_dict
                async with Agent(cfg) as agent:
                    harness_proc = getattr(agent.conversation.connection, "_process", None)
                    harness_pid = getattr(harness_proc, "pid", None)
                    resp = await agent.chat(prompt)
                    text = await resp.text()
                    conv_id = agent.conversation_id
                    stop_reason = (
                        resp.stop_reason.value
                        if hasattr(resp.stop_reason, "value")
                        else str(resp.stop_reason)
                    )
                    u = agent.conversation.total_usage
                    usage_dict = {
                        "prompt_token_count": u.prompt_token_count,
                        "cached_content_token_count": u.cached_content_token_count,
                        "candidates_token_count": u.candidates_token_count,
                        "thoughts_token_count": u.thoughts_token_count,
                        "total_token_count": u.total_token_count,
                    }

            await asyncio.wait_for(_exec(), timeout=self.options.timeout_seconds)
        except asyncio.TimeoutError:
            err = f"TimeoutError after {self.options.timeout_seconds}s"
        except Exception as exc:
            err = repr(exc)
        finally:
            if harness_pid is not None:
                cleaned = _terminate_child_pid(harness_pid)

        return TEL99RunOutcome(
            ok=err is None,
            response_text=text,
            conversation_id=conv_id,
            harness_pid=harness_pid,
            duration_seconds=round(time.perf_counter() - start, 2),
            stop_reason=stop_reason,
            usage=usage_dict,
            tool_calls_observed=observed_tools,
            harness_cleaned_up=cleaned,
            error=err,
        )


class AntigravitySDKProvider:
    """Synchronous provider matching OllamaNativeProvider.complete() with safe fallback."""

    name = "antigravity-sdk-ollama"

    def __init__(
        self,
        *,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: int = 120,
        max_tokens: int = 768,
        fallback_to_ollama_native: bool = True,
        max_empty_retries: int = 1,
        options_overrides: dict[str, Any] | None = None,
    ):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.fallback_to_ollama_native = fallback_to_ollama_native
        self.max_empty_retries = max_empty_retries
        self.options_overrides = dict(options_overrides or {})
        self.last_metadata: dict[str, Any] = {}

    def _run_async(self, coro_factory: Callable[[], Any]) -> TEL99RunOutcome:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro_factory())
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro_factory())).result()

    def _fallback_complete(self, *, system: str, prompt: str, reason: str) -> str:
        native = OllamaNativeProvider(
            model=self.model,
            timeout=min(max(int(self.timeout), 10), 90),
            max_tokens=min(max(int(self.max_tokens), 64), 1024),
        )
        answer = native.complete(system=system, prompt=prompt)
        self.last_metadata = {
            "backend": "ollama-native-fallback",
            "fallback_used": True,
            "fallback_reason": reason,
            "native_metadata": native.last_metadata,
        }
        return answer

    def complete(self, *, system: str, prompt: str) -> str:
        self.last_metadata = {}
        if not sdk_available():
            if self.fallback_to_ollama_native:
                return self._fallback_complete(
                    system=system, prompt=prompt, reason="sdk_not_installed"
                )
            raise ProviderError("google-antigravity SDK is not installed")

        opts_kwargs = {
            "model": self.model,
            "base_url": self.base_url,
            "system_instructions": system,
            "timeout_seconds": float(self.timeout),
            "max_tool_calls": 4,
            "max_model_calls": 6,
            **self.options_overrides,
        }
        adapter = TEL99SDKAdapter(TEL99SDKOptions(**opts_kwargs))

        last_err: str | None = None
        for attempt in range(1, self.max_empty_retries + 2):
            try:
                with ide_coordination.local_inference_lease(
                    "antigravity-sdk",
                    model=self.model,
                    ttl_seconds=max(120, int(self.timeout) + 120),
                ):
                    outcome = self._run_async(lambda: adapter.run(prompt))
            except ide_coordination.LeaseConflict as exc:
                last_err = f"resource_lease_busy: {exc}"
                break
            if outcome.ok and outcome.response_text.strip():
                self.last_metadata = {
                    "backend": "antigravity-sdk",
                    "fallback_used": False,
                    "attempt": attempt,
                    "duration_seconds": outcome.duration_seconds,
                    "conversation_id": outcome.conversation_id,
                    "harness_pid": outcome.harness_pid,
                    "stop_reason": outcome.stop_reason,
                    "usage": outcome.usage,
                }
                return outcome.response_text.strip()
            last_err = outcome.error or "empty_response"

        if self.fallback_to_ollama_native:
            return self._fallback_complete(
                system=system, prompt=prompt, reason=last_err or "sdk_failed"
            )
        raise ProviderError(f"AntigravitySDKProvider failed: {last_err}")


def run_bounded_role_pipeline(
    *,
    analyst_fn: Callable[[], dict[str, Any]],
    developer_fn: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]],
    verifier_fn: Callable[[dict[str, Any]], dict[str, Any]],
    max_repairs: int = 1,
) -> dict[str, Any]:
    """Sequential bounded specialist pipeline (Analyst -> Developer -> Verifier) with repair loop.

    Avoids unbounded single-root multi-subagent CPU timeouts while guaranteeing
    independent verification and at most `max_repairs` bounded repair attempts.
    """
    if max_repairs < 0 or max_repairs > 2:
        raise ValueError("max_repairs must be within 0..2")
    analysis = analyst_fn()
    feedback: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_repairs + 2):
        candidate = developer_fn(analysis, feedback)
        verification = verifier_fn(candidate)
        attempts.append({
            "attempt": attempt,
            "candidate": candidate,
            "verification": verification,
        })
        if verification.get("ok"):
            return {
                "ok": True,
                "attempts": attempt,
                "analysis": analysis,
                "final_candidate": candidate,
                "final_verification": verification,
                "history": attempts,
            }
        feedback = verification.get("feedback") or {"kind": "candidate-test"}
    return {
        "ok": False,
        "attempts": len(attempts),
        "analysis": analysis,
        "final_candidate": attempts[-1]["candidate"] if attempts else None,
        "final_verification": attempts[-1]["verification"] if attempts else None,
        "history": attempts,
    }
