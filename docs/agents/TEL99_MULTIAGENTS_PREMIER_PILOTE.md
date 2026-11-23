# TEL99 — premier travail réel entre agents (branche pilote)

Ce pilote réutilise intégralement le superviseur local Windows déjà validé,
le registre de missions, les contrats SHA-256, Ollama et le vérificateur Docker.
Il n'installe **aucun nouveau superviseur**, ne démarre aucun service, ne
réclame ni API payante ni clé, ne fusionne rien et ne négocie pas.

## Les 12 profils ne sont pas 12 exécutants prouvés

L'inventaire canonique du dépôt est dans scripts/agents/team_config.py :
3 profils marqués ACTIVE (tel99-analyst, tel99-dev, tel99-verifier),
9 spécialités RESERVED. L'inventaire ne prouve pas à lui seul que des
processus distincts ont travaillé.

Le mode Team teste la chaîne explicite suivante :

1. **tel99-analyst** — une vraie génération Ollama locale,
   lecture seule de l'objectif autorisé et de la fonction source
   (Gemma 4 E4B), sans outil d'exécution ni permission d'écriture.
   Un avis limité à 1200 octets est conservé avec son SHA-256.
2. **tel99-dev** — le worker de réparation Python existant,
   avec le modèle sélectionné d'après les preuves Docker antérieures
   (Gemma 4 pour 01/02/03 ; Qwen Coder 7B pour 04/05).
   L'avis de l'analyste est inséré comme DONNÉE NON FIABLE dans
   le prompt, sans changer la fonction/les tests/le sandbox approuvés.
   Le worker émet un reçu de passage analyste -> développeur.
3. **tel99-verifier** — rôle d'évaluation indépendant matérialisé par
   le **vérificateur déterministe Docker existant** : base rouge,
   candidat vert, fonction unique et source/test épinglés. Ce n'est
   PAS un troisième appel LLM ni une validation par le développeur.
   Sans reçu analyste authentique et cohérent, même du code apparemment
   correct est rejeté.

La mémoire inter-sessions enregistre les empreintes des rôles et du
correctif uniquement après ACCEPTED. Les anciens tests et le mode
Evidence restent inchangés.

## Démarrer : une commande initiale dans PowerShell

Une fois la branche pilote récupérée dans un worktree séparé :

~~~powershell
$checkout = "$HOME\Desktop\TEL99_TEAM_PILOT_20261123"
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Team
~~~

Le script lance d'abord les tests Python hors ligne (y compris les nouveaux
cas de refus), relit les deux anciens dossiers de preuve du 23 novembre,
crée un registre neuf de 5 missions scellées avec le champ team, puis lance
le superviseur TEL99 existant une seule fois. Durée limite : 1 heure.
Résultats et checkpoints dans un nouveau dossier TEL99_AUTONOMIE_NUIT_*
du Bureau. Ne pas écraser les campagnes déjà validées.

Mode de vérification sans génération :

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Test
~~~

**Résultat encore attendu** : une campagne Team réelle où les reçus
analyst/dev existent et le contrôle Docker indépendant accepte (ou refuse
avec diagnostic). L'ancienne réussite 5/5 n'est pas une preuve de
coopération multi-agents : cette nouvelle expérience est distincte.

**Non prouvé par ce pilote** : activation automatique des neuf autres
profils, découverte d'issues GitHub inédites, PR ouvertes par les agents
eux-mêmes, bascule de modèle pendant une même mission ou reprise après
crash incertain. Ces travaux sont les étapes suivantes, avec de nouveaux
mandats authentifiés. Ne jamais déclarer le système complètement autonome
avant cette recette de bout en bout.

Arrêt : utiliser le mécanisme STOP de night_lab_20261123.py et le chemin
exact de la session, depuis une seconde fenêtre. Ne pas supprimer les
checkpoints et ne pas rejouer automatiquement un worker marqué RUNNING.
