"""Generate one approved Python function and verify its behavior in local Docker."""

from __future__ import annotations

import ast
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_codex import Blocked, git_committed_blob
from scripts.agents.native import sandbox
from scripts.agents.native.mission import MissionError, valid_artifact_name
from scripts.agents.native.provider import OpenAICompatibleProvider, ProviderError

FIELDS = {
    "id", "owner", "project", "specialist", "priority", "dependencies", "objective",
    "base_sha", "path", "function", "test", "sandbox_image", "model", "port",
}
VERIFIER = "tel99-local-docker-code-v1"
PROVIDER = "loopback-code"


def validate_scope(mission):
    path = mission.get("path")
    port = mission.get("port")
    if (set(mission) != FIELDS or mission["owner"] != "local"
            or mission["project"] != "tel99" or mission["specialist"] != "tel99-dev"
            or not isinstance(mission["id"], str)
            or not re.fullmatch(r"[a-zA-Z0-9-]{1,48}", mission["id"])
            or not re.fullmatch(r"[0-9a-f]{40}", str(mission["base_sha"]))
            or not isinstance(path, str) or not path.endswith(".py") or len(path) > 200
            or not all(valid_artifact_name(part) for part in path.split("/"))
            or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}", str(mission["function"]))
            or not isinstance(mission["test"], str) or not 1 <= len(mission["test"]) <= 8000
            or not sandbox.valid_image(mission["sandbox_image"])
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", str(mission["model"]))
            or type(port) is not int or not 1024 <= port <= 65535):
        raise ValueError("invalid local code scope")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source(mission):
    data = git_committed_blob(ROOT, mission["base_sha"], mission["path"])
    if len(data) > 100_000:
        raise ValueError("source file exceeds the local code limit")
    return data.decode("utf-8")


def _function(source, name):
    matches = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1 or matches[0].decorator_list:
        raise ValueError("the approved function must be a unique, undecorated top-level function")
    return matches[0]


def _physical_lines(source):
    return io.StringIO(source, newline="").readlines()


def _function_source(source, node):
    return "".join(_physical_lines(source)[node.lineno - 1:node.end_lineno])


def replace_function(source, name, reply):
    original = _function(source, name)
    code = reply.strip()
    if re.search(r"^```", code, re.MULTILINE):
        blocks = re.findall(
            r"^```(?:python|py)?[ \t]*\r?\n(.*?)\r?\n^```[ \t]*\r?$",
            code, re.MULTILINE | re.DOTALL,
        )
        if len(blocks) != 1 or len(re.findall(r"^```", code, re.MULTILINE)) != 2:
            raise ValueError("candidate must provide exactly one Python code block")
        code = blocks[0]
    body = ast.parse(code).body
    if (len(body) != 1 or not isinstance(body[0], ast.FunctionDef) or body[0].name != name
            or body[0].decorator_list or ast.dump(body[0].args) != ast.dump(original.args)
            or (ast.dump(body[0].returns) if body[0].returns else None)
            != (ast.dump(original.returns) if original.returns else None)
            or getattr(body[0], "type_params", ()) or getattr(original, "type_params", ())
            or ast.dump(body[0]) == ast.dump(original)):
        raise ValueError("candidate must change one function with its existing signature")
    lines = _physical_lines(source)
    replacement = _function_source(code, body[0])
    if not replacement.endswith(("\r", "\n")):
        replacement += "\n"
    candidate = "".join(lines[:original.lineno - 1]) + replacement + "".join(lines[original.end_lineno:])
    compile(candidate, "<candidate>", "exec")
    return candidate


def execute(mission):
    validate_scope(mission)
    sandbox.require_local_image(mission["sandbox_image"])
    source = _source(mission)
    function = _function_source(source, _function(source, mission["function"]))
    if len(function) > 4000:
        raise ValueError("approved function exceeds the model input limit")
    model = mission["model"]
    provider = OpenAICompatibleProvider(
        model=model, included_local_model=model, base_url=f"http://127.0.0.1:{mission['port']}/v1",
        timeout=80, max_tokens=384,
    )
    reply = provider.complete(
        system=(
            "You are tel99-dev. Return only the updated Python function with its existing signature, "
            "including annotations. Start with def. Do not add or repeat module-level imports. "
            "Use only Python's standard library. You have no tools. "
            "Do not output other code, claims about tests, or deployment and trading actions."
        ),
        prompt=f"Task: {mission['objective']}\n\nExisting function:\n{function}",
    )
    if not isinstance(reply, str) or not 1 <= len(reply.encode("utf-8")) <= 16_000:
        raise ValueError("missing or oversized model reply")
    return {"artifact": reply, "sha256": _sha(reply), "specialist_id": mission["specialist"],
            "provider": PROVIDER, "model": model}


