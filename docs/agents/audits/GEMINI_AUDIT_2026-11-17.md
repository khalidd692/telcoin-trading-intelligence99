# AUDIT EXTERNE — GEMINI — RAPPORT A–K
**Réception :** 17 novembre 2026. Source : réponse de Gemini fournie par le propriétaire dans cette conversation.
**Périmètre de Gemini :** aucun connecteur de lecture GitHub. [FAIT] dans sa réponse = information fournie par le brief, [HYPOTHÈSE] = déduction, [PROPOSITION] = cible. Ceci est une **retranscription structurée détaillée**, non une transcription mot à mot. Les chiffres et jours sont proposés, non mesurés.

## A. Verdict
Prototype distribué fragmenté entre main et huit PR non fusionnées. Pile #76 intégrée ; cloud ponctuel PC éteint (#80), mémoire inter-sandboxes ponctuelle (#84), scripts Python locaux ; correctifs #79 non intégrés, Kilo non relié au bus, secret #88 à révoquer. Les capacités documentaires dépassent la preuve d'exécution réelle.

## B. Audit de vérité selon Gemini
| Capacité | Statut attribué | Motif |
|---|---|---|
| Socle #76 | Prouvé | Fusion antérieure |
| Cloud PC éteint | Prouvé ponctuellement | #80, pas service continu |
| Mémoire inter-sandboxes | Expérimental | #84, #85/#91 en attente |
| Orchestration main | Bloqué | #79 non intégré |
| Kilo et bus GitHub | Bloqué | connected=False |
| Rappel Hermes/Kilo nouvelle session | Non prouvé | Absence de traces |
| Reprise crash | Partielle | checkpoint/atomicité non garantis |
| Routeur et quotas | Partiels | modèles non vérifiés, seuils divergents |
| Auto-amélioration | Partielle | held-out, rollback non prouvés |
| Cockpit mobile | Non prouvé en exploitation | #87 draft |
| 24–72h et multi-projets | Non prouvé | aucun test d'endurance |
| Secrets et gouvernance Git | À sécuriser | rotation clé et protections à confirmer |

## C. Dix angles morts
1. **Split-brain Git** : plusieurs chefs modifiant même état/fichier sans OCC ni écrivains distincts -> push conflict, lost-update.
2. **Cron/webhook storm** : un événement déclenche le workflow qui recrée son événement ; quotas épuisés.
3. **Couplage TEL99 ↔ noyau généraliste** : contamination de contexte et risque de régression ; isolation forte et éventuelle extraction ultérieure.
4. **RAM Windows de 16 Go** : plusieurs processus locaux, serveurs MCP et LLM locaux peuvent saturer RAM et causer des timeouts. **Modèles locaux actuellement écartés par l'utilisateur**.
5. **Mocks CI** : unit tests verts ne démontrent pas les API et bus live.
6. **Injection de prompt via Issues/logs/outils** : risque d'exfiltration de tokens et fausses instructions.
7. **Dérive des contrats entre huit PR** : adapter schéma/version/tests de compatibilité ; **il existe déjà un protocole v1 et des schémas**.
8. **Pollution de la mémoire** : contradictions, péremption, GC et contrôle de fraîcheur.
9. **Vérificateur même modèle** : rôles nominalement distincts, biais commun.
10. **PC hors ligne** : Kilo asynchrone opportuniste, pas maillon bloquant des missions purement cloud.

## D. Corrections critiques
- P0 : rotation des secrets exposés, recherche d'autres fuites, scan et .env ignoré ; protections main, interdiction push direct/force-push, checks, droits agent restreints. Certains contrôles GitHub nécessitent une action du propriétaire.
- P1 : intégration ciblée et ordonnée suggérée #79 -> #90 -> #85/#91 -> #88 -> #83/#89 -> #87. **Ordre à réévaluer pour chaque dépendance, sans autorisation de fusion automatique.**
- P1 : healthcheck modèles gratuits, quotas cohérents, retries limités ; réutiliser configuration existante avant d'ajouter config/quotas.yaml.
- P1 : runner Kilo pull Windows, polling proposé toutes les 60 secondes, ne déclarer connected=True qu'après test réel.
- P2 : checkpoint durable, project_id et isolation ; extraction future vers agent-core **à différer si séparation logique suffit**.

