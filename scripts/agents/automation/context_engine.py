"""Advanced Context Engineering, AST Code Knowledge Graph, SQLite FTS5 Hybrid RAG & Structured Outputs.

Design principles (TEL99 Ultimate Agent Evolution — Reuse-First):
- Never creates a second source of truth: Code Graph is derived live from AST of workspace files,
  and SQLite FTS5 indexes existing MemoryStore JSON entries deterministically.
- Strict token/byte budgets: selects only relevant files, symbols, dependencies, verified lessons,
  and matching Skills instead of dumping the whole repository.
- Prompt-injection & staleness protection: strips control/override markers and excludes superseded entries.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Sequence

from scripts.agents.intelligence.memory import COMMON_PROJECT, Entry, MemoryStore

INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?safety|bypass\s+guard", re.IGNORECASE),
    re.compile(r"exfiltrate|reveal\s+(your\s+)?(api|secret|token)", re.IGNORECASE),
)

IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
    ".mypy_cache", "dist", "build", ".cache",
})


def sanitize_untrusted_text(text: str, *, max_chars: int = 400) -> tuple[str, bool]:
    """Strip control chars and neutralize prompt-injection directives in external/memory text."""
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", " ", str(text or "")).strip()
    flagged = False
    for pat in INJECTION_PATTERNS:
        if pat.search(clean):
            clean = pat.sub("[REDACTED_DIRECTIVE]", clean)
            flagged = True
    if len(clean) > max_chars:
        clean = clean[: max_chars - 3].rstrip() + "..."
    return clean, flagged


def estimate_tokens(text: str) -> int:
    """Fast deterministic token estimate (~3.8 chars/token for code/French prose)."""
    if not text:
        return 0
    return max(1, int(round(len(text) / 3.8)))


# ---------------------------------------------------------------------------
# 1. Live AST Code Knowledge Graph (§5)
# ---------------------------------------------------------------------------
def build_code_graph(workspace_root: Path | str, *, max_files: int = 300) -> dict[str, Any]:
    """Build a fresh, verifiable AST knowledge graph of Python modules, symbols, imports, calls, and tests."""
    root = Path(workspace_root).resolve()
    files_index: dict[str, dict[str, Any]] = {}
    symbol_index: dict[str, list[str]] = {}
    reverse_imports: dict[str, set[str]] = {}
    test_links: dict[str, list[str]] = {}

    py_files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        py_files.append(path)
        if len(py_files) >= max_files:
            break

    for path in py_files:
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=rel)
        except (OSError, SyntaxError):
            files_index[rel] = {"parse_ok": False, "functions": [], "classes": [], "imports": [], "calls": [], "lines": 0}
            continue

        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []
        imports: set[str] = set()
        calls: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                    "args": [a.arg for a in node.args.args],
                })
                symbol_index.setdefault(node.name, []).append(rel)
            elif isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({"name": node.name, "lineno": node.lineno, "methods": methods})
                symbol_index.setdefault(node.name, []).append(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)

        mod_stem = path.stem
        files_index[rel] = {
            "parse_ok": True,
            "module_stem": mod_stem,
            "lines": len(source.splitlines()),
            "functions": functions,
            "classes": classes,
            "imports": sorted(imports),
            "calls": sorted(calls)[:80],
            "is_test": rel.startswith("tests/") or mod_stem.startswith("test_"),
        }

    # Resolve intra-repo dependencies & map tests to source modules
    stem_to_rel = {info.get("module_stem"): rel for rel, info in files_index.items() if info.get("module_stem")}
    for rel, info in files_index.items():
        local_deps: set[str] = set()
        for imp in info.get("imports", ()):
            tail = imp.rsplit(".", 1)[-1]
            if tail in stem_to_rel and stem_to_rel[tail] != rel:
                dep_rel = stem_to_rel[tail]
                local_deps.add(dep_rel)
                reverse_imports.setdefault(dep_rel, set()).add(rel)
                if info.get("is_test"):
                    test_links.setdefault(dep_rel, []).append(rel)
        info["local_dependencies"] = sorted(local_deps)

    for rel, info in files_index.items():
        info["dependents"] = sorted(reverse_imports.get(rel, set()))
        info["related_tests"] = sorted(set(test_links.get(rel, [])))

    return {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workspace_root": str(root),
        "file_count": len(files_index),
        "symbol_count": len(symbol_index),
        "files": files_index,
        "symbols": {k: sorted(set(v)) for k, v in symbol_index.items()},
    }


def impact_analysis(graph: dict[str, Any], target: str) -> dict[str, Any]:
    """Compute direct & transitive dependents, interfaces, and related tests for a file or symbol."""
    files = graph.get("files") or {}
    norm = target.replace("\\", "/")
    matched_files = [norm] if norm in files else list((graph.get("symbols") or {}).get(target, []))
    direct_dependents: set[str] = set()
    transitive_dependents: set[str] = set()
    related_tests: set[str] = set()
    local_deps: set[str] = set()

    queue = list(matched_files)
    visited = set(matched_files)
    while queue:
        cur = queue.pop(0)
        info = files.get(cur) or {}
        local_deps.update(info.get("local_dependencies") or [])
        related_tests.update(info.get("related_tests") or [])
        for dep in info.get("dependents") or []:
            if cur in matched_files:
                direct_dependents.add(dep)
            if dep not in visited:
                visited.add(dep)
                transitive_dependents.add(dep)
                queue.append(dep)

    return {
        "target": target,
        "matched_files": matched_files,
        "local_dependencies": sorted(local_deps),
        "direct_dependents": sorted(direct_dependents),
        "transitive_dependents": sorted(transitive_dependents),
        "related_tests": sorted(related_tests),
        "risk_level": "high" if len(transitive_dependents) >= 5 else ("medium" if transitive_dependents else "low"),
    }


# ---------------------------------------------------------------------------
# 2. SQLite FTS5 Hybrid Memory Index (§12 — Reuses MemoryStore as Single Source of Truth)
# ---------------------------------------------------------------------------
class HybridMemoryIndex:
    """In-memory or ephemeral SQLite FTS5 BM25 + metadata ranker synced directly from MemoryStore."""

    def __init__(self, memory_root: Path | str) -> None:
        self.memory_root = Path(memory_root)
        self.store = MemoryStore(self.memory_root)

    def search(
        self,
        project: str,
        query: str,
        *,
        limit: int = 5,
        verified_only: bool = False,
        include_common: bool = True,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid BM25 (SQLite FTS5) + verification/confidence/role boost over project-isolated MemoryStore."""
        if not self.memory_root.exists():
            return []
        entries = self.store.all_entries(project, include_common=include_common)
        active = [
            e for e in entries
            if not e.superseded_by and (not verified_only or (e.verified and bool(e.verified_by)))
        ]
        if not active:
            return []

        tokens = re.findall(r"[A-Za-z0-9_]{2,}", (query or "").lower())
        if not tokens:
            return []

        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE mem_fts USING fts5("
                "entry_id UNINDEXED, title, body, tags, tokenize='porter unicode61')"
            )
            by_id: dict[str, Entry] = {}
            for e in active:
                by_id[e.id] = e
                safe_title, _ = sanitize_untrusted_text(e.title, max_chars=200)
                safe_body, _ = sanitize_untrusted_text(e.body, max_chars=500)
                conn.execute(
                    "INSERT INTO mem_fts(entry_id, title, body, tags) VALUES (?, ?, ?, ?)",
                    (e.id, safe_title, safe_body, " ".join(e.tags)),
                )
            fts_query = " OR ".join(f'"{tok}"' for tok in sorted(set(tokens))[:12])
            rows = conn.execute(
                "SELECT entry_id, bm25(mem_fts, 3.0, 1.0, 2.0) AS rank "
                "FROM mem_fts WHERE mem_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, max(limit * 4, 12)),
            ).fetchall()
        finally:
            conn.close()

        ranked: list[tuple[float, dict[str, Any]]] = []
        for entry_id, bm25_rank in rows:
            e = by_id[entry_id]
            # SQLite bm25() returns negative scores where more negative = stronger match
            score = -float(bm25_rank)
            if e.verified:
                score += 1.5
            if e.kind in ("fix", "procedure"):
                score += 0.8
            if role and e.author == role:
                score += 0.5
            if e.project == project:
                score += 0.4
            score += 0.5 * float(e.confidence)
            safe_title, f1 = sanitize_untrusted_text(e.title, max_chars=120)
            safe_body, f2 = sanitize_untrusted_text(e.body, max_chars=240)
            ranked.append((
                score,
                {
                    "id": e.id,
                    "project": e.project,
                    "kind": e.kind,
                    "title": safe_title,
                    "body": safe_body,
                    "author": e.author,
                    "verified": e.verified,
                    "verified_by": e.verified_by,
                    "created_at": e.created_at,
                    "score": round(score, 4),
                    "injection_sanitized": bool(f1 or f2),
                    "scope": (
                        "procedural" if e.kind == "procedure"
                        else ("individual" if role and e.author == role
                              else ("collective" if e.project == COMMON_PROJECT else "project"))
                    ),
                },
            ))
        ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [item[1] for item in ranked[:limit]]