def _behavior(image, source, test):
    # The approval pins the test. It invokes /work/program.py as a child process.
    runner = (
        "try:\n"
        f"    exec(compile({test!r}, '<independent-test>', 'exec'))\n"
        "except AssertionError:\n"
        "    print('TEL99_TEST_FAIL')\n"
        "    raise SystemExit(1)\n"
        "print('TEL99_TEST_PASS')\n"
    )
    with tempfile.TemporaryDirectory(prefix="tel99-code-test-") as directory:
        path = Path(directory) / "program.py"
        path.write_bytes(source.encode("utf-8"))
        result = sandbox._run_container(image, path, 20, runner=runner)
    if (result.returncode, result.stdout) == (0, b"TEL99_TEST_PASS\n"):
        return True
    if (result.returncode, result.stdout) == (1, b"TEL99_TEST_FAIL\n"):
        return False
    raise MissionError(f"no independent test verdict from Docker (exit {result.returncode})")


def _publish(directory, path, candidate, diff):
    if directory.resolve() != directory:
        raise ValueError("redirected proof directory")
    if directory.exists():
        for name, content in ((path, candidate), ("change.diff", diff)):
            target = directory / name
            if target.resolve() != target or target.read_bytes() != content.encode("utf-8"):
                raise ValueError("existing proof does not match the verified source")
        return
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as temp:
        bundle = Path(temp) / "bundle"
        target = bundle / path
        target.parent.mkdir(parents=True)
        target.write_bytes(candidate.encode("utf-8"))
        (bundle / "change.diff").write_bytes(diff.encode("utf-8"))
        bundle.rename(directory)


def verify(mission, result, root):
    validate_scope(mission)
    reply = result.get("artifact")
    if (not isinstance(reply, str) or not 1 <= len(reply.encode("utf-8")) <= 16_000
            or result.get("sha256") != _sha(reply) or result.get("specialist_id") != "tel99-dev"
            or result.get("provider") != PROVIDER or result.get("model") != mission["model"]):
        return {"ok": False, "checks": [{"name": "bounded-model-receipt", "ok": False}]}
    report = {
        "verifier": VERIFIER, "artifact_sha256": _sha(reply), "ok": False,
        "base_sha": mission["base_sha"], "path": mission["path"], "function": mission["function"],
        "test_sha256": _sha(mission["test"]), "sandbox_image": mission["sandbox_image"],
        "checks": [{"name": "bounded-model-receipt", "ok": True}],
    }
    source = _source(mission)
    try:
        candidate = replace_function(source, mission["function"], reply)
    except (SyntaxError, ValueError):
        report["checks"].append({"name": "approved-function-diff", "ok": False})
        return report
    report["checks"].append({"name": "approved-function-diff", "ok": True})
    sandbox.require_local_image(mission["sandbox_image"])
    before = _behavior(mission["sandbox_image"], source, mission["test"])
    after = _behavior(mission["sandbox_image"], candidate, mission["test"])
    report["checks"].extend([
        {"name": "baseline-fails", "ok": not before, "exit_code": 0 if before else 1},
        {"name": "candidate-passes", "ok": after, "exit_code": 0 if after else 1},
    ])
    if not before and after:
        path = mission["path"]
        changes = difflib.unified_diff(
            _physical_lines(source), _physical_lines(candidate),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        )
        diff = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                       for line in changes)
        _publish(root / "verified-code" / mission["id"], path, candidate, diff)
        report.update(ok=True, base_file_sha256=_sha(source), candidate_sha256=_sha(candidate),
                      diff_sha256=_sha(diff))
    return report


def main():
    try:
        raw = sys.stdin.buffer.read(100_001)
        if len(raw) > 100_000:
            raise ValueError("worker input exceeds the limit")
        print(json.dumps(execute(json.loads(raw))), flush=True)
        return 0
    except (Blocked, MissionError, OSError, ProviderError, SyntaxError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), flush=True)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
