# Diagnostic opérationnel et mission Codex — nuit du 18 novembre 2026

**Sources de vérité :** [plan maître 4 IA et audits (#90)](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/90), [backlog 20 tâches (#94)](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94), [PR documentaire #93](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/93), [consignes Codex (#101)](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/101). **Photographie horodatée au 18/11**, pas un état live. Chaque chef doit revalider les SHA, runs, leases, quotas et commentaires avant action.

**Objet :** terminer le noyau d'agents **possédé et portable** du propriétaire, pas enrichir indéfiniment les clients Hermes/Kilo/OpenHands. Aucune refonte, aucun nouveau bus ou moteur concurrent. Codex doit travailler sur les blocages restant **après déduplication**, et vérifier les livrables des autres.

## 1. Ce qui est réellement observé et ce que ça prouve

| Source | Fait observé | Preuve/limite |
| --- | --- | --- |
| `main`, historique récent | nombreux commits « Refresh published TEL/USDT market report [skip ci] » et workflows TEL market monitor/evaluation ; pas de fusion visible des PR agent-core #92/#95/#96/#97/#99 | les publications TEL fonctionnent, **pas** preuve de la finition agent-core |
| PR #90 | quatre audits Claude/Grok/Gemini/DeepSeek + registre + plan maître ; **draft** | avis d'audit, avec constats à reproduire, pas correctifs en production |
| PR #92 | reprise cloud anti-duplication, correctifs #79, recette pilote inactive ; **draft** | chevauche #79, #89 et `orchestrator.py` de #99 |
| PR #95 | CLI native + providers + tests hors ligne ; **draft** | fournisseur scripté et serveur HTTP de test ≠ fournisseur gratuit réellement joignable |
| PR #96 | handoff/ACK/verdict/dédup ; **draft** | doit être intégré au vrai chemin de mission, réception Windows/Hermes non prouvée par cette PR |
| PR #97 | CAS de mission/état ; **draft** | séparer tests de stockage FileStore Linux et vrai usage Windows/cloud |
| PR #99 | correction du faux PASS dans `verify_outcome` ; **draft** | partage `orchestrator.py` et les tests avec #92 ; CI verte ≠ correctif combiné validé |
| issue #102 | Kilo rapporte 6 tests pytest verts sur workspace isolé ; **deux commentaires RESULT** pour même mission | preuve d'une exécution de tests, **pas** de correction ni de première mission native LLM complète |
| issue #94 | Kilo signale plusieurs démarrages du superviseur Windows et une mission publiée deux fois ; corrigés annoncés sans tests de concurrence exclusifs prouvés sur GitHub | **P0** vérifier verrou inter-processus, propriétaire/PID, lease/fencing, crash, reprise et publication idempotente |
| issue #94 | Hermes annonce Z-03 PASS, 25 tests ; receiver Windows PASS (9+12 tests), I-01 BLOCKED, absence de sonde modèle gratuit autorisée | progrès annoncés, mais les SHA `0395460b40c9d123` et `livraison-20261118` ne sont **pas des commits retrouvés dans ce dépôt** ; exiger lien de code/artefacts et vérification indépendante du vrai trajet REQUEST→ACK→RESULT |
| issue #94 | OpenHands a répondu « I'm on it » avec lien conversation cloud pour la mission nocturne | **réception prouvée**, résultat final non attesté par cet ACK seul |
| issue #94 | Réponse Codex : « To use Codex here, create an environment for this repo » | **blocage réel de prérequis Codex Cloud**, lien : https://chatgpt.com/codex/cloud/settings/environments |
| PR #95 | Réponse à `@codex review` : limite de code review atteinte | quota **code review** distinct du budget Codex développement ; ne pas relancer cette commande |
| PR #88 | jeton anciennement exposé, révocation non attestée | **AWAITING_HUMAN** propriétaire pour invalidation/rotation de secret ; aucun secret reproduit ou utilisé |

### Conflits techniques confirmés par listes de fichiers changés

- **#79 ↔ #92 ↔ #99** : `scripts/agents/automation/orchestrator.py` et `tests/test_cloud_autonomy_e2e.py`.
- **#89 ↔ #92** : `pilot_recipe.py`, `test_automate_pilot.py`, documentation pilote et workflow audit.
- **#85 ↔ #95** : `.github/workflows/tel99-agent-team-audit.yml`.
- **#85 ↔ #89 ↔ #92 ↔ #95** : workflow `.github/workflows/tel99-agent-team-audit.yml` (chevauchement multi-PR).
- **#96 ↔ #97** : pas les mêmes fichiers, mais intégration fonctionnelle handoff/store/bus à tester ensemble.
- **#90, #93, #101** : directives de branches **documentaires** différentes ; #101 cible la branche #93, sans merge implicite sur `main`.

L'absence de conflit de fichier ne prouve pas l'absence de conflit sémantique. Codex devra construire une **branche d'intégration de vérification isolée**, établir une matrice de compatibilité, exécuter tous les tests au SHA combiné et proposer l'ordre de fusion **au propriétaire**, sans fusionner.

## 2. Missions Codex par ordre strict (pas de tâches supplémentaires inventées)

**C-01 / P0 — Triage sécurité / véracité** : reprendre les preuves du plan #90, identifier un vrai défaut résiduel, contrôles anti-injection et d'exécution arbitraire des missions GitHub ; priorité au danger faux PASS / code non fiable / accès secrets. Audit indépendant de PR #95 et #96/#99. Test négatif : un résultat FAIL ne peut devenir `MISSION_ACCEPTED`.

**C-02 / P0 — Correctif collision Kilo** : examiner les deux commentaires #102, les démarrages rapportés dans #94, les preuves d'identité de processus ; contacter le chef Kilo dans #94 pour la correction **sur son workspace**. Codex n'a pas accès à `scripts/night_supervisor.py` local hors dépôt sauf preuve du contraire. **Ne jamais prétendre corriger Windows à distance avec un commentaire**. Si le code Kilo n'est pas accessible à Codex, marquer BLOCKED_SOURCE_UNAVAILABLE et produire spécification/tests de concurrence à appliquer par Kilo (vrai 2 processus, at-most-one-run, at-most-one-RESULT, crash/restart, deadline conservée, PID vérifié avant kill).

**C-03 / P0 — Intégration PR cloud** : comparer #79/#92/#99 et #96/#97. Identifier les recouvrements réels ; exécuter les tests ensemble en isolation. Confirmer que reprise cloud ne double jamais une conversation, que state CAS ne perd pas une mise à jour, et que le verdict rejette les fausses preuves. OpenHands est auteur de l'orchestrateur : Codex fournit audit/tests/PR distincte si claim valide, **pas une implémentation concurrente du même fichier**.

**C-04 / P1 — Contrôles inter-runtime** : Kilo Z-01 est une exécution de tests locale, pas encore le livrable F-01. Hermes Z-03 nécessite une preuve reproductible dans ce dépôt ou artefact horodaté accessible. Vérifier REQ→ACK→RESULT→vérification indépendante→mémoire nouvelle session→reprise, sans copier-coller, sans secret et avec projets isolés.

**C-05 / P1 — Qualité des modèles et des Skills** : utiliser les tests déterministes disponibles, refuser un vrai appel si coût/quota non vérifié, exiger le fournisseur cloud gratuit réel ou BLOCKED ; pas de réactivation locale, pas d'auto-promotion de Skill sur 3 observations seulement, rollback et jeux held-out.

**C-06 / P2-P3 — Consolidation du produit** : compatibilité des PR documentation/code, tests finaux G0–G7, cockpit sourcé si déjà existant, instructions une commande. Aucun « produit terminé » sans un vrai livrable qui tourne hors Hermes/Kilo/OpenHands.

## 3. Règles pour cette nuit : travailler si possible, sinon arrêt propre

- Fenêtre **bornée** déjà décidée dans la discussion #94 (les équipes ont des horizons particuliers) ; ne pas prolonger le deadline après reboot. **Ce document ne crée ni nouvelle session ni cron.**
- **Une mission cloud coûteuse active au maximum**, pas de nouveaux runs si équivalent déjà actif ; quota OpenHands `remaining >=12/20` mesuré, free-only, plafond par run existant ; si quota inconnu, STOP cloud.
- Une seule instance Windows par superviseur ; si suspicion d'instances multiples, diagnostic lecture seule et mise en sécurité avant toute reprise. Ne pas forcer le kill de PID non vérifié.
- Codex **pas lancé aujourd'hui par ce document** : une vraie session Codex connectée/Goal et un environnement cloud publié sont nécessaires ; `@codex review` indisponible par quota propre. Un Goal peut enchaîner des tâches dans le même thread jusqu'à limite de budget, **pas** contrôler de lui-même Hermes/Kilo/OpenHands ou rester vivant sans exécuteur.
- Pour tâche admissible, publier dans #94 : `TASK_ID OWNER STATUS CLAIM SHA BASE PR TESTS NEGATIVE_PROOF QUOTA NEXT_TASK`. Puis passer à la suivante **sans nouveau prompt** dans la session et le budget existants.
- Les fichiers de ce dossier et les commentaires GitHub sont de la **documentation/passation**, pas une preuve de réception des runtimes locaux.
- **Aucune dépense, fusion, déploiement, activation permanente, modification de permissions, exécution financière réelle ou simulée, divulgation de secret, force-push, écriture sur branches TEL99 protégées**.

## 4. Actions non automatisables à ce stade — regroupées pour le propriétaire

1. **Environnement Codex Cloud** : ouvrir https://chatgpt.com/codex/cloud/settings/environments sur web/desktop, créer/publier un environnement pour `khalidd692/telcoin-trading-intelligence99`, limiter la portée du dépôt et ne fournir aucun secret dans GitHub ; puis ouvrir **une session Codex** sur la branche de PR #101 et activer `/goal` du runbook si le client le supporte. La réponse du bot GitHub a précisément confirmé l'environnement manquant. Une publication de fichier ne peut pas effectuer ces étapes d'authentification à la place de l'utilisateur.
2. **Ancien secret OpenHands** : invalider/faire tourner le jeton chez le fournisseur et confirmer la révocation **sans publier sa valeur**. Les travaux de lecture/tests isolés peuvent continuer mais aucune automation utilisant ce secret ancien.
3. **Merges, protections, cron permanent, dépense** : attendre la preuve de tests intégrés et la validation explicite du propriétaire. Des travaux nocturnes ponctuels déjà autorisés ne donnent pas une autorisation illimitée.

## 5. Critères pour considérer la nuit productive

- **Progrès** : un correctif P0 avec reproduction d'un bug avant/après et CI au SHA, ou une vérification indépendante réfutable d'une PR, ou une preuve runtime d'un trajet entre agents. Pas le nombre de commentaires.
- **Dédoublonnage** : zéro nouvelle mission doublée ; interdiction d'une deuxième réponse RESULT pour le même `mission_id` après garde idempotente.
- **Sécurité** : 0 secret dans logs/public, 0 dépenses, 0 nouveaux accès arbitraires.
- **Reprise** : checkpoint avec TASK_ID, état actuel, preuve, autorité de claim, prochain auteur ; déclarer BLOCKED plutôt qu'inventer une activité.
- **Fin du programme** : critères G0–G7 de `CRITERES_DE_FIN.md`, non prouvés par cette seule nuit.

---
Rédigé après inspection directe des fichiers d'audit sur la branche #90, des fichiers changés dans les PR, des Issues #94/#102, des commentaires Hermes/Kilo et des runs GitHub Actions. Toute affirmation relative aux programmes Windows provient de leurs rapports GitHub : leur processus local n'est pas directement inspectable par cette session ChatGPT.
