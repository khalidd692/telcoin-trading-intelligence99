#!/usr/bin/env python3
"""TEL99 PreToolUse guard.

Reads a HookEvent JSON document on stdin and decides whether the pending tool
call may proceed.

Contract (OpenHands SDK 1.62.0): exit code 2 BLOCKS the action before it runs;
exit code 0 allows it. Exit code 1 does NOT block, so this guard never uses it.

Only ``terminal`` commands are policed. Everything else is allowed so the guard
cannot accidentally freeze the agent.

Design: the command is split on shell separators (``;``, ``&&``, ``||``, ``|``,
newlines) and each segment is judged by its HEAD word, not by a substring
search. A substring approach wrongly blocks read-only commands such as
``find deploy -type f`` or ``grep -n deploy-pages file``; head analysis does not.

This is a defence-in-depth heuristic. The primary controls remain the per-agent
``tools=["terminal"]`` allowlist, ``sub_agent_scope`` and the confirmation
policy.
"""

from __future__ import annotations

import json
import re
import sys

# Commands that mutate state and must never run in a read-only pilot. Matched
# against the head word of a segment (and the effective head after xargs).
MUTATING_HEADS = {
    "rm", "mv", "cp", "dd", "mkfs", "truncate", "tee", "chmod", "chown", "chgrp",
    "kill", "pkill", "killall", "sudo", "su", "doas", "touch", "mkdir", "rmdir",
    "ln", "install", "mount", "umount", "systemctl", "service", "shutdown",
    "reboot", "iptables", "crontab", "at", "docker", "kubectl", "terraform",
    "ansible", "scp", "rsync", "ssh", "brew", "snap", "apt", "apt-get", "yum",
    "dnf", "apk", "wrangler", "git-lfs",
}

# Prefix words that wrap another command; the guard looks past them.
WRAPPERS = {"env", "command", "builtin", "nohup", "time", "nice", "stdbuf",
            "ionice", "setsid", "timeout", "xargs"}

# Shells that can run a nested command via -c.
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "csh", "tcsh"}

# Package / dependency installation, matched inside a segment.
INSTALL_PATTERNS = [
    r"\bpip3?\s+install\b", r"\bnpm\s+(i|install|ci|add)\b",
    r"\byarn\s+(add|install)\b", r"\bpnpm\s+(add|install)\b",
    r"\bpoetry\s+(add|install)\b", r"\buv\s+(pip\s+install|add)\b",
    r"\bconda\s+install\b", r"\bgem\s+install\b", r"\bcargo\s+install\b",
    r"\bgo\s+install\b", r"\bapt(-get)?\s+install\b",
]

# Git subcommands that write to the repository or its refs.
GIT_MUTATING = {
    "commit", "push", "checkout", "switch", "reset", "clean", "add", "merge",
    "rebase", "fetch", "pull", "tag", "stash", "cherry-pick", "revert", "init",
    "remote", "apply", "am", "config", "gc", "prune", "worktree", "submodule",
}

# Scripted file writes (Python, Node, sed in place).
WRITE_PATTERNS = [
    r"open\([^)]*,\s*['\"][wax]",          # open(path, 'w'|'a'|'x'|...)
    r"\.write_text\(", r"\.write_bytes\(",
    r"Path\([^)]*\)\.(write|touch|unlink|mkdir|rename|replace)\b",
    r"\bshutil\.(copy|copyfile|move|rmtree|make_archive)\b",
    r"\bos\.(remove|unlink|rename|replace|mkdir|makedirs|rmdir|removedirs|"
    r"chmod|chown|symlink|link|truncate)\b",
    r"\.unlink\(",
    r"\bfs\.(write|rm|unlink|mkdir|rename|appendFile)\w*\(",
    r"\bwriteFileSync?\(",
    r"\bsed\b[^\n]*-i",                     # sed -i (in-place edit)
    r"\bperl\b[^\n]*-i",
]

