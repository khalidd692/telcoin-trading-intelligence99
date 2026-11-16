#!/usr/bin/env python3
"""Read-only inventory of OpenHands capabilities and MCP needs (TEL99, issue #86).

Single source of truth for the *measured* state. Every entry carries the
command that produced it, so a reader can re-run it. This module makes NO
network call and opens NO conversation: it is data + pure functions.

Verdict vocabulary (the five buckets requested on issue #86):

- EXISTANT          : already available in the OpenHands account / session
- A_AJOUTER         : useful, free, safe, non-duplicate -- not yet enabled
- AJOUTE_ET_TESTE   : enabled and exercised with a real, side-effect-free call
- NON_NECESSAIRE    : duplicate of an existing capability
- BLOCKED           : cannot proceed (quota, missing permission, human action)

Rule of thumb enforced by ``validate()``: an entry may only be AJOUTE_ET_TESTE
when it is free (``cost == "gratuit"``), read-only (``writes is False``) and
carries at least one reproducible evidence line.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

# The three active TEL99 roles (see scripts/agents/team_config.py).
ROLES: tuple[str, ...] = ("tel99-analyst", "tel99-dev", "tel99-verifier")

# Free daily conversation quota gate from issue #86 ("remaining >= 12").
QUOTA_MIN_REMAINING = 12


@dataclass(frozen=True)
class Capability:
    """One native capability or candidate MCP server."""

    key: str
    label: str
    verdict: str
    scope: str            # "compte" | "session" | "sous-agents" | "role"
    url: str = ""
    permissions: str = ""
    cost: str = ""        # "gratuit" | "payant" | "inconnu"
    writes: bool = False
    roles: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    notes: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["roles"] = list(self.roles)
        d["evidence"] = list(self.evidence)
        return d


# --------------------------------------------------------------------------
# 1. EXISTANT -- what the account / session / sub-agents already have.
# --------------------------------------------------------------------------
EXISTING: tuple[Capability, ...] = (
    Capability(
        key="github",
        label="GitHub (Integrations)",
        verdict="EXISTANT",
        scope="compte",
        url="https://github.com/khalidd692/telcoin-trading-intelligence99",
        permissions="lecture+ecriture via jeton de session (jamais affiche)",
        cost="gratuit",
        roles=ROLES,
        evidence=(
            'curl -s -H "Authorization: Bearer $GITHUB_TOKEN" '
            "https://api.github.com/repos/khalidd692/telcoin-trading-intelligence99/issues/86",
        ),
        notes="Deja connecte (Settings -> Integrations). Ne pas installer une 2e integration equivalente.",
    ),
    Capability(
        key="context7_mcp",
        label="Context7 MCP (documentation a jour)",
        verdict="EXISTANT",
        scope="session",
        url="https://mcp.context7.com/mcp",
        permissions="lecture seule (resolve-library-id, query-docs)",
        cost="gratuit",
        roles=("tel99-dev", "tel99-verifier"),
        evidence=(
            "outils exposes dans cette session : Context7_resolve-library-id, Context7_query-docs",
            'POST https://app.all-hands.dev/api/v1/mcp/test '
            '{"server":{"url":"https://mcp.context7.com/mcp","transport":"http"}} -> ok=true, '
            'tools=["resolve-library-id","query-docs"]',
        ),
        notes="Deja natif dans la session OpenHands : rien a installer cote compte.",
    ),
    Capability(
        key="tavily_mcp",
        label="Tavily MCP (recherche web)",
        verdict="EXISTANT",
        scope="session",
        url="https://mcp.tavily.com",
        permissions="lecture seule (recherche/extraction web)",
        cost="gratuit",
        roles=("tel99-analyst",),
        evidence=(
            "outils exposes dans cette session : default_tavily_tavily_search, tavily_extract, ...",
            "appel reel -> HTTP 432 (plan Tavily au-dela de sa limite) : present mais degrade",
        ),
        notes="Present mais quota fournisseur epuise (432). Ne pas compter dessus comme capacite fiable.",
    ),
    Capability(
        key="agents_readonly",
        label="Equipe 3 agents (terminal seul, LECTURE SEULE)",
        verdict="EXISTANT",
        scope="sous-agents",
        url=".agents/agents/tel99-*.md",
        permissions="terminal uniquement, permission_mode=confirm_risky, hook PreToolUse guard.py",
        cost="gratuit",
        roles=ROLES,
        evidence=(
            "cat .agents/agents/tel99-dev.md -> tools: [terminal]",
            "cat scripts/agents/team_config.py -> validate(): spec.tools != ('terminal',) -> ValueError",
        ),
        notes="Un sous-agent n'a PAS de tool MCP dedie : il n'a que terminal + le garde-fou.",
    ),
    Capability(
        key="memory_inter_run",
        label="Memoire durable inter-runs",
        verdict="EXISTANT",
        scope="compte",
        url="memory/projects/tel99.json",
        permissions="lecture/ecriture via bus + KvStore (pas de secret en clair)",
        cost="gratuit",
        roles=ROLES,
        evidence=(
            "curl -s /api/v1/settings -> enable_memory_context=true",
            "ls memory/ -> common.json, measured_quality.json, projects/tel99.json",
        ),
        notes="Deja partagee entre conversations : ne pas ajouter un 2e systeme de memoire.",
    ),
    Capability(
        key="quota_status",
        label="Quota gratuit (API lecture seule)",
        verdict="EXISTANT",
        scope="compte",
        url="https://app.all-hands.dev/api/quota/status",
        permissions="lecture seule",
        cost="gratuit",
        roles=ROLES,
        evidence=(
            'curl -s -H "Authorization: Bearer $OPENHANDS_API_KEY" '
            "https://app.all-hands.dev/api/quota/status",
        ),
        notes="Source de verite du quota. Ne jamais presumer un nombre : relire.",
    ),
)


# --------------------------------------------------------------------------
# 2. A_AJOUTER -- useful, free, safe, non-duplicate, but not yet enabled.
# --------------------------------------------------------------------------
TO_ADD: tuple[Capability, ...] = ()

# --------------------------------------------------------------------------
# 3. AJOUTE_ET_TESTE -- enabled and exercised with a real side-effect-free call.
# --------------------------------------------------------------------------
ADDED_AND_TESTED: tuple[Capability, ...] = (
    Capability(
        key="context7_mcp_test",
        label="Context7 MCP -- test d'outil sans effet de bord",
        verdict="AJOUTE_ET_TESTE",
        scope="role",
        url="https://mcp.context7.com/mcp",
        permissions="lecture seule, sans cle d'API pour l'endpoint public",
        cost="gratuit",
        roles=("tel99-dev", "tel99-verifier"),
        evidence=(
            'POST /api/v1/mcp/test {"name":"context7","server":{"url":'
            '"https://mcp.context7.com/mcp","transport":"http"},'
            '"tool_call":{"name":"resolve-library-id",'
            '"arguments":{"libraryName":"OpenHands","query":"sub-agents"}}} '
            "-> HTTP 200, ok=true, tool_result.is_error=false",
            "POST https://mcp.context7.com/mcp initialize (SANS header d'auth) "
            "-> serverInfo Context7 v4.7.0",
        ),
        notes="Teste via l'API OpenHands autorisee (aucune modification persistee, aucun secret).",
    ),
)


# --------------------------------------------------------------------------
# 4. NON_NECESSAIRE -- duplicates an existing capability.
# --------------------------------------------------------------------------
NOT_NEEDED: tuple[Capability, ...] = (
    Capability(
        key="github_mcp_second",
        label="2e serveur MCP GitHub",
        verdict="NON_NECESSAIRE",
        scope="compte",
        url="",
        permissions="n/a",
        cost="gratuit",
        roles=ROLES,
        evidence=("GitHub deja connecte (voir EXISTANT/github) : doublon.",),
        notes="Ne pas installer une deuxieme integration offrant les memes capacites.",
    ),
    Capability(
        key="second_memory",
        label="2e systeme de memoire MCP",
        verdict="NON_NECESSAIRE",
        scope="compte",
        url="",
        permissions="n/a",
        cost="gratuit",
        roles=ROLES,
        evidence=("Memoire inter-runs deja presente (voir EXISTANT/memory_inter_run).",),
        notes="La consigne #86 interdit explicitement un doublon de memoire.",
    ),
)


# --------------------------------------------------------------------------
# 5. BLOCKED -- cannot proceed.
# --------------------------------------------------------------------------
BLOCKED: tuple[Capability, ...] = (
    Capability(
        key="mcp_settings_write",
        label="Modification des reglages MCP du compte depuis le sandbox",
        verdict="BLOCKED",
        scope="compte",
        url="https://app.all-hands.dev/settings/mcp",
        permissions="Admin/Owner requis pour POST /api/organizations/{org_id}/mcp-servers",
        cost="gratuit",
        roles=ROLES,
        evidence=(
            "GET /api/organizations/<org_id>/mcp-servers -> HTTP 200 {\"items\":[]} (lecture OK)",
            "POST .../mcp-servers : 'Admin/Owner only' (OpenAPI) -> ecriture compte non autorisee ici",
        ),
        notes="ACTION_HUMAINE_REQUISE: ajouter un serveur MCP compte se fait depuis l'UI/avec un role admin.",
    ),
    Capability(
        key="long_mission_quota",
        label="Mission longue / delegation multi-agents",
        verdict="BLOCKED",
        scope="compte",
        url="https://app.all-hands.dev/api/quota/status",
        permissions="n/a",
        cost="gratuit",
        roles=ROLES,
        evidence=(
            'curl -s -H "Authorization: Bearer $OPENHANDS_API_KEY" '
            "https://app.all-hands.dev/api/quota/status -> remaining=1/20 (< 12)",
        ),
        notes="BLOCKED_QUOTA: conserver la reserve ; aucune mission longue ni sous-agent lance.",
    ),
)


# --------------------------------------------------------------------------
# Needs matrix: what each role needs, and whether it is already covered.
# --------------------------------------------------------------------------
NEEDS_MATRIX: dict[str, tuple[dict, ...]] = {
    "tel99-analyst": (
        {"need": "lire docs / recherches web", "covered_by": "tavily_mcp (degrade 432) + lecture locale", "gap": "recherche web non fiable (quota fournisseur)"},
        {"need": "lire le code et les donnees", "covered_by": "terminal (lecture seule)", "gap": ""},
        {"need": "documentation a jour", "covered_by": "context7_mcp", "gap": ""},
    ),
    "tel99-dev": (
        {"need": "docs SDK / API a jour", "covered_by": "context7_mcp", "gap": ""},
        {"need": "executer les tests", "covered_by": "terminal (lecture seule + tests autorises)", "gap": ""},
        {"need": "suivi GitHub (issues/PR)", "covered_by": "github (jeton de session)", "gap": ""},
    ),
    "tel99-verifier": (
        {"need": "lecture code independante", "covered_by": "terminal (lecture seule)", "gap": ""},
        {"need": "reproduire les preuves (docs a jour)", "covered_by": "context7_mcp", "gap": ""},
        {"need": "audits et tests independants", "covered_by": "terminal + tests stdlib", "gap": ""},
    ),
    "commun": (
        {"need": "suivi GitHub (issues/PR)", "covered_by": "github", "gap": ""},
        {"need": "memoire inter-runs", "covered_by": "memory_inter_run", "gap": ""},
        {"need": "controle de quota", "covered_by": "quota_status", "gap": ""},
    ),
}


def all_capabilities() -> tuple[Capability, ...]:
    return EXISTING + TO_ADD + ADDED_AND_TESTED + NOT_NEEDED + BLOCKED


def counts() -> dict[str, int]:
    """Verdict histogram, always including the five canonical buckets."""
    buckets = ["EXISTANT", "A_AJOUTER", "AJOUTE_ET_TESTE", "NON_NECESSAIRE", "BLOCKED"]
    out = {b: 0 for b in buckets}
    for cap in all_capabilities():
        out[cap.verdict] = out.get(cap.verdict, 0) + 1
    return out


def validate() -> None:
    """Fail loudly on an unsafe or inconsistent inventory.

    Enforces the #86 safety rule: nothing is reported as enabled/tested unless
    it is free, read-only and backed by reproducible evidence. It also refuses
    an "A_AJOUTER" entry that is a duplicate of an EXISTANT capability.
    """
    valid = {"EXISTANT", "A_AJOUTER", "AJOUTE_ET_TESTE", "NON_NECESSAIRE", "BLOCKED"}
    existing_keys = {c.key for c in EXISTING}
    for cap in all_capabilities():
        if cap.verdict not in valid:
            raise ValueError(f"{cap.key}: unknown verdict {cap.verdict!r}")
        if cap.verdict == "AJOUTE_ET_TESTE":
            if cap.cost != "gratuit":
                raise ValueError(f"{cap.key}: only free capabilities may be marked tested")
            if cap.writes:
                raise ValueError(f"{cap.key}: a writing capability must not be marked tested")
            if not cap.evidence:
                raise ValueError(f"{cap.key}: tested capability needs reproducible evidence")
        if cap.verdict == "A_AJOUTER" and cap.key in existing_keys:
            raise ValueError(f"{cap.key}: cannot be A_AJOUTER, it already exists")
    if counts()["AJOUTE_ET_TESTE"] < 1:
        raise ValueError("at least one capability must be measured and tested")


def report() -> dict:
    """Full, JSON-serialisable snapshot of the inventory."""
    return {
        "schema": 1,
        "issue": 86,
        "mode": "read_only",
        "orders_allowed": False,
        "deploy_allowed": False,
        "quota_min_remaining": QUOTA_MIN_REMAINING,
        "roles": list(ROLES),
        "counts": counts(),
        "capabilities": [c.as_dict() for c in all_capabilities()],
        "needs_matrix": {role: list(items) for role, items in NEEDS_MATRIX.items()},
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="write the report JSON to this path")
    parser.add_argument("--check", action="store_true", help="validate only")
    args = parser.parse_args()

    validate()
    data = report()
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.output}")
    if not args.output:
        print(text)
    print(f"verdicts: {data['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
