# Capacités / MCP de l'équipe OpenHands — inventaire et test (issue #86)

_Date : 16 novembre 2026. Rapport produit par l'agent coordinateur OpenHands
pour le compte du propriétaire. **Lecture seule** : aucun merge, aucun
déploiement, aucun cron, aucun ordre (réel ou simulé), aucun secret affiché._

**Verdict global : PASS (inventaire + un ajout utile déjà présent et testé).
Deux points `BLOCKED` et une action humaine minimale.**

Le présent document est la **source de vérité statique** de l'inventaire. Il est
adossé au module testable `scripts/agents/capabilities/inventory.py` et à ses 13 tests
(`tests/test_agent_mcp_inventory.py`). Le JSON complet est reproductible :

```bash
python3 scripts/agents/capabilities/inventory.py            # affiche le rapport JSON
python3 -m unittest tests.test_agent_mcp_inventory -v
```

## 1. Contexte de quota (garde-fou prioritaire)

```bash
curl -s -H "Authorization: Bearer $OPENHANDS_API_KEY" \
  https://app.all-hands.dev/api/quota/status
```
```json
{"daily_limit":20,"used_today":19,"remaining":1,"reset_at":"2026-11-17T00:00:00+00:00", ...}
```

`remaining = 1 < 12` → **`BLOCKED_QUOTA` pour toute mission longue ou
délégation**. Conformément à la consigne #86 (« ne crée AUCUN sous-agent pour la
préparation de MCPs »), **aucun sous-agent n'a été convoqué** et aucune nouvelle
conversation n'a été ouverte. Le travail ci-dessous est fait dans la session de
coordination existante, sans appeler de modèle payant.

## 2. Inventaire : `EXISTANT`

| Clé | Capacité | Portée | Permissions | Coût |
|---|---|---|---|---|
| `github` | GitHub (Settings → Integrations) | compte | lecture+écriture via jeton de session | gratuit |
| `context7_mcp` | Context7 MCP — documentation à jour | session | lecture seule | gratuit |
| `tavily_mcp` | Tavily MCP — recherche web | session | lecture seule | gratuit (mais quota fournisseur épuisé) |
| `agents_readonly` | Équipe 3 agents, `terminal` seul | sous-agents | `confirm_risky` + garde-fou | gratuit |
| `memory_inter_run` | Mémoire durable inter-runs | compte | bus + KvStore | gratuit |
| `quota_status` | Quota gratuit (API lecture seule) | compte | lecture seule | gratuit |

**Point clé : Context7 est DÉJÀ présent nativement** dans la session OpenHands.
Il n'y a rien à installer côté compte. Preuve par appel d'outil réel (voir §4).

**Point clé : les trois sous-agents n'ont que l'outil `terminal`.** Aucun
sous-agent n'a de tool MCP dédié ; c'est `scripts/agents/team_config.py` qui
l'impose (`validate()` refuse tout autre outil). Un MCP « par rôle » exigerait
donc une modification de définition d'agent — non faite ici (lecture seule).

### Recherche web

Tavily MCP est bien exposé, mais un appel réel renvoie **HTTP 432** (limite du
plan fournisseur) :

```bash
# outil de session default_tavily_tavily_search
# -> {"error":"Search failed","status":432,"detail":{"error":"This request exceeds your plan's set usage limit..."}}
```

→ Présent mais **dégradé** : ne pas compter dessus comme capacité fiable.

## 3. Matrice de besoins (Analyste / Développeur / Vérificateur + commun)

| Rôle | Besoin | Couvert par | Manque |
|---|---|---|---|
| Analyste | lire docs / recherches web | `tavily_mcp` (dégradé 432) + lecture locale | recherche web non fiable |
| Analyste | lire code et données | `terminal` (lecture seule) | — |
| Analyste | documentation à jour | `context7_mcp` | — |
| Développeur | docs SDK / API à jour | `context7_mcp` | — |
| Développeur | exécuter les tests | `terminal` | — |
| Développeur | suivi GitHub | `github` | — |
| Vérificateur | lecture code indépendante | `terminal` | — |
| Vérificateur | reproduire les preuves | `context7_mcp` | — |
| Vérificateur | audits + tests indépendants | `terminal` + tests stdlib | — |
| Commun | suivi GitHub / mémoire / quota | `github`, `memory_inter_run`, `quota_status` | — |

**Conclusion : la matrice est déjà couverte.** Le seul manque réel est la
**recherche web fiable**, et il vient d'un quota fournisseur, pas d'un MCP
manquant.

## 4. `AJOUTÉ ET TESTÉ` : Context7 MCP (déjà présent, exercé sans effet de bord)

