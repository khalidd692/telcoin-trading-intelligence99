# Mémoire durable — coordination OpenHands (v1)

- Date : 2026-11-17
- Version : 1
- Périmètre : OpenHands Cloud / produit multi-agents personnel ; TEL99 est un projet utilisateur, pas l'ensemble du produit
- Source primaire : `docs/agents/TEAM_CHARTER_MEMORY_2026-11-17.md` de la branche `coordination/agent-team-boundaries-memory-20261117`, PR #90, HEAD de référence `cb8e73481d7a0203d7386fb9bcd9ae5941f3d0ec`
- Source de mission : issue #67 — https://github.com/khalidd692/telcoin-trading-intelligence99/issues/67
- Provenance : ordre officiel du propriétaire du 17 novembre 2026 dans la conversation, confirmé par la charte GitHub
- Statut de la consigne : `validated_by_owner_in_chat`
- Statut d'activation : copie de dépôt proposée par PR en brouillon ; **chargement automatique dans un nouveau sandbox OpenHands non vérifié**
- Données sensibles : aucune clé ni aucun jeton ne doit être copié ici

## But commun

Construire un système personnel d'agents IA généraliste, autonome sous contrôle, multi-projets, capable de développer, corriger et tester des applications, d'exécuter des missions utiles, de conserver des connaissances vérifiables entre missions et d'améliorer ses méthodes/Skills par évaluations mesurables. Hermes, Kilo et OpenHands sont trois environnements complémentaires ; ils ne doivent pas être entièrement interconnectés pour contribuer au même produit.

## Responsabilités et limites

- **OpenHands — exécution cloud (chef de cet environnement).** Missions et délégation des sous-agents cloud ; quotas gratuits et budgets ; automation événementielle/manuelle/programmée uniquement si autorisée ; garde-fous runtime ; verrouillage, déduplication, reprise et journaux ; preuves d'exécution PC éteint. Propriétaire fonctionnel : `scripts/agents/automation/`, `.plugin/`, intégration d'automation. Ne pas reconstruire le routeur Hermes ou l'interface locale Kilo.
- **Hermes — intelligence et mémoire fonctionnelle.** Routeur et sélection des modèles gratuits ; connaissances, provenance, Skills, capitalisation, mémoire commune, amélioration contrôlée et évaluations. Propriétaire fonctionnel : `scripts/agents/intelligence/` et contrat mémoire, avec revue croisée si partagé. OpenHands n'a pas autorité pour réécrire son routeur ou son adaptateur sans coordination.
- **Kilo Crew — poste Windows, livrables et validation locale.** Cockpit/Agent Manager local, missions locales, fichiers produits, robustesse du lancement et vérification indépendante. Ne pas reconstruire son interface depuis OpenHands.
- **Partagé — revue croisée préalable.** `scripts/agents/protocol/`, `memory/`, `.github/workflows/`, garde-fous et contrats d'intégration. Une seule équipe écrit un composant partagé à la fois.

## Préserver et connaître les travaux

- PR #76 fusionnée : équipe, plugin, orchestrateur, protocole et garde-fous. Réutiliser.
- PR #79 : correctifs d'autonomie cloud (confirmation sans opérateur, lecture paginée des événements), non supposés intégrés tant que la fusion n'est pas vérifiée.
- PR #85 : mémoire inter-runs durable et modifications de `scripts/agents/intelligence/memory.py` et de l'adaptateur Hermes ; revue Hermes obligatoire avant intégration.
- PR #87 : cockpit de consultation **cloud** ; distinct de l'interface **locale** Kilo, sans bouton live fictif.
- PR #88 et #89 : toutes deux touchent `.github/workflows/tel99-agent-team-audit.yml` ; vérifier incompatibilités et demander revue avant merge.
- Kilo : adaptateur `scripts/agents/protocol/adapters/kilo.py` déclaré `connected=False` lors de l'audit ; ne pas prétendre que les trois outils sont interconnectés en direct.
- `scripts/agents/automation/policy.py` : protection des branches produit insuffisante au 17/11 ; ajouter/revoir `codex/tel99-quant-terminal` avant toute écriture automatique autorisée.

## Règles avant toute nouvelle mission

1. Lire cette mémoire, la charte de PR #90 et l'issue #67 ; vérifier les versions, PR et branches actuelles.
2. Déterminer qui possède le composant ; ne pas modifier une zone Hermes/Kilo ; proposer revue croisée pour tout partage.
3. Travailler sur branche isolée ; aucun merge, déploiement, changement de production ou de permissions sans accord séparé.
4. Modèles exclusivement gratuits vérifiés, quotas réels et budgets plafonnés ; aucun ordre financier réel ou simulé.
5. Pas de reconstruction, d'agent ou d'automation supplémentaire sans besoin démontré ; préférer réemploi, tests indépendants et preuves sources.
6. Séparer `tests hors ligne`, `runs cloud réels` et `persistance inter-sessions` ; refuser de déclarer PASS sans trace vérifiable.
7. **Sécurité urgente** : une clé API OpenHands a été exposée dans la description de PR #88 (d'après la charte). Ne jamais reproduire la valeur. La rotation/révocation doit être confirmée explicitement ; nettoyer les copies ne suffit pas.

## Procédure de contrôle de mémoire (à faire dans une nouvelle session réelle)

Démarrer un **nouveau sandbox / nouvelle conversation OpenHands**, sans coller cette charte ni son contenu. Vérifier dans les journaux que la session a chargé `.openhands/memory/MEMORY.md` et suivi ce renvoi vers ce fichier, ou qu'une clé KV durable documentée le contient. Demander : but final, responsabilité OpenHands, périmètres Hermes/Kilo, composants interdits, règles avant modification. Consigner l'identifiant de session, l'identifiant/version du stockage et les extraits de lecture. Si une seule étape manque, retourner `BLOCKED` ; la présence du fichier sur GitHub **ne démontre pas** à elle seule la mémoire autonome.
