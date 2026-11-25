"""Route approved code missions among already-loaded loopback llama.cpp models."""

from __future__ import annotations

import ast
from dataclasses import replace
from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path
import re
import socket
import sys
from threading import Timer
import time

from scripts.agents.intelligence import catalog, router


AVAILABLE_MEMORY_RESERVE_MIB = 1024
LARGE_MODEL_MIB = 4096
PROBE_TIMEOUT_SECONDS = 2.0
MAX_PROBE_BYTES = 16_384


class ProbeError(RuntimeError):
    """An explicitly pinned loopback endpoint was not verifiable."""


def validate_candidates(candidates):
    """Validate approval-bound identity, API alias and loopback port for each model."""
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 4:
        raise ValueError("local routing requires 1..4 approved candidates")
    seen = set()
    for binding in candidates:
        if (not isinstance(binding, dict) or binding.keys() != {"id", "model", "port"}
                or not isinstance(binding["id"], str) or not isinstance(binding["model"], str)
                or type(binding["port"]) is not int or not 1024 <= binding["port"] <= 65535):
            raise ValueError("invalid local model binding")
        spec = catalog.by_id(binding["id"])
        if (spec is None or spec.provider not in ("llama.cpp", "ollama")
                or not spec.is_local or not spec.is_free
                or not isinstance(spec.memory_mib, int) or spec.memory_mib <= 0
                or binding["model"] not in spec.served_ids
                or (spec.provider == "ollama" and binding["port"] != 11434)):
            raise ValueError("local model/API alias is not in the approved catalogue")
        if spec.id in seen:
            raise ValueError("local model identities must be unique within an approval")
        seen.add(spec.id)


def _windows_available_memory_mib():
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint32), ("load", ctypes.c_uint32),
            ("total_physical", ctypes.c_uint64), ("available_physical", ctypes.c_uint64),
            ("total_page_file", ctypes.c_uint64), ("available_page_file", ctypes.c_uint64),
            ("total_virtual", ctypes.c_uint64), ("available_virtual", ctypes.c_uint64),
            ("available_extended_virtual", ctypes.c_uint64),
        ]

    status = MemoryStatus(length=ctypes.sizeof(MemoryStatus))
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return status.available_physical // (1024 * 1024)
    return None


def available_memory_mib():
    """Sample physical memory available to an already-loaded model, in MiB."""
    try:
        if sys.platform == "win32":
            return _windows_available_memory_mib()
        if sys.platform.startswith("linux"):
            info = Path("/proc/meminfo").read_text(encoding="ascii")
            match = re.search(r"^MemAvailable:\s+([0-9]+) kB$", info, re.MULTILINE)
            if match:
                return int(match[1]) // 1024
    except (OSError, ValueError):
        pass
    return None


def _probe_json(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=PROBE_TIMEOUT_SECONDS)
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    timer = None
    try:
        connection.connect()
        connected = connection.sock
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError("loopback probe timed out")

        def stop_reading():
            # Bound the whole response even if bytes arrive before each socket timeout.
            try:
                connected.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = Timer(remaining, stop_reading)
        timer.daemon = True
        timer.start()
        connection.request("GET", path)
        with connection.getresponse() as response:
            if response.status != 200:
                raise ProbeError(f"loopback probe returned HTTP {response.status}")
            payload = response.read(MAX_PROBE_BYTES + 1)
        if time.monotonic() >= deadline:
            raise ProbeError("loopback probe timed out")
        if len(payload) > MAX_PROBE_BYTES:
            raise ProbeError("loopback probe response exceeded its byte limit")
        return json.loads(payload)
    except (OSError, HTTPException, ValueError, RecursionError) as exc:
        raise ProbeError("loopback probe unavailable or invalid") from exc
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()


def _probe(port):
    started = time.monotonic()
    served = None
    reason = None
    try:
        health = _probe_json(port, "/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise ProbeError("llama.cpp health is not ready")
        payload = _probe_json(port, "/v1/models")
        models = payload.get("data") if isinstance(payload, dict) else None
        if (not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict)
                or not isinstance(models[0].get("id"), str)):
            raise ProbeError("loopback endpoint did not attest exactly one API model ID")
        served = models[0]["id"]
    except ProbeError as exc:
        reason = str(exc)
    return served, reason, round(1000 * (time.monotonic() - started), 2)


def _probe_ollama(model):
    """Verify the exact installed Ollama model, without loading it or generating."""
    started = time.monotonic()
    try:
        payload = _probe_json(11434, "/api/tags")
        rows = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ProbeError("Ollama model list invalid")
        listed = [row.get("name") for row in rows if isinstance(row, dict)]
        if model not in listed:
            raise ProbeError("approved Ollama model not installed")
        return model, None, round(1000 * (time.monotonic() - started), 2)
    except ProbeError as exc:
        return None, str(exc), round(1000 * (time.monotonic() - started), 2)