# ---------------------------------------------------------------------------
# 3. Selective Mission Context Packer (§4)
# ---------------------------------------------------------------------------
def select_relevant_skills(skills_root: Path | str, query: str, *, limit: int = 2) -> list[dict[str, str]]:
    """Select only Skills matching the mission query instead of loading every SKILL.md."""
    root = Path(skills_root)
    if not root.is_dir():
        return []
    tokens = set(re.findall(r"[a-z0-9_-]{3,}", (query or "").lower()))
    scored: list[tuple[int, str, str, str]] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = skill_md.parent.name
        hay = set(re.findall(r"[a-z0-9_-]{3,}", (name + " " + text[:800]).lower()))
        hits = len(tokens & hay)
        if hits > 0:
            scored.append((hits, name, str(skill_md), text[:500].strip()))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"name": n, "path": p, "excerpt": ex} for _, n, p, ex in scored[:limit]]


def build_mission_context(
    workspace_root: Path | str,
    mission: dict[str, Any],
    *,
    memory_root: Path | str | None = None,
    skills_root: Path | str | None = None,
    hard_constraints: Sequence[str] = (),
    max_chars: int = 4400,
) -> dict[str, Any]:
    """Assemble a strictly bounded, provenance-tagged context packet for an agent mission."""
    root = Path(workspace_root).resolve()
    graph = build_code_graph(root)
    target = str(mission.get("target_file") or mission.get("path") or "").replace("\\", "/")
    objective = str(mission.get("objective") or "")
    project = str(mission.get("project") or "tel99")
    role = str(mission.get("specialist") or "")

    impact = impact_analysis(graph, target) if target else {"matched_files": [], "local_dependencies": [], "related_tests": [], "risk_level": "low"}
    selected_files: list[str] = []
    for rel in [target, *impact.get("local_dependencies", [])[:3], *impact.get("related_tests", [])[:2]]:
        if rel and rel not in selected_files and (root / rel).is_file():
            selected_files.append(rel)

    # Extract concise symbol signatures rather than dumping full repository files
    file_summaries: list[dict[str, Any]] = []
    repo_total_chars = 0
    for rel, info in graph["files"].items():
        p = root / rel
        if p.is_file():
            try:
                repo_total_chars += p.stat().st_size
            except OSError:
                pass
    for rel in selected_files:
        info = graph["files"].get(rel) or {}
        sigs = [f"def {fn['name']}({', '.join(fn['args'])})" for fn in (info.get("functions") or [])[:12]]
        cls = [f"class {c['name']}({', '.join(c['methods'][:6])})" for c in (info.get("classes") or [])[:6]]
        file_summaries.append({
            "path": rel,
            "lines": info.get("lines", 0),
            "signatures": sigs + cls,
            "imports": (info.get("imports") or [])[:10],
        })

    memories: list[dict[str, Any]] = []
    if memory_root is not None:
        idx = HybridMemoryIndex(memory_root)
        memories = idx.search(project, f"{target} {objective}", limit=3, verified_only=True, role=role or None)

    skills = select_relevant_skills(skills_root, f"{target} {objective}", limit=2) if skills_root else []

    sections = [
        f"OBJECTIVE: {objective.strip()[:900]}",
        "HARD CONSTRAINTS (preserved verbatim):\n- " + "\n- ".join(hard_constraints or ("Follow contract strictly", "No security bypass")),
    ]
    if file_summaries:
        lines = []
        for fs in file_summaries:
            lines.append(f"- {fs['path']} ({fs['lines']}L): " + "; ".join(fs["signatures"][:8]))
        sections.append("CODE GRAPH INTERFACES:\n" + "\n".join(lines))
    if impact.get("direct_dependents"):
        sections.append("IMPACT DEPENDENTS: " + ", ".join(impact["direct_dependents"][:8]))
    if memories:
        sections.append(
            "VERIFIED MEMORY (FTS5 hybrid):\n- "
            + "\n- ".join(f"[{m['scope']}|{m['kind']}] {m['title']}: {m['body']}" for m in memories)
        )
    if skills:
        sections.append("RELEVANT SKILLS: " + ", ".join(s["name"] for s in skills))

    packed = "\n\n".join(sections)
    if len(packed) > max_chars:
        # Preserve hard constraints at top and truncate middle softly
        packed = packed[: max_chars - 24].rstrip() + "\n[context budget cap]"

    compression_ratio = round(len(packed) / max(1, repo_total_chars), 4) if repo_total_chars else 1.0
    return {
        "packed_context": packed,
        "chars": len(packed),
        "estimated_tokens": estimate_tokens(packed),
        "repo_total_chars": repo_total_chars,
        "compression_ratio": compression_ratio,
        "files_selected": selected_files,
        "impact": impact,
        "memories_used": memories,
        "skills_selected": [s["name"] for s in skills],
    }


