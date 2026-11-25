"""Deterministic local helper tools for TEL99 agents (pure stdlib, zero network, zero side effects).

Addresses verified local 7-9B failure modes diagnosed from Academy & benchmark traces:
1. Trailing example/main blocks causing token truncation SyntaxErrors.
2. Instant AST syntax + critical security static pre-checks (eval/exec/__import__/shell=True/0.0.0.0).
3. Canonical JSON extraction for structured JSON tasks.
4. Precise assertion failure line reporting for Smart Repair (without ever weakening tests).
5. Reusable strict type/bool/bounds/path/causal validators.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
import traceback
from typing import Any, Callable

FORBIDDEN_BUILTINS = frozenset({"eval", "exec", "compile", "__import__"})
_EXAMPLE_COMMENT_RE = re.compile(r"^#\s*(?:example|usage|test|demo)\b", re.IGNORECASE)
_MAIN_GUARD_RE = re.compile(r"^if\s+__name__\s*==\s*['\"]__main__['\"]\s*:")
_LEGIT_MAIN_SIGNALS = (
    "argparse",
    "ArgumentParser",
    "serve_forever",
    "make_server",
    "create_server",
    "run_server",
    "HTTPServer",
    "ThreadingHTTPServer",
    "unittest.main",
    "sys.argv",
    "SystemExit",
    "main(",
)
_WIN_RESERVED_DEVICE_NAMES = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
})
_SECRET_TOKEN_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9\-_]{16,}|"
    r"gsk_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z\-_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
_PROMPT_INJECTION_RE = re.compile(
    r"(?i)(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"
    r"disregard\s+system\s+prompt|reveal\s+(?:your\s+)?(?:system\s+prompt|api[_\s]?key|secrets?)|"
    r"override\s+security\s+(?:policy|guard)|bypass\s+(?:sandbox|guard|verification))"
)
_DANGEROUS_OS_CALLS = frozenset({"system", "popen"})
_DANGEROUS_PICKLE_CALLS = frozenset({"loads", "load"})


def _is_legitimate_main_block(tail_text: str) -> bool:
    """Return True when a trailing `if __name__ == '__main__':` block is a real CLI/server/test entrypoint."""
    return any(sig in tail_text for sig in _LEGIT_MAIN_SIGNALS)


def strip_trailing_example_blocks(code: str, *, preserve_main: bool = False) -> str:
    """Remove trailing top-level example/demo stubs that local models append after defs.

    Preserves legitimate `if __name__ == "__main__":` CLI, server, and `unittest.main()`
    entrypoints whenever the full file parses cleanly. Strips a trailing `__main__` block
    ONLY if it is a trivial print/assert demo stub or if it contains a truncation SyntaxError
    whose preceding prefix parses cleanly.
    """
    if not code or not code.strip():
        return code
    lines = code.splitlines()
    full_parses = True
    try:
        ast.parse(code)
    except SyntaxError:
        full_parses = False

    cut_idx: int | None = None
    has_def_before = False
    for idx, line in enumerate(lines):
        if line.startswith(("def ", "class ")):
            has_def_before = True
        elif has_def_before and _EXAMPLE_COMMENT_RE.match(line):
            cut_idx = idx
            break
        elif has_def_before and _MAIN_GUARD_RE.match(line):
            tail_text = "\n".join(lines[idx:])
            if full_parses and (preserve_main or _is_legitimate_main_block(tail_text)):
                continue
            cut_idx = idx
            break
    if cut_idx is None:
        return code
    prefix = "\n".join(lines[:cut_idx]).rstrip()
    if not prefix:
        return code
    try:
        ast.parse(prefix)
        return prefix + "\n"
    except SyntaxError:
        return code


def extract_clean_json(raw: str) -> str:
    """Deterministically extract a valid JSON object/array from markdown-fenced or prose output."""
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except ValueError:
            text = candidate
    try:
        json.loads(text)
        return text
    except ValueError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        sub = text[start : end + 1]
        try:
            json.loads(sub)
            return sub
        except ValueError:
            pass
    return text


def static_security_and_syntax_precheck(output: str, *, kind: str = "python") -> dict[str, Any]:
    """Fast (<2ms) deterministic self-check before formal verification."""
    if kind == "json":
        cleaned = extract_clean_json(output)
        try:
            parsed = json.loads(cleaned)
        except ValueError as exc:
            return {
                "ok": False,
                "cleaned": cleaned,
                "syntax_ok": False,
                "security_ok": True,
                "issues": [f"Invalid JSON: {exc}"],
            }
        if not isinstance(parsed, dict):
            return {
                "ok": False,
                "cleaned": cleaned,
                "syntax_ok": True,
                "security_ok": True,
                "issues": [f"Expected top-level JSON object, got {type(parsed).__name__}"],
            }
        return {"ok": True, "cleaned": cleaned, "syntax_ok": True, "security_ok": True, "issues": []}

    cleaned = strip_trailing_example_blocks(output)
    try:
        tree = ast.parse(cleaned)
    except SyntaxError as exc:
        return {
            "ok": False,
            "cleaned": cleaned,
            "syntax_ok": False,
            "security_ok": True,
            "issues": [f"SyntaxError line {exc.lineno}: {exc.msg}"],
        }
    sec_issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                sec_issues.append(f"forbidden call {node.func.id}()")
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    sec_issues.append("forbidden subprocess shell=True")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == "0.0.0.0":
            sec_issues.append("forbidden non-loopback host 0.0.0.0")
    return {
        "ok": not sec_issues,
        "cleaned": cleaned,
        "syntax_ok": True,
        "security_ok": not sec_issues,
        "issues": sec_issues,
    }


def format_precise_failure_feedback(exc: Exception, test_code: str = "") -> str:
    """Provide actionable failure context (exact failing assertion or line) without revealing hidden tests."""
    etype = type(exc).__name__
    msg = str(exc).strip()
    tb = traceback.extract_tb(exc.__traceback__)
    if etype == "AssertionError" and not msg and test_code:
        test_lines = test_code.splitlines()
        for frame in reversed(tb):
            if frame.filename in ("<held-out-test>", "<test>") and frame.lineno and 1 <= frame.lineno <= len(test_lines):
                failing_expr = test_lines[frame.lineno - 1].strip()
                # Describe failure category cleanly (assertion check failed)
                return f"AssertionError at test check #{frame.lineno}: `{failing_expr[:140]}`"
    if tb:
        last = tb[-1]
        if last.filename == "<candidate>":
            return f"{etype}: {msg} (candidate line {last.lineno})"[:260]
    return f"{etype}: {msg}"[:260]


# Reusable strict deterministic validators (unit-tested, stdlib-only)
def require_int(value: Any, *, name: str = "value", min_val: int | None = None, max_val: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be int (not bool)")
    if min_val is not None and value < min_val:
        raise ValueError(f"{name} < {min_val}")
    if max_val is not None and value > max_val:
        raise ValueError(f"{name} > {max_val}")
    return value


def require_number(
    value: Any,
    *,
    name: str = "value",
    min_val: float | None = None,
    max_val: float | None = None,
    strict_gt: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be int/float (not bool)")
    if min_val is not None and value < min_val:
        raise ValueError(f"{name} < {min_val}")
    if strict_gt is not None and value <= strict_gt:
        raise ValueError(f"{name} <= {strict_gt}")
    if max_val is not None and value > max_val:
        raise ValueError(f"{name} > {max_val}")
    return float(value)


def safe_subpath(
    root_dir: str | Path,
    rel_path: str,
    *,
    blocked_top_dirs: frozenset[str] | set[str] | None = None,
) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip() or "\x00" in rel_path:
        raise ValueError("rel_path must be non-empty string without null bytes")
    norm = rel_path.replace("\\", "/")
    if norm.startswith(("/", "~")) or ":" in norm:
        raise ValueError("path traversal or absolute path forbidden")
    parts = norm.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("path traversal or empty path segment forbidden")
    for part in parts:
        if part != part.strip() or part.endswith("."):
            raise ValueError(f"invalid Windows path segment: {part!r}")
        stem = part.split(".", 1)[0].lower()
        if stem in _WIN_RESERVED_DEVICE_NAMES:
            raise ValueError(f"Windows reserved device name forbidden: {part!r}")
    if blocked_top_dirs and parts[0].lower() in {d.lower() for d in blocked_top_dirs}:
        raise ValueError(f"protected top-level path forbidden: {parts[0]!r}")

    root = Path(root_dir).resolve()
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink() or os.path.islink(cursor):
            raise ValueError(f"symlink/junction escape forbidden: {rel_path!r}")
    target = cursor.resolve()
    if target != root and root not in target.parents:
        raise ValueError("resolved path escapes root_dir")
    return target


def causal_slice(values: list[float], idx: int, window: int) -> list[float]:
    require_int(idx, name="idx", min_val=0)
    require_int(window, name="window", min_val=1)
    return values[max(0, idx - window + 1) : idx + 1]


def detect_prompt_injection(text: str) -> dict[str, Any]:
    """Deterministic prompt-injection detector independent of LLM compliance."""
    raw = str(text or "")
    matches = [m.group(0)[:80] for m in _PROMPT_INJECTION_RE.finditer(raw)]
    return {"safe": not matches, "matches": matches}


def detect_secret_leak(text: str) -> dict[str, Any]:
    """Deterministic secret-token leak detector (never echoes matched secrets)."""
    raw = str(text or "")
    hits = _SECRET_TOKEN_RE.findall(raw)
    return {"safe": not hits, "count": len(hits)}


def check_cloud_escalation_policy(
    *,
    confidential: bool,
    allow_cloud: bool,
    prompt_text: str = "",
) -> dict[str, Any]:
    """Deterministic guard blocking unauthorized cloud escalations or secret egress."""
    if not allow_cloud:
        return {"allowed": False, "reason": "cloud_disabled_local_only"}
    if confidential:
        return {"allowed": False, "reason": "confidential_local_only"}
    if not detect_secret_leak(prompt_text)["safe"]:
        return {"allowed": False, "reason": "secret_detected_in_outbound_payload"}
    return {"allowed": True, "reason": "ok"}


def deterministic_security_gate(
    output: str,
    *,
    kind: str = "python",
    allowed_root: str | Path | None = None,
    target_rel_path: str | None = None,
    check_secrets: bool = True,
    check_injection: bool = False,
) -> dict[str, Any]:
    """Comprehensive deterministic security gate (independent of model goodwill).

    Checks syntax, forbidden execution primitives, non-loopback binds, unsafe deserialization,
    secret leakage, optional prompt injection markers, and path confinement within allowed_root.
    """
    issues: list[str] = []
    base = static_security_and_syntax_precheck(output, kind=kind)
    cleaned = base["cleaned"]
    if not base["syntax_ok"]:
        issues.extend(base["issues"])
    if not base["security_ok"]:
        issues.extend(base["issues"])

    if check_secrets and not detect_secret_leak(cleaned)["safe"]:
        issues.append("secret token pattern detected in output")
    if check_injection and not detect_prompt_injection(cleaned)["safe"]:
        issues.append("prompt injection override pattern detected")

    if allowed_root is not None and target_rel_path is not None:
        try:
            safe_subpath(allowed_root, target_rel_path)
        except ValueError as exc:
            issues.append(f"out_of_scope_path: {exc}")

    if kind == "python" and base["syntax_ok"]:
        tree = ast.parse(cleaned)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                if owner == "os" and attr in _DANGEROUS_OS_CALLS:
                    issues.append(f"forbidden os.{attr}() call")
                if owner == "pickle" and attr in _DANGEROUS_PICKLE_CALLS:
                    issues.append(f"forbidden unsafe pickle.{attr}() call")
                if owner == "yaml" and attr == "load":
                    has_safe_loader = any(
                        kw.arg == "Loader" and isinstance(kw.value, ast.Attribute) and kw.value.attr == "SafeLoader"
                        for kw in node.keywords
                    )
                    if not has_safe_loader:
                        issues.append("forbidden unsafe yaml.load() without SafeLoader")
                if owner == "hmac" and attr == "new" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        issues.append("hmac.new() key literal must be bytes, not str")

    dedup_issues = list(dict.fromkeys(issues))
    return {
        "ok": not dedup_issues,
        "syntax_ok": base["syntax_ok"],
        "security_ok": not [i for i in dedup_issues if not i.startswith("SyntaxError") and not i.startswith("Invalid JSON")],
        "cleaned": cleaned,
        "issues": dedup_issues,
    }


@contextmanager
def file_lock(lock_path: Path | str, *, timeout_s: float = 15.0, poll_s: float = 0.05):
    """Cross-platform retrying advisory file lock (Windows msvcrt / POSIX fcntl)."""
    lp = Path(lock_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.1, float(timeout_s))
    fh = lp.open("a+b")
    locked = False
    try:
        while True:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Could not acquire lock {lp} within {timeout_s}s")
                time.sleep(poll_s)
        yield
    finally:
        if locked:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def write_json_atomic_locked(path: Path | str, payload: dict[str, Any], *, timeout_s: float = 15.0) -> Path:
    """Write JSON atomically under a retrying file lock with a PID-scoped temp file."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lock_path = dest.parent / f"{dest.name}.lock"
    tmp = dest.parent / f"{dest.name}.{os.getpid()}.tmp"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with file_lock(lock_path, timeout_s=timeout_s):
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, dest)
    return dest


def locked_json_update(
    path: Path | str,
    updater: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """Read-modify-write a JSON object safely under an exclusive lock (prevents concurrent clobbering)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lock_path = dest.parent / f"{dest.name}.lock"
    tmp = dest.parent / f"{dest.name}.{os.getpid()}.tmp"
    with file_lock(lock_path, timeout_s=timeout_s):
        current: dict[str, Any] = {}
        if dest.is_file():
            try:
                loaded = json.loads(dest.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current = loaded
            except (OSError, ValueError):
                current = {}
        updated = updater(current)
        tmp.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, dest)
    return updated