def check_selected(binding):
    """Recheck a single previously selected, approval-bound model before generation."""
    try:
        validate_candidates([binding])
    except ValueError:
        return False
    available = available_memory_mib()
    if available is None or available < AVAILABLE_MEMORY_RESERVE_MIB:
        return False
    spec = catalog.by_id(binding["id"])
    if spec.provider == "ollama":
        served, _, _ = _probe_ollama(binding["model"])
    else:
        served, _, _ = _probe(binding["port"])
    return served == binding["model"]


def _task_profile(mission, function):
    branching = (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                 ast.match_case, ast.comprehension)
    complexity = sum(len(node.values) - 1 if isinstance(node, ast.BoolOp) else isinstance(node, branching)
                     for node in ast.walk(ast.parse(function)))
    # A planning estimate for source/objective plus the system, repair and output allowance.
    input_bytes = len((function + mission["objective"]).encode("utf-8"))
    return router.TaskProfile(kind="code", touches_files=1, needs_tools=False, confidential=True,
                              code_complexity=complexity, estimated_tokens=1024 + (input_bytes + 2) // 3)


def _generation_timing(spec, observations):
    seconds = observations.get(spec.id) if isinstance(observations, dict) else None
    if type(seconds) not in (float, int) or not 0 <= seconds <= 80:
        return None, spec.latency_tier
    if seconds <= 25:
        return seconds, "fast"
    if seconds <= 55:
        return seconds, "medium"
    return seconds, "slow"


def choose(mission, function, *, exclude=(), minimum_memory_mib=0, measured_seconds=None, measured_quality=None):
    """Inspect approved bindings and return a route without making a generation call.

    ``measured_seconds`` groups recent mean generation times by difficulty and
    model. Probe RTT measures only the two endpoint checks.
    """
    candidates = mission["routing"]["candidates"]
    validate_candidates(candidates)
    if type(minimum_memory_mib) is not int or minimum_memory_mib < 0:
        raise ValueError("invalid minimum model memory class")
    task = _task_profile(mission, function)
    difficulty, _ = router.classify_difficulty(task)
    timings = measured_seconds.get(difficulty) if isinstance(measured_seconds, dict) else None
    available = available_memory_mib()
    probes = {}
    inventory = []
    eligible = []
    for binding in candidates:
        model_id, port = binding["id"], binding["port"]
        spec = catalog.by_id(model_id)
        generation_seconds, latency_tier = _generation_timing(spec, timings)
        omitted = model_id in exclude
        rtt = None
        reason = None
        verified = False
        if not omitted or spec.memory_mib >= LARGE_MODEL_MIB:
            key = (port, binding["model"]) if spec.provider == "ollama" else (port, "llama.cpp")
            if key not in probes:
                probes[key] = (_probe_ollama(binding["model"]) if spec.provider == "ollama"
                               else _probe(port))
            served, reason, rtt = probes[key]
            verified = served == binding["model"]
        if omitted:
            reason = "excluded from this attempt"
        elif not verified and reason is None:
            reason = "loopback API model ID did not match the approved binding"
        elif verified and (available is None or available < AVAILABLE_MEMORY_RESERVE_MIB):
            reason = "insufficient or unavailable physical memory reserve"
        elif verified and spec.memory_mib < minimum_memory_mib:
            reason = "model is below the escalation memory class"
        inventory.append({**binding, "verified": verified, "eligible": reason is None,
                          "reason": reason, "probe_rtt_ms": rtt, "model_memory_mib": spec.memory_mib,
                          "quality_prior": spec.quality_prior, "latency_tier_prior": spec.latency_tier,
                          "generation_seconds_observed": generation_seconds, "latency_tier_effective": latency_tier})
        if reason is None:
            eligible.append(replace(spec, verified=True, latency_tier=latency_tier))

    # Multiple simultaneously served heavy llama.cpp models are unsafe on 16 GiB.
    # Ollama uses on-demand sequential generations with keep_alive=0s instead.
    heavy_llama = [row for row in inventory if row["verified"]
                   and row["model_memory_mib"] >= LARGE_MODEL_MIB
                   and catalog.by_id(row["id"]).provider == "llama.cpp"]
    if len(heavy_llama) > 1:
        ineligible = {row["id"] for row in heavy_llama}
        eligible = [spec for spec in eligible if spec.id not in ineligible]
        for row in inventory:
            if row["id"] in ineligible and row["eligible"]:
                row.update(eligible=False, reason="more than one large llama.cpp model served")

    routed = router.route(task, verified_local=tuple(eligible), quota_remaining=mission.get("max_attempts", 1),
                          measured_quality=measured_quality,
                          approved_models=frozenset(binding["id"] for binding in candidates)).to_dict()
    rejected = {row["id"]: row["reason"] for row in routed["rejected"]}
    routed["rejected"].extend({"id": row["id"], "reason": row["reason"]}
                              for row in inventory if not row["eligible"])
    for row in inventory:
        if row["id"] in rejected:
            row.update(eligible=False, reason=rejected[row["id"]])
    selection = next((dict(binding) for binding in candidates if binding["id"] == routed["chosen"]), None)
    return {"selection": selection, "decision": routed, "inventory": inventory,
            "available_memory_mib": available}
