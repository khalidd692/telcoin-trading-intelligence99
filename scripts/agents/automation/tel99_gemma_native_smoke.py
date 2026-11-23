#!/usr/bin/env python3
"""TEL99: Gemma via Ollama native API, verified by the existing Docker code verifier.

One approved historical task, with a fresh proof directory. No Git changes,
no automatic pull requests, no network for Docker, and no trading actions.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "gemma4:e4b-tel99-8k"
MODEL_ALIAS = "gemma4-e4b-tel99-8k"
REGISTRY = "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
REGISTRY_SHA = "dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9"
TASK = "qwen-repair-metadata-shape-20261123"


def save_json(path: Path, item):
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def ollama_complete(system: str, prompt: str):
    payload = {
        "model": MODEL,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "0s",
        "options": {"num_ctx": 8192, "num_predict": 1024, "temperature": 0},
    }
    request = Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:
        if response.status != 200:
            raise RuntimeError(f"Ollama HTTP {response.status}")
        raw = response.read(512_001)
    if len(raw) > 512_000:
        raise RuntimeError("Ollama response exceeded 512 KB")
    obj = json.loads(raw)
    answer = obj.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Ollama did not return usable code")
    return answer.strip(), {
        "eval_count": obj.get("eval_count"),
        "total_duration": obj.get("total_duration"),
    }


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path.cwd()).resolve()
    if not (root / "scripts/agents/automation/local_codegen.py").is_file():
        raise RuntimeError("Provide the existing TEL99 worktree path")

    # TEL99 includes legacy imports that require these repository paths.
    for path in (root, root / "scripts/agents", root / "scripts/agents/automation"):
        sys.path.insert(0, str(path))
    from scripts.agents.automation import local_codegen
    from scripts.agents.automation.autonomy_runtime import fingerprint
    from scripts.agents.native.sandbox import require_local_image

    raw = (root / REGISTRY).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA:
        raise RuntimeError("Historical task registry SHA-256 mismatch: refused")
    registry = json.loads(raw)
    original = next(x for x in registry["missions"] if x["id"] == TASK)
    if registry["approvals"].get(TASK) != fingerprint(original):
        raise RuntimeError("Historical task approval mismatch: refused")

    mission = copy.deepcopy(original)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    mission["id"] = "gemma-smoke-" + stamp[:15]
    mission["model"] = MODEL_ALIAS  # This scoped validator disallows ':' in model names.
    mission["port"] = 11434
    local_codegen.validate_scope(mission)

    evidence = Path.home() / "Desktop" / ("TEL99_GEMMA_PREUVES_" + stamp)
    evidence.mkdir(parents=True, exist_ok=False)
    save_json(evidence / "contract.json", {
        "mission": mission,
        "origin_sha256": REGISTRY_SHA,
        "actual_ollama_model": MODEL,
        "transport": "ollama-native-api-generate",
    })
    print("Mission:", TASK, "=>", mission["function"], flush=True)
    print("Preuves:", evidence, flush=True)
    print("Verification de l'image Docker epinglee (aucun telechargement)...", flush=True)
    require_local_image(mission["sandbox_image"])

    source = local_codegen._source(mission)
    function = local_codegen._function_source(
        source, local_codegen._function(source, mission["function"])
    )
    if len(function) > 4000:
        raise RuntimeError("Approved function too long")

    system = (
        "You are tel99-dev, a Python maintenance agent. Return ONLY the complete "
        "updated Python function with EXACT existing signature and annotations. "
        "Start with def. No markdown, explanations or imports. "
        "No fabricated test claims, network calls or trading actions."
    )
    prompt = f"Task: {mission['objective']}\n\nExisting function:\n{function}"

    for attempt in (1, 2):
        print(f"Ollama natif: {MODEL}, tentative {attempt}/2...", flush=True)
        started = time.monotonic()
        artifact, metrics = ollama_complete(system, prompt)
        elapsed = round(time.monotonic() - started, 3)
        (evidence / f"attempt-{attempt}.txt").write_text(artifact + "\n", encoding="utf-8")

        result = {
            "artifact": artifact,
            "sha256": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
            "specialist_id": mission["specialist"],
            "provider": local_codegen.PROVIDER,
            "model": MODEL_ALIAS,
            "generation_seconds": elapsed,
        }
        print(f"Generation: {elapsed:.1f} s. Verification Docker...", flush=True)
        report = local_codegen.verify(mission, result, evidence)
        report["ollama_transport"] = "native-/api/generate"
        report["ollama_model"] = MODEL
        report["ollama_metrics"] = metrics
        save_json(evidence / f"verify-{attempt}.json", report)

        for check in report.get("checks", []):
            print(" ", "OK" if check["ok"] else "ECHEC", check["name"], flush=True)
        if report.get("ok"):
            print("ACCEPTED: Gemma a produit un correctif valide selon Docker", flush=True)
            print("Preuves:", evidence, flush=True)
            return 0

        feedback = report.get("feedback")
        if attempt == 2 or not feedback:
            break
        previous = artifact if feedback.get("kind") == "candidate-test" else None
        repair = local_codegen._repair_prompt(
            mission, feedback, previous, source, function
        )
        prompt = f"Task: {mission['objective']}\n\nExisting function:\n{function}\n\nPrevious attempt:\n{repair}"

    print("REJECTED: aucune proposition valide, preuves conservees", flush=True)
    print("Preuves:", evidence, flush=True)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, HTTPError, URLError) as exc:
        print(f"BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3)
