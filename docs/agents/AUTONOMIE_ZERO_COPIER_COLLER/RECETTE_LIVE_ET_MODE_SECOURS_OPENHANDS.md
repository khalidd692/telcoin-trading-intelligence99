# ORDRE DU PROPRIÉTAIRE — PROUVER LA CONTINUITÉ AUTONOME, PRÉVOIR OPENHANDS SEUL
**18 novembre 2026 — test de réception et d'enchaînement, sans autorisation de dépense, de merge ni de déploiement.**
**Dossier source :** docs/agents/AUTONOMIE_ZERO_COPIER_COLLER ; issue maîtresse #94 ; PR documentaire #93.

## Observation et distinction de preuve
L'utilisateur confirme **que plusieurs conversations OpenHands apparaissent sans clic sur le site OpenHands** après les messages transmis sur GitHub. Les réponses de `openhands-ai[bot]` de type `I'm on it!` avec URL Canvas PROUVENT qu'un déclencheur GitHub peut créer une conversation.

Elles NE prouvent PAS que :
- le premier agent a poursuivi sa mission *après* son rapport sans nouvelle mention `@openhands` ou intervention ;
- une tâche B s'est lancée à la suite d'une tâche A au sein du même run ou d'un run automatiquement programmé, en conservant la même mission ;
- une nouvelle session récupère son état tout seule ;
- Hermes Desktop/Kilo Agent Manager reçoivent leurs missions GitHub sans intervention.

**Ne plus écrire « autonomie totale » sur la seule foi d'une nouvelle conversation.** Les étapes ci-dessous établissent le verdict indépendamment.

## TEST A — Vérifier la vraie réception GitHub -> OpenHands
1. Collecter les identifiants des déclencheurs GitHub, l'horodatage, l'acteur, l'événement (issue/comment), et les URLs de conversations créées.
2. Comparer les événements aux conversations. Distinguer `trigger_by_human_comment`, `scheduled_run`, `internal_handoff`, `retry` ou `unknown`.
3. Rendre explicite : nouvelles conversations créées en réaction à PLUSIEURS mentions humaines n'est pas une preuve de boucle autonome.
4. Détecter déclenchements multiples pour le même `mission_id`, corréler à #92, produire garde-fou anti-doublon.

**PASS A** : vraie correspondance événement/ID/run/temps. Sinon BLOCKED, préciser quel journal API manque.

## TEST B — Deux tâches enchaînées pour UNE instruction humaine
1. Partir d'un **unique** ordre utilisateur à partir de #94 ; fixer `mission_id`, nonce et objectif borné **non dangereux** et sans coût payant.
2. Tâche A : analyser un bug reproductible dans un programme Python de démonstration ou un test isolé. Produire artefact A, preuve déterministe et SHA.
3. **Sans second prompt/commentaire humain**, démarrer B après la réussite d'A : correction + tests négatifs/positifs et compte rendu indépendant. Utiliser la même conversation si la plateforme ne possède pas de scheduler autonome ; cela prouve alors uniquement l'enchaînement **intra-session**.
4. Pour revendiquer reprise **inter-session**, démontrer un événement machine / planification ponctuelle explicitement autorisée, ou une session indépendante qui récupère d'elle-même la mission et son état sans mention `@openhands`. Ne pas créer ni activer une automatisation récurrente sans consentement. Si pas disponible, marquer `INTER_SESSION_BLOCKED` sans feindre.
5. Référencer le nombre de déclenchements humains (doit valoir **1**), la timeline, les conversations et journaux, le quota avant/après, les fichiers et tests réellement exécutés.

**PASS B intra-session** = A et B exécutées et vérifiées après un seul déclenchement ; `PASS B inter-session` exige un second exécuteur lancé par un événement non humain autorisé. Sinon PARTIAL/BLOCKED.

## TEST C — « Plus jamais de copier-coller »
Le propriétaire n'intervient plus pour transmettre instructions, comptes rendus ou résultats entre les chefs. La réception des tâches, l'ACK, la déduplication, l'état et les rapports sont gérés par un canal machine (bus existant + GitHub) et un consommateur réellement exécuté.

**PASS C** = mission soumise une seule fois -> au moins deux spécialités effectuent des étapes distinctes -> preuve indépendante -> livrable -> tâche suivante (sans intervention propriétaire) -> mémoire relue en session neuve et sauvegarde. Si des tâches locales attendent un PC hors ligne, le cloud avance les tâches indépendantes.

## PLAN B FORMEL : OPENHANDS GÈRE LE TRAVAIL SI HERMES / KILO NE RÉPONDENT PAS

**DÉCLENCHEMENT DU MODE DE SECOURS :** un chef local ne répond pas faute de pont GitHub réellement fonctionnel, après vérification de l'absence de réponse dans le délai de lease et de l'état de connexion. **Ne pas** lancer simultanément une action Kilo et son remplaçant Cloud : 1 propriétaire par tâche et fencing/CAS obligatoires.

**OpenHands est alors chef d'exécution UNIQUE pour les tâches réalisables dans son sandbox.** Il utilise son équipe EXISTANTE Analyste -> Développeur -> Vérificateur et le code du noyau propriétaire, sur branche isolée, en distinguant les rôles logiques et les outils.

### Ce qu'il peut assumer en mode secours
- Audit, recherche technique, écriture et correction Python/JavaScript, tests et CI cloud, revue indépendante via critères déterministes, ajout de tests et documentation.
- Code portable du routeur des modèles gratuits, mémoire versionnée/isolée, Skills évalués et rollback, contrats d'adaptateurs.
- CLI du noyau personnel, bus FileStore, protocole GitHub, test cloud « pas besoin des clients Hermes/Kilo/OpenHands pour le moteur natif » quand une API de modèle accessible et sûre est disponible.
- Dossiers de preuve, PR draft, suivi de l'issue #94 et progression des tâches non bloquées.

### Ce qu'il ne peut pas prétendre réaliser seul
- Lancer, piloter ou tester réellement l'interface Kilo Agent Manager sur le PC Windows éteint ou inaccessible, et prouver une réception GitHub Kilo native sur cette machine.
- Démontrer un rappel automatique depuis Hermes Desktop sans accès réel à ce runtime. Les tests du noyau hors Hermes sont réalisables sans cela.
- Fournir des ressources cloud permanentes ou modèles « gratuits illimités » sans fournisseur et quotas, ni contourner une rotation de secret ou autorisation humaine.
- Fusionner, déployer en production, modifier droits/secrets, activer cron permanent, effectuer un paiement ou un ordre financier réel/simulé.

### Règle anti-blocage
Une tâche réservée au runtime Windows/Hermes devient `WAITING_LOCAL` et **ne doit pas bloquer** le développement cloud portable indépendant. Créer au besoin une sous-tâche `cloud_portable_substitute` de portée différente, sans falsifier l'acceptation initiale. Avoir un seul responsable de statut et une interface LLM interchangeable. Lorsque le PC revient, le vrai test local reste requis.

### Preuves de mode secours
La preuve attendue est « moteur portable + tests exécutés + artefacts » plutôt que « Hermes/Kilo fonctionnent » si ceux-ci ne sont pas connectés. Le livrable doit pouvoir être importé sur Windows ultérieurement, sans modification du coeur.

## Format obligatoire de rapport dans l'issue #94
```text
TEST_SUITE: AutonomousContinuation-V1
TRIGGER: <issue/comment ID + timestamp>
HUMAN_TRIGGER_COUNT: <entier>
OPENHANDS_CONVERSATION_IDS: <liens>
TASK_A: <SHA, tests, artefacts>
TASK_B: <SHA, tests, artefacts>
AUTO_NEXT_STEP: PASS|FAIL|BLOCKED
INTER_SESSION_RESUME: PASS|FAIL|BLOCKED
GITHUB_BRIDGE_HERMES: PASS|FAIL|BLOCKED
GITHUB_BRIDGE_KILO: PASS|FAIL|BLOCKED
FALLBACK_OPENHANDS_ONLY: PASS|FAIL|BLOCKED
CURRENT_FREE_QUOTA: <valeur sourcée + timestamp ou UNKNOWN>
NEXT_SAFE_TASK: <task_id>
HUMAN_APPROVAL_REQUIRED: <uniquement opérations sensibles>
```

**Prendre les prochaines tâches admissibles selon BACKLOG.json et l'état réel des PR ; ne pas répondre avec un prompt que le propriétaire devrait copier.**
