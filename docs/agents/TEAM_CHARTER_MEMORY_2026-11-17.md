# CHARTE DURABLE — COORDINATION DES TROIS ÉQUIPES IA
Date : 2026-11-17
Statut : instruction de coordination du propriétaire, **non déployée**, à ingérer dans les mémoires persistantes de chaque équipe.
Dépôt : khalidd692/telcoin-trading-intelligence99
Source : audit GitHub du 17 novembre 2026 ; issue maîtresse #67 ; PR #76 fusionnée et PR #85, #87–#89 ouvertes.

## 1. Finalité

Nous construisons **notre propre produit multi-agents généraliste** et exploitable sur plusieurs projets. Hermes, Kilo Crew et OpenHands sont trois environnements/outils qui contribuent au produit ; il n'est **pas obligatoire** de les connecter tous automatiquement ni de les faire travailler sur la même tâche. Ne pas reconstruire ce qui fonctionne déjà, ne pas multiplier les agents sans besoin prouvé.

## 2. Responsabilités principales (« owner » fonctionnel)

- **Chef Hermes : intelligence et capitalisation.** Routeur/modèles gratuits, sélection et fallback, mémoire et provenance, Skills, évaluation des résultats, amélioration contrôlée. Responsable fonctionnel de `scripts/agents/intelligence/` et du contrat mémoire, sous réserve de revue croisée pour toute modification partagée.
- **Chef OpenHands : exécution et autonomie cloud.** Orchestrateur cloud, quotas gratuits, exécutions avec PC éteint, programmation contrôlée, reprise/idempotence, journal des vrais runs et garde-fous runtime. Responsable fonctionnel de `scripts/agents/automation/`, `.plugin/` et intégration des automatismes, sans toucher au produit TEL99.
- **Chef Kilo : produit local et contre-vérification.** Kilo Crew sur Windows, UI locale, persistance des workspaces/livrables, tests de lancement, validation indépendante, robustesse locale. Responsable de son dossier local Kilo Crew ; **ne présumez pas qu'il est branché au bus GitHub**.
- **Coordination générale / validation croisée :** protocole/bus `scripts/agents/protocol/`, `memory/`, `.github/workflows/`, garde-fous et tout fichier partagé. Un changement dans ces zones exige de prévenir les autres chefs et de demander une revue indépendante, pas un développement parallèle concurrent.

La propriété fonctionnelle est une **règle de travail à formaliser**, pas une garantie GitHub déjà imposée : aucun CODEOWNERS standard n'a été trouvé lors du contrôle.

## 3. Faits confirmés et limites

- La PR #76 a fusionné une pile multi-agents commune sur `main` le 16/11.
- Le dépôt possède un protocole v1 et des adaptateurs ; dans `scripts/agents/protocol/adapters/kilo.py`, **Kilo est `connected=False`**. Ne jamais prétendre que les trois plateformes échangent des missions en direct tant que ce point n'est pas démontré.
- OpenHands limite ses missions internes à une simultanément et conserve des conditions de sécurité dont `dry_run` par défaut ; **ce verrou n'est pas un verrou global sur Hermes et Kilo**.
- **Risque de chevauchement** : PR #85 touche `scripts/agents/intelligence/memory.py` et l'adaptateur Hermes, bien que la mémoire soit la responsabilité Hermes. PR #87 construit un cockpit OpenHands distinct de l'UI Kilo Crew ; différencier clairement « lecture cloud » et « pilotage local » sans dupliquer le produit. PR #88 et #89 changent le même workflow GitHub `.github/workflows/tel99-agent-team-audit.yml` ; revue d'intégration requise avant fusion.
- **Protection incomplète** : la liste `PROTECTED_BRANCHES` de `scripts/agents/automation/policy.py` protège `main`, `master` et les branches de données ; elle n'inclut pas explicitement `codex/tel99-quant-terminal`. Corriger/valider ce contrôle avant d'autoriser des écritures automatisées.
- **Incident de sécurité prioritaire** : une clé d'accès OpenHands a été publiée en clair dans la description de PR #88. **Ne pas recopier la valeur**. Le propriétaire doit la révoquer/faire tourner immédiatement et rechercher d'autres copies exposées. Une suppression de la description ne répare pas une clé compromise.

## 4. Règles opérationnelles communes

1. Chaque chef garde le pilotage de ses propres agents. Les autres chefs ne leur attribuent pas directement de missions.
2. Avant chaque tâche : vérifier si la capacité existe, consulter ce document et #67, identifier le propriétaire du composant, ses PR ouvertes et le dossier/branche de travail.
3. Une seule équipe propriétaire écrit un composant partagé à la fois. Les autres examinent/testent indépendamment et rendent PASS / FAIL / BLOCKED avec preuves.
4. Les branches et espaces sont isolés. Aucun push sur `main`, branches produit, données ou évaluation ; aucun merge ni déploiement sans autorisation distincte.
5. Ne pas exécuter d'ordres financiers réels ou simulés ; n'utiliser que des modèles et quotas gratuits vérifiés ; respecter secrets, permissions et budgets.
6. Ne jamais confondre **tests unitaires**, **démo hors ligne** et **exécution cloud/locale réellement prouvée**. Rapporter les limites.
7. Ne pas créer de second routeur, de seconde mémoire ou de second orchestrateur si le composant existant répond au besoin. Différencier UI locale Kilo / cockpit d'observation cloud OpenHands.
8. Les modèles IA ne changent pas leurs poids grâce à une consigne ; **la « mémoire » recherchée est un stockage durable consulté au démarrage et à chaque nouvelle mission**.

## 5. INSTRUCTION OBLIGATOIRE DE MÉMOIRE (à exécuter par chaque chef)

Dans votre environnement respectif :
- Enregistrer un résumé fidèle de cette charte **dans votre mécanisme de mémoire persistante existant**, avec `source` = chemin de ce document, `date` = 2026-11-17, `version` = 1, périmètre/projet, statut `validated_by_owner_in_chat` et lien issue #67.
- Conserver séparément **la mémoire commune** (règles et frontières) et **la mémoire privée par projet**, sans secrets dans le dépôt.
- Depuis **une nouvelle session / un nouveau processus**, retrouver cette connaissance **sans la recoller dans le prompt** ; restituer ses responsabilités et les deux principaux chevauchements ; fournir les chemins/IDs et les journaux de lecture.
- Si le stockage inter-session ne fonctionne pas, déclarer **BLOCKED**, expliquer la limite et proposer la correction minimale ; ne pas prétendre que l'inscription dans ce fichier rend l'agent automatiquement capable de s'en souvenir.
- Répondre au coordinateur par : `ACK / memory_written / memory_recalled_in_fresh_session / source / proof / conflicts_remaining`. Ne pas démarrer de nouveaux travaux non demandés.

## 6. Liens et portée

- https://github.com/khalidd692/telcoin-trading-intelligence99/issues/67
- https://github.com/khalidd692/telcoin-trading-intelligence99/pull/76
- https://github.com/khalidd692/telcoin-trading-intelligence99/pull/85
- https://github.com/khalidd692/telcoin-trading-intelligence99/pull/87
- https://github.com/khalidd692/telcoin-trading-intelligence99/pull/88
- https://github.com/khalidd692/telcoin-trading-intelligence99/pull/89

Document de coordination **additif uniquement**, sur branche isolée et PR draft. Il ne modifie ni code ni production.