Context7 a été **vérifié** sur l'endpoint officiel `https://mcp.context7.com/mcp`
et exercé **sans écriture** via l'API OpenHands autorisée
`POST /api/v1/mcp/test` (qui teste une config et liste les outils **sans rien
persister**).

### 4.1 Test par l'API OpenHands (read-only, aucun secret)

```bash
curl -s -X POST "https://app.all-hands.dev/api/v1/mcp/test" \
  -H "Authorization: Bearer $OPENHANDS_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"context7",
       "server":{"url":"https://mcp.context7.com/mcp","transport":"http"},
       "timeout":20,
       "tool_call":{"name":"resolve-library-id",
                    "arguments":{"libraryName":"OpenHands","query":"sub-agents"}}}'
```
```json
{
 "ok": true,
 "tools": ["resolve-library-id", "query-docs"],
 "tool_result": {"is_error": false,
   "text": "Available Libraries: ... /openhands/software-agent-sdk ... Code Snippets: 1872 ..."}
}
```

### 4.2 Test direct de l'endpoint, **sans aucune clé d'API**

```bash
curl -s -X POST "https://mcp.context7.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize",
       "params":{"protocolVersion":"2024-11-05","capabilities":{},
                 "clientInfo":{"name":"tel99","version":"0.1"}}}'
```
```
event: message
data: {"result":{...,"serverInfo":{"name":"Context7","version":"4.7.0", ...}}}
```

→ L'endpoint public répond **sans header d'authentification**.

### 4.3 Gratuité, confidentialité, coût (docs officielles Context7)

- **Gratuit** : « Most of Context7 is free. The Free plan covers the MCP server,
  the CLI, the Search API, every public library… » — et « a free account includes
  1,000 API calls each month » (`https://context7.com/docs/plans-pricing`).
- **Sans clé pour l'endpoint public** : « No API key is needed »
  (`https://context7.com/docs/installation`).
- **Confidentialité / sécurité** : « Your original prompts stay with your AI
  assistant; Context7 only receives search queries… » ; infrastructure
  **SOC 2 (Upstash)** (`https://context7.com/docs/security`).
- **Outils exposés** : exactement 2, tous **lecture seule**
  (`resolve-library-id`, `query-docs`).
- **Coût réel observé** : 0 (aucune conversation ouverte, aucun modèle appelé).

## 5. `NON NÉCESSAIRE` (pas de doublon)

| Clé | Pourquoi |
|---|---|
| `github_mcp_second` | GitHub **déjà connecté** : une 2e intégration serait un doublon. |
| `second_memory` | La **mémoire inter-runs existe déjà** : doublon interdit par #86. |

## 6. `BLOCKED`

| Clé | Raison | Déblocage |
|---|---|---|
| `mcp_settings_write` | Écrire un serveur MCP **de compte** exige un rôle **Admin/Owner** (`POST /api/organizations/{org_id}/mcp-servers`). Le sandbox ne fait que **lire** (`GET … → {"items":[]}`). | **ACTION_HUMAINE_REQUISE** (§7) |
| `long_mission_quota` | `remaining=1 < 12` | Attendre le reset `2026-11-17T00:00:00Z`, puis relire le quota |

## 7. `ACTION_HUMAINE_REQUISE` (minimum de clics)

Le compte a déjà Context7 **natif** : **aucune action n'est nécessaire** pour en
bénéficier dans les conversations OpenHands.

Si le propriétaire souhaite néanmoins **épingler** Context7 comme serveur MCP de
compte (pour le rendre explicite dans `/settings/mcp`) :

1. Ouvrir `https://app.all-hands.dev/settings/mcp`.
2. **Add MCP server** → URL `https://mcp.context7.com/mcp`, transport **HTTP**,
   **aucune clé**.
3. **Save**.

C'est **la seule action humaine** ; l'agent ne peut pas écrire ces réglages
(permission Admin requise). Tant qu'elle n'est pas faite, l'agent signale
`BLOCKED` — il ne prétend pas que c'est installé.

## 8. Ce qui reste une autorisation humaine

- Écriture des réglages MCP **de compte** (Admin/Owner).
- Toute **fusion**, tout **déploiement**, tout **cron**.
- Tout lancement de mission longue tant que `remaining < 12`.

## 9. Risques et limites (honnêtes)

- **Tavily dégradé** (432) : la recherche web n'est pas fiable aujourd'hui.
- **Context7 = documentation de bibliothèques**, pas un moteur de recherche
  général : son périmètre est la doc de libs/frameworks.
- **Sous-agents = `terminal` seul** : ils bénéficient de Context7 via la session
  parente, pas via un outil MCP nommé. Ne pas annoncer « MCP installé sur les
  trois agents » sans cette nuance.
- **Quota non consommé par cet inventaire** : `remaining=1/20` avant et après.
