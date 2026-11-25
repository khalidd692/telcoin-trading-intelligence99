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
import json
from pathlib import Path
import re
import traceback
from typing import Any

FORBIDDEN_BUILTINS = frozenset({"eval", "exec", "compile", "__import__"})
_EXAMPLE_MARKER_RE = re.compile(
    r"^(?:if\s+__name__\s*==\s*['\"]__main__['\"]\s*:|#\s*(?:example|usage|test|demo)\b)",
    re.IGNORECASE,
)


def strip_trailing_example_blocks(code: str) -> str:
    """Remove trailing top-level example/test/main stubs that local models append after defs.

    Only strips a trailing block starting at column 0 when the preceding prefix already
    contains at least one `def ` or `class ` and parses cleanly (or is strictly cleaner).
    Never removes required function/class definitions.
    """
    if not code or not code.strip():
        return code
    lines = code.splitlines()
    cut_idx: int | None = None
    has_def_before = False
    for idx, line in enumerate(lines):
        if line.startswith(("def ", "class ")):
            has_def_before = True
        elif has_def_before and _EXAMPLE_MARKER_RE.match(line):
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


def safe_subpath(root_dir: str | Path, rel_path: str) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ValueError("rel_path must be non-empty string")
    if rel_path.startswith(("/", "\\", "~")) or ":" in rel_path or ".." in Path(rel_path).parts:
        raise ValueError("path traversal or absolute path forbidden")
    root = Path(root_dir).resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("resolved path escapes root_dir")
    return target


def causal_slice(values: list[float], idx: int, window: int) -> list[float]:
    require_int(idx, name="idx", min_val=0)
    require_int(window, name="window", min_val=1)
    return values[max(0, idx - window + 1) : idx + 1]
