# Relais OpenHands / Hermes — source A→B manquante

Date : 23 novembre 2026. Statut global : **BLOQUÉ_SOURCE_ORIGINE**.
Cette branche publie un dossier de récupération, **pas la solution a5112413**.
Aucun nouvel appel modèle, démonstration, superviseur, merge ou suppression de worktree.

## Entrée et provenance
- Ordre intégral archivé : sources/issue94-7089282477.json.
- Rapport antérieur archivé : sources/issue94-7089256513.json.
- Branche documentaire : handoff/a5112413-source-recovery-20261123.
- Base GitHub observée : 2671228398ecfc18e506332bb9d5011266ceedd5 (main).
- Worktree inspecté : C:\Users\sabri\Desktop\tel99-kilo-cli-bridge.
- HEAD local : b57806f4786a4551b4c2d8e63c530d1328e226ae, branche feat/kilo-cli-native-bridge, piste distincte PR #158.
- Commit recherché : a5112413 (préfixe uniquement). **SHA complet, arbre, parents et diff inconnus.**
- GitHub renvoie HTTP 422, « No commit found for SHA: a5112413 ».
- Le dépôt partagé de ce worktree et quatre dépôts locaux ciblés ne résolvent pas ce commit.
- Seule distribution WSL observée hors sandbox : docker-desktop. Aucune distribution Linux utilisateur observée.
- Docker CLI présent, démon Docker indisponible sur npipe:////./pipe/docker_engine.
- Aucun outil de terminal Cloud attaché n'est exposé dans cette session. La liste des tâches locales ne donne pas accès au système de fichiers Linux d'origine.
- Les trois modifications locales préexistantes sont préservées ; leurs empreintes sont dans evidence/working-tree-preserved.json. Elles ne font pas partie de cette livraison.
- Aucun bundle/patch/code A→B d'origine n'a pu être produit : ses objets Git et preuves ne sont pas accessibles. L'archive locale de ce dossier est seulement un export du relais et de ses constats.

## Inventaire de transférabilité
**PROUVÉ dans cette session**
- Lecture intégrale du mandat et du rapport antérieur, #60/#61 et quatre archives Smart View.
- Identité du checkout Windows, absence de résolution du commit dans les dépôts ciblés, réponse négative de GitHub.
- Documentation Windows du socle déjà publié : start-agents.ps1 et docs/agents/AUTONOMY_RUNBOOK.md. Le lanceur inspecté n'expose pas --local-code.
- Cinq runs GitHub réussis existent pour b57806f4 ; ils concernent PR #158 et **ne valident pas a5112413** (evidence/pr158-workflows.json).
- Création de ce dossier sans modification des trois fichiers utilisateurs.

**NON TESTÉ / rapporté seulement** — source : commentaire 7089256513
- A acceptée à 01:25:24.050 UTC : modification d'une tâche héritée sans identifiant.
- B acceptée à 01:25:41.979 UTC : UTF-8 illisible traité comme JSON invalide.
- Enchaînement A→B, base rouge/candidat vert dans Docker, arrêt après reçu A, reprise puis replay à zéro appel.
- 1 129 tests dont 31 ignorés, Docker/Node/PowerShell ; aucune sortie brute ni configuration récupérée.
- Qwen2.5-3B / llama.cpp et coût API annoncé 0 $. Ne pas transformer cette annonce en mesure indépendante.
- Démonstration sous Linux, PowerShell sous Linux compris ; Windows natif et Windows+WSL2 restent NON TESTÉS.
- Une fonction Python par mission ; aucune preuve que les 12 agents sont pleinement autonomes ; aucune surveillance permanente démontrée.
- Candidat et tests annoncés dans le même conteneur Docker : frontière insuffisante face à un candidat hostile. Ne pas utiliser ce périmètre sur un projet réel avant décision explicite.

**BLOQUÉ tant que la source manque**
- Publication du SHA exact a5112413 ; extraction de son parent/base, arbre, patch et tests.
- Nom et chemin exacts de son superviseur --local-code, runner llama.cpp, GGUF/config et SHA256 du modèle.
- Schémas CODE, registre approuvé/hash, vérificateur indépendant, chemins mémoire/STOP/reçus.
- Récupération des candidats/diffs/empreintes/journaux/reçus A/B, preuve replay et coûts.
- Commande exacte de lancement/STOP/reprise de **cette** démonstration. Aucune commande inventée ici.
- Dépendances et versions Python/Node/PowerShell/Docker de cette solution : verrouillés par la source à récupérer.

## Ordre de lecture et prochaine action
1. WINDOWS_POWERSHELL.md : prérequis et diagnostics sans modèle.
2. RECUPERATION_ORIGINE.md : export/push depuis le checkout qui possède réellement a5112413.
3. DEPANNAGE.md : diagnostics et corrections sans destruction.
4. REPRISE.ps1 : contrôle du paquet, recherche du commit ou import d'un bundle **complet** authentifié.
5. evidence/ et sources/ : pièces et limites ; SHA256SUMS.json pour contrôler chaque fichier livré.

OpenHands est l'intégrateur prioritaire. Hermes reprend uniquement après libération explicite de la tâche par OpenHands ; jamais simultanément. Réutiliser les rôles, mémoire, contrats et superviseur existants. Ne pas retoucher PR #158 ni relancer la mission C historique REJECTED. Publier sur #94 TASK_ID / STATUS / SOURCE_SHA / TESTS / EVIDENCE / NEXT_TASK. Un commentaire n'est pas un ACK de réception ni une exécution.

Le prochain atelier doit **d'abord récupérer l'export d'origine** depuis le stockage ou la session Linux déjà existante, sans demander de nouvelle inférence Codex. Si l'environnement d'origine n'est plus récupérable, conserver BLOQUÉ_SOURCE_ORIGINE. Ne pas reconstruire la solution pour masquer la perte.