# Network mutations and downloads.
NETWORK_PATTERNS = [
    r"\bcurl\b[^\n]*(-X\s*(POST|PUT|DELETE|PATCH)|--data|-d\s|--upload-file|-F\s)",
    r"\bwget\b",
    r"\bgh\s+pr\s+create\b",
    r"\bgh\s+release\s+create\b",
    r"\bgh\s+api\b[^\n]*-X\s*(POST|PUT|PATCH|DELETE)",
]

# No real and no simulated order.
TRADING_PATTERN = (
    r"\b(kraken|binance|coinbase|mexc|kucoin|tel99)\b[^\n]*"
    r"\b(order|buy|sell|trade)\b"
)
PAPER_PATTERN = r"\bpaper\s+(order|trade|account)\b"


def split_segments(command: str) -> list[str]:
    """Split a shell command on separators, keeping quoted parts intact."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            current.append(ch)
            i += 1
            continue
        if command.startswith("&&", i) or command.startswith("||", i):
            segments.append("".join(current))
            current = []
            i += 2
            continue
        if ch in ";|\n":
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return [s.strip() for s in segments if s.strip()]


def head_words(segment: str) -> list[str]:
    """Return the effective command tokens, skipping assignments and wrappers."""
    try:
        tokens = segment.split()
    except ValueError:
        return []
    out: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            i += 1
            continue
        base = token.rsplit("/", 1)[-1]
        if base in WRAPPERS:
            i += 1
            continue
        out = tokens[i:]
        break
    return out


def _strip_quotes(text: str) -> str:
    return text.strip().strip("'\"")


def decide(event: dict) -> tuple[int, str]:
    """Return (exit_code, reason). 2 blocks, 0 allows."""
    tool = event.get("tool_name") or ""
    tool_input = event.get("tool_input") or {}
    command = ""
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd") or ""
    if tool != "terminal" or not command:
        return 0, ""

    segments = split_segments(command)
    # Expand nested shell invocations (bash -c '...') one level deep.
    for segment in list(segments):
        words = head_words(segment)
        if words and words[0].rsplit("/", 1)[-1] in SHELLS and "-c" in words[1:3]:
            idx = words.index("-c")
            if idx + 1 < len(words):
                segments.extend(split_segments(_strip_quotes(" ".join(words[idx + 1:]))))

    for segment in segments:
        words = head_words(segment)
        if not words:
            continue
        base = words[0].rsplit("/", 1)[-1]

        if base in MUTATING_HEADS or base.startswith("deploy"):
            return 2, f"guard: BLOCKED (mutating command {base!r})"

        if base == "git":
            sub = next((w for w in words[1:] if not w.startswith("-")), "")
            if sub in GIT_MUTATING or (sub == "branch" and
                                       re.search(r"-[dD]\b", segment)):
                return 2, f"guard: BLOCKED (git {sub or 'mutating'})"

        for pattern in INSTALL_PATTERNS + WRITE_PATTERNS + NETWORK_PATTERNS:
            if re.search(pattern, segment, re.I):
                return 2, f"guard: BLOCKED (pattern {pattern!r})"

        if re.search(TRADING_PATTERN, segment, re.I) or \
                re.search(PAPER_PATTERN, segment, re.I):
            return 2, "guard: BLOCKED (trading order)"

        if has_write_redirection(segment):
            return 2, "guard: BLOCKED (output redirection to a file)"

    return 0, ""


def has_write_redirection(segment: str) -> bool:
    """True if the segment redirects output to a real file.

    Allowed: ``>/dev/null`` and ``2>&1`` style descriptor duplication.
    """
    for match in re.finditer(r">>?", segment):
        rest = segment[match.end():]
        if match.group() == ">" and rest.startswith("&"):
            continue
        stripped = rest.lstrip()
        if stripped.startswith("&") or re.match(r"^/dev/null(\b|$)", stripped):
            continue
        return True
    return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.stderr.write("guard: unparseable event, allowing\n")
        return 0
    code, reason = decide(event)
    if code != 0:
        sys.stderr.write(reason + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
