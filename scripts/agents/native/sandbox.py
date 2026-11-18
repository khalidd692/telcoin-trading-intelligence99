"""Run a selected Python deliverable in a local, isolated Docker container."""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import tempfile
import uuid

from .mission import Check, MissionError, valid_artifact_name

_IMAGE = re.compile(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}")
_OUTPUT_LIMIT = 4096
_CAPTURE = """\
import subprocess, sys
with subprocess.Popen([sys.executable, "-I", "-B", "/work/program.py"],
                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
    output = process.stdout.read(4097)
    if len(output) > 4096:
        process.kill()
        sys.exit(1)
    sys.stdout.buffer.write(output)
    sys.exit(0 if process.wait() == 0 else 1)
"""


def _run_container(image: str, program: pathlib.Path, timeout: int):
    name = "tel99-native-" + uuid.uuid4().hex
    host = ("npipe:////./pipe/docker_engine" if os.name == "nt"
            else "unix:///var/run/docker.sock")
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
           if key in os.environ}
    with tempfile.TemporaryDirectory(prefix="tel99-sandbox-") as tmp:
        root = pathlib.Path(tmp)
        config = root / "config"
        config.mkdir()
        source = root / "program.py"
        source.write_bytes(program.read_bytes())
        root.chmod(0o755)
        source.chmod(0o644)
        if "," in str(source):
            raise MissionError("sandbox staging path contains a comma")
        docker = ["docker", "--config", str(config), "--host", host]
        command = [*docker, "run", "--name", name, "--rm", "--pull", "never",
                   "--network", "none", "--read-only", "--log-driver", "none",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--user", "65534:65534", "--pids-limit", "32",
                   "--memory", "256m", "--cpus", "1",
                   "--mount", f"type=bind,source={source},target=/work/program.py,readonly",
                   "--entrypoint", "python", image, "-I", "-B", "-c", _CAPTURE]
        try:
            return subprocess.run(command, env=env, capture_output=True, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            # Killing the Docker client alone does not guarantee the container stopped.
            subprocess.run([*docker, "rm", "-f", name], env=env, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            raise


class ScriptCheck(Check):
    """Check the program's observed exit status and exact output outside the sandbox."""

    def __init__(self, image: str, script: str, expected_stdout: str):
        if not _IMAGE.fullmatch(image):
            raise MissionError("sandbox image must be pinned by a sha256 digest")
        if not valid_artifact_name(script) or not script.endswith(".py"):
            raise MissionError("sandbox script must be a Python artifact")
        encoded = (expected_stdout + "\n").encode("utf-8")
        if len(encoded) > _OUTPUT_LIMIT:
            raise MissionError("expected sandbox output exceeds 4096 bytes")
        super().__init__(name="sandboxed-script", command=["python", script])
        self.image, self.script, self.expected_stdout = image, script, encoded
        self.fingerprint = hashlib.sha256(
            f"{image}\n{script}\n".encode("utf-8") + encoded).hexdigest()

    def run(self, cwd: pathlib.Path, timeout: int = 60) -> dict:
        script = cwd / self.script
        evidence = {"name": self.name, "sandbox_fingerprint": self.fingerprint}
        try:
            if script.is_symlink() or not script.is_file():
                raise MissionError("missing sandbox script")
            result = _run_container(self.image, script, timeout)
        except (MissionError, OSError, subprocess.TimeoutExpired) as exc:
            return {**evidence, "ok": False, "exit": None,
                    "detail": f"sandbox execution unavailable ({type(exc).__name__})"}
        ok = result.returncode == 0 and result.stdout == self.expected_stdout
        return {**evidence, "ok": ok, "exit": result.returncode,
                "detail": "" if ok else "sandbox exit or stdout differs from expectation"}
