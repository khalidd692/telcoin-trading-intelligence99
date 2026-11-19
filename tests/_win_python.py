"""Robust Python interpreter resolution for Windows.

The Microsoft Store installs ``python.exe`` / ``python3.exe`` stubs under
``%LOCALAPPDATA%\\Microsoft\\WindowsApps`` that open a Store dialog and fail
with a non-zero exit code when invoked from a subprocess.  A version-suffixed
alias such as ``python3.12.exe`` points at the real interpreter.  This module
resolves a working interpreter without mutating the global PC configuration.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def python_interpreter() -> str:
    """Return the path to a Python interpreter that works from subprocess.

    Prefers ``sys.executable`` when it actually works; otherwise falls back to
    version-suffixed aliases (e.g. ``python3.12``) that bypass the Windows Store
    stub.  Never modifies the system PATH or installs anything.
    """

    def _is_store_stub(path: str | None) -> bool:
        if not path:
            return False
        return 'WindowsApps' in path and 'PythonSoftwareFoundation' in path

    def _works(path: str | None) -> bool:
        if not path or _is_store_stub(path):
            return False
        try:
            result = subprocess.run(
                [path, '-c', 'import sys; print(sys.executable)'],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError, ValueError):
            return False

    exe = sys.executable
    if _works(exe):
        return exe

    for candidate in ('python3.13', 'python3.12', 'python3.11', 'python3', 'python'):
        found = shutil.which(candidate)
        if found and _works(found):
            return found

    return exe