# ---------------------------------------------------------------------------
# 4. Structured Output Validation (§9 — Stdlib + Optional Pydantic)
# ---------------------------------------------------------------------------
def validate_structured_json(
    raw_text: str,
    *,
    required_fields: dict[str, type | tuple[type, ...]],
    optional_fields: dict[str, type | tuple[type, ...]] | None = None,
) -> dict[str, Any]:
    """Parse and strictly validate structured JSON output from an agent/model."""
    text = (raw_text or "").strip()
    fence = re.search(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError as exc:
        return {"ok": False, "error": f"Invalid JSON: {exc}", "data": None}
    if not isinstance(data, dict):
        return {"ok": False, "error": "Expected JSON object", "data": None}

    opt = optional_fields or {}
    allowed_keys = set(required_fields) | set(opt)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        return {"ok": False, "error": f"Unexpected fields: {', '.join(unknown)}", "data": None}

    for key, expected_type in required_fields.items():
        if key not in data:
            return {"ok": False, "error": f"Missing required field: {key}", "data": None}
        val = data[key]
        if expected_type is int and type(val) is bool:
            return {"ok": False, "error": f"Field {key} cannot be bool when int expected", "data": None}
        if not isinstance(val, expected_type):
            return {"ok": False, "error": f"Field {key} wrong type: got {type(val).__name__}", "data": None}

    for key, expected_type in opt.items():
        if key in data and data[key] is not None:
            val = data[key]
            if expected_type is int and type(val) is bool:
                return {"ok": False, "error": f"Field {key} cannot be bool when int expected", "data": None}
            if not isinstance(val, expected_type):
                return {"ok": False, "error": f"Optional field {key} wrong type: got {type(val).__name__}", "data": None}

    return {"ok": True, "error": None, "data": data}