## E. Dix optimisations et objectifs proposés
1. Tests déterministes pytest/ruff/jsonschema/ast avant appel LLM : économie annoncée 40–60% tokens **non mesurée**.
2. Routage en cascade de modèle simple → cloud : objectif illustratif 85% réussite avec ≤25% d'appels lourds sur 20 tâches, **non validé** ; modèles locaux mis de côté.
3. Compression de contexte : état/diff/mémoire ciblés ; cible de baisse 50% des tokens **non mesurée**.
4. Unifier logique de #85/#91 au lieu de deux mémoires ; Gemini propose JSONL+index mais il existe un backend KV, éviter refonte non nécessaire.
5. Coupe-circuit après 3 échecs, plafonds par mission ; valeur 3 = hypothèse.
6. Healthcheck modèle et cache 15 min ; cache TTL à mesurer.
7. STATUS.md depuis CI pour lecture mobile rapide ; **ceci n'est pas du temps réel**, afficher date et fraîcheur.
8. Décharger modèle Ollama si RAM sous 3 Go ; **pas applicable actuellement** puisqu'on a suspendu modèles locaux.
9. Skills déclaratifs avec SKILL.md, schema.json et test unitaire ; ne pas inventer un deuxième standard concurrent.
10. Réduire les clients GitHub redondants ; ne pas reconstruire le protocole/bus déjà existant.

## F. Auto-amélioration (Gemini)
- Journal d'erreurs : id, timestamp, projet, agent, Skill, type, input_hash, cause.
- Déclencheur proposé ≥2 erreurs similaires ou demande explicite.
- Branche isolée ; modifications limitées aux instructions Skills, prompts et paramètres de routage ; pas d'édition de sécurité ou d'évaluateur.
- Golden benchmark 15 à 25 tâches figées ; jeu tenu à l'écart du proposant recommandé en complément.
- Gate proposée : score candidat ≥ base +5%, zéro régression de sécurité, tokens ≤110% base. **Chiffres à calibrer par variance et puissance ; n=20 ne garantit aucune significativité.**
- Skill versionné ; Gemini propose un rollback après 2 échecs consécutifs. **Rollback d'un déploiement ne doit pas être automatique sans autorisation** ; quarantaine et PR de réversion.
- Pas de réentraînement des poids du modèle.

## G. Bus GitHub (Gemini)
- GitHub comme point durable asynchrone, événements append-only par mission/agent, outbox + ack, correlation_id, idempotency_key, TTL, hop_count, client Kilo en polling sortant, zéro port ouvert.
- Labels queued→claimed→verifying→done et proposition de claim atomique par label ou branche.
- **CORRECTION** : changement de labels GitHub n'est PAS un CAS transactionnel. Tester réellement un mécanisme atomique (réutiliser verrou KV quand adapté, ou création de ref sécurisée) ; pas de deuxième autorité d'état concurrente.
- Permissions GitHub minimales ; **fine-grained PAT Contents write ne se limite pas nativement à un seul dossier**. Préférer Issues write + Contents read et protections additionnelles.
- Balise [bot-event], hop_count plafonné 6 comme défense anti-boucle ; vérifier les vrais déclencheurs plutôt que faire confiance à un marqueur auto-déclaré.

## H. Responsabilités proposées
- Hermes : plan, routeur, mémoire, Skills ; revue de contrats et de nouvelles procédures.
- Kilo : développement local, UI Windows, validation indépendante, tests lourds.
- OpenHands : exécution cloud, sandbox, CI, programmation et preuves.
- Zones partagées sous revue croisée ; pas de règle arbitraire « Hermes >3 min interdit » sans mesure.

## I. Plan Gemini
1. Sécurité/secret et branch rulesets.
2. Contrôle/rebase/intégration séquentielle des PR, sans autofusion.
3. Contrat versionné, reprise, bus, Kilo PC hors ligne/reconnexion/crash.
4. Golden benchmark, Skills, quotas/cascade, séparation de deux projets, endurance 24 h.
**Jours 1–10, 20 missions et 100% de reprises sont des cibles proposées, sans garantie ni mesure préalable.**

## J. Critiques
- Développer framework généraliste dans dépôt TEL99 peut engendrer de la dette : extraire seulement si nécessaire.
- Trop de PR parallèles, cockpit et MCP avant fiabilité backend.
- Triple environnement x trois rôles = coût ; tester plutôt qu'affirmer qu'un binôme serait toujours meilleur.
- Chartes utiles seulement si traduites en assertions et permissions CI.

## K. Conclusions
1. Goulot = coordination et fiabilité de l'état plus que nombre de modèles.
2. Validation déterministe et routage sobre potentiellement économiques, gains chiffrés à mesurer.
3. Benchmark indépendant pour maîtriser auto-amélioration.
Recommandation finale : geler les nouvelles features, sécuriser, intégrer #79, fiabiliser reprise/bus/mémoire, tester des missions réelles avant de proclamer le produit terminé.

## NOTE DE CONFRONTATION
Écrit d'après le message reçu, non une preuve indépendante. Vérifié directement dans le dépôt : bus.py comporte déjà une machine à états ; memory.py comporte version, schéma et isolation par projet ; #76 est fusionnée. Un second bus, un autre dépôt et la suppression d'outils existants ne doivent pas être imposés par défaut.
