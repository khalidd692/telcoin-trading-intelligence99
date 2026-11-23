# Audit indépendant du pilote GitHub → Ollama → Docker

Référence auditée `3dc03e8d1a6a13d002249ec330f21003353da172`, tête de la [PR #168](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/168). Les checks de cette note portent sur cette révision et les preuves historiques publiées.

## Vérifications exécutées

| Vérification | Résultat |
| --- | --- |
| `python -B -m unittest discover -s tests -q` sur Linux, Python 3.12 | 1 211 recensés, 1 178 réussites, 33 ignorés, zéro échec |
| Suite sécurité utilisée par le lanceur `run_github_code.ps1` sur Linux | 59 réussites |
| `python -B -m unittest discover -s collector -p 'test_*.py' -q` | 42 réussites |
| `node tests/test_dashboard.js` et `node tests/test_realtime.js` | Deux suites réussies |
| `npm --prefix cloudflare/tel99-hybrid test` | 9 réussites |
| `python -B scripts/agents/render_agents.py --check` et `git diff --check origin/main...HEAD` | Réussis |
| `tests.test_local_codegen_repair_e2e` et `tests.test_local_model_routing_e2e` avec `TEL99_TEST_SANDBOX_IMAGE` épinglée | 2 réussites, Docker et processus worker réels, réponses de modèle scriptées sur loopback |
| `tests.test_agent_native` avec la même image | 58 réussites, dont deux tests activés avec Docker réel |
| CI sécurité hors ligne au commit audité | Jobs Windows et Ubuntu réussis ([run 45266782244](https://github.com/khalidd692/telcoin-trading-intelligence99/actions/runs/45266782244)) |

La sonde locale `ScriptCheck` utilise l’image Python `docker.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`. Le conteneur s’exécute avec UID/GID 65534, sans capacité effective et avec `NoNewPrivs=1`. Le réseau ne présente que `lo`. Le système de fichiers racine et le fichier Python monté sont en lecture seule. Le répertoire `/scratch` accepte l’écriture. Le socket Docker et une variable témoin définie sur l’hôte sont absents du conteneur.

Le daemon cloud Linux est rootless sans cgroups. `docker info` renvoie `CgroupDriver=none` et signale l’absence de cgroups en mode rootless. Avec les options de production de 256 Mio, un CPU et 32 PID, la sonde relève `memory.max=8589934592`, `cpu.max=200000 100000` et `pids.max=max`. Une recette des plafonds nécessite un daemon avec cgroups actifs. Les tests Docker ci-dessus démontrent les verdicts métier dans l’environnement disponible.

## Contrôle des preuves historiques

- Le [mandat #169](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/169#issuecomment-7113655599) et les six reçus ACK, EVIDENCE et RESULT des [issues #170](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/170) et [#171](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/171) proviennent du propriétaire `khalidd692`. Les dates de création et de dernière modification correspondent. Les deux EVIDENCE publient baseline exit 1 et candidat exit 0.
- Les commits récupérés en lecture seule depuis `refs/pull/172/head` et `refs/pull/173/head` modifient chacun un seul fichier par rapport à `934d9fd8a3fd498c6e3e69226007dd46276aa6da`. Les SHA-256 des fichiers complets, `d6f16f38b2695bafa69c2dfab3e0241f9b7fb8088b36c7f5408edbd31ddf4943` et `f1bc6023467556ab653fc0909e3f09023d0a3156566baf9f7746608a767b4554`, correspondent aux [PR #172](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/172) et [#173](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/173). Le digest de l’EVIDENCE identifie le fragment produit par le modèle. Celui de la PR identifie le fichier matérialisé.
- Sur la campagne Windows, la sortie `delivery=COMPLETE` et les 59 tests proviennent du [rapport opérateur #94](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7114469111). Le ledger Windows est resté hors de cette session. Les tests Linux ci-dessus utilisent les fixtures du dépôt.

## Garanties et limites de cette révision

| Surface | Constat |
| --- | --- |
| Admission | L’identité propriétaire repose sur le login, l’ID de compte et le type GitHub. Le corps du mandat est épinglé SHA-256. La date, le dépôt, la base, les deux contrats, les issues et leurs dépendances sont contrôlés. L’empreinte SHA-256 protège le contenu. GitHub authentifie l’auteur. |
| Exclusivité | Le verrou de session, le claim et l’outbox CAS s’appliquent au même ledger. Des processus qui démarrent simultanément avec deux ledgers pour le même mandat peuvent chacun constater l’absence d’ACK avant publication. Un répertoire d’état canonique par mandat est nécessaire pour bénéficier de l’exclusion locale. Une garantie inter-machines exige un arbitre partagé. |
| Fournisseur | L’admission du pilote accepte une équipe fixe sur un port loopback autre que 11434. Dans ce cas, le worker de développement rejoint un serveur compatible OpenAI alors que l’événement déclare `ollama-loopback`. Le profil GitHub doit épingler le port et le modèle Ollama à l’admission et dans le contrôle de publication. |
| Portée | Le pilote vise exactement deux missions, un fichier Python par mission et une base isolée figée à `934d9fd8`. Un autre lot de deux missions sur cette base est possible avec un nouveau mandat. L’admission d’une nouvelle base nécessite son propre contrôle d’autorisation. |
| Vérification | Le test approuvé, son empreinte et le verdict Docker sont liés au contrat, au résultat et au fichier matérialisé. La revue du brouillon reste nécessaire pour contrôler les effets hors des cas de test. |
| Publication | L’ACK précède l’exécution et la publication recalcule les octets du candidat. Chaque écriture PR revalide l’approbation. Le brouillon doit provenir du propriétaire et modifier exactement le fichier prévu sur la base approuvée. Un POST PR d’issue incertaine est réconcilié par lecture. |
| Cockpit Night Lab | Le serveur écoute sur loopback et refuse les en-têtes Host externes. Dans la version auditée, `/status.json` retourne les octets du fichier local sans projection. Un branchement au ledger GitHub doit borner les données, garder le code, les tests approuvés et les prompts privés, et considérer la fraîcheur du heartbeat pour qualifier l’activité. |

Cette session n’avait pas d’Ollama actif ni d’accès au PC Windows. La validation des nouveaux modèles et la recette de deux nouvelles issues GitHub sur ce PC restent à réaliser séparément des résultats historiques.
