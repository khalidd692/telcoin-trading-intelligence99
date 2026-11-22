# Reprise de l’autonomie TEL99 sous Windows

La préparation part de `main` au SHA `5d0567faef515979ff74ec29e008522e3585030e`, qui contient #153 et #156. La recette de développement suit le mandat de reprise de #123. Les issues #94 et #123 servent à la coordination. [Mandat de reprise](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/123#issuecomment-7084046524)

## Au retour devant le PC

Ouvrir PowerShell dans un worktree neuf au SHA de la PR de préparation après ses contrôles. Garder les worktrees et les registres existants. Lancer le diagnostic une fois.

```powershell
pwsh -NoProfile -File .\start-agents.ps1 -Action DIAGNOSTIC
```

Le JSON indique l’heure UTC, les versions trouvées, les worktrees et modifications visibles, les emplacements d’état et les marqueurs STOP. `BLOCKED` et le code de sortie 2 signifient qu’une capacité nécessaire reste à attester. Avec un mandat machine frais et épinglé, `-GitHubIssue`, `-MandateComment` et `-MandateSha256` ajoutent les lectures GitHub. Ajouter `-Campaign` pour un mandat de campagne texte. Le diagnostic reste en lecture seule et la présence d’un binaire constitue un inventaire.

Inspecter le worktree historique `C:\Users\sabri\projects\tel99-ps-receiver-fix` en lecture seule. Si des changements ou suppressions y sont visibles, conserver une copie de ses fichiers, diffs et états dans un espace privé avant intervention. Les états A/B historiques et les preuves de la mission Hermes C `REJECTED` restent archivés. [État historique et preuves à préserver](AWAITING_HUMAN.md)

## Choisir un exécuteur

| Ordre | Fonction documentée | Preuve exigée sur le poste ou le compte |
| --- | --- | --- |
| 1. Kilo Agent Manager | Extension VS Code, `agent_manager` pour lister les sessions gérées et cibler un prompt, worktrees dédiés. L’acceptation d’un prompt précède sa réception et son exécution effectives. Le CLI `kilo run` fournit un autre chemin avec des événements JSON. | `WINDOWS_PENDING` pour la version, les IDs des sessions, le raccord GitHub, l’ACK natif, le travail outillé et ses permissions. Vérifier le catalogue et le solde de requêtes gratuites. La limite publique annoncée est de 200 requêtes gratuites par heure et par IP. Vérifier aussi le petit modèle et les tâches d’arrière-plan. [Agent Manager](https://kilo.ai/docs/automate/agent-manager) · [Limites](https://kilo.ai/docs/gateway/usage-and-billing#free-model-rate-limits) · [Tâches d’arrière-plan](https://kilo.ai/docs/getting-started/using-kilo-for-free#free-background-tasks) |
| 2. Hermes | `delegate_task` crée un sous-agent. `execute_code` permet de lancer du Python avec les outils autorisés. Le relais TEL99 actuel utilise une sortie texte synthétique et désactive les outils du worker. | `WINDOWS_PENDING` pour la délégation outillée et le bac à sable. `PROVIDER_PENDING` pour le quota et le prix exacts du fournisseur configuré. `hermes usage --json` couvre certains fournisseurs. Pour Nous, `hermes portal info` renseigne le compte et le routage. Exiger l’identité du fournisseur et du modèle et les coûts réel et estimé nuls dans le reçu. [Délégation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/delegation.md) · [Usage](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/cli-commands.md#hermes-usage) · [Portail Nous](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/nous-portal.md#inspecting-whats-wired-up) |
| 3. OpenHands Cloud | API de conversations authentifiée. La documentation liste des modèles gratuits sur le service. TEL99 possède déjà une lecture de quota. | `PROVIDER_PENDING` pour une identité autorisée, une référence de modèle exacte, une allocation disponible et les droits de la conversation. G0 reste `BLOCKED` pour l’ancien jeton #88 tant que sa révocation est sans attestation. Utiliser uniquement une identité distincte expressément approuvée pour la recette. [API Cloud](https://github.com/OpenHands/docs/blob/main/openhands/usage/cloud/cloud-api.mdx) · [Catalogue](https://github.com/OpenHands/docs/blob/main/openhands/usage/llms/openhands-llms.mdx#free-models) · [Lecture de quota TEL99](../../scripts/agents/protocol/adapters/openhands.py) |

Retenir le premier exécuteur qui prouve le raccord de développement, les droits effectifs, l’isolation, le modèle gratuit et le quota restant avant chaque exécution. Un coût ou un quota inconnu donne `BLOCKED`. Une mission réclamée reste liée à son état et à son exécuteur. Un transfert requiert un nouvel accord explicite et une réconciliation de la première tentative. Garder un seul récepteur et un seul état durable pour chaque mandat.

## Recette de développement en deux issues

Les deux issues et leur autorisation initiale sont `WINDOWS_PENDING`. Le propriétaire approuve une fois la campagne sur GitHub, avec le dépôt, le SHA des octets UTF-8 du mandat, les deux empreintes de contrat, le périmètre des fichiers, les identités, l’expiration, les plafonds et la dépendance de B à A. Publier les deux nouvelles issues sous cet accord. Les textes et chemins suivants sont proposés pour un projet de démonstration sans données financières.

| Issue proposée | Fichier réservé | Contrôles indépendants à épingler dans le mandat |
| --- | --- | --- |
| A · Résumé des tâches | `docs/agents/autonomy-demo/summary.py` | Entrée JSON synthétique, compter `total`, `open` et `done`. Vérifier les compteurs sur trois tâches et sur une liste vide, refuser une racine invalide. Comparer le contenu de l’entrée avant et après. |
| B · Export CSV du gestionnaire | `docs/agents/autonomy-demo/export.py` | Entrée JSON synthétique, écrire sur stdout les colonnes `id,title,done`. Tester une liste vide, l’ordre des lignes et les titres avec virgule, guillemets et accents. Refuser une entrée invalide et vérifier l’intégrité de la source. Lire la preuve A dans la mémoire du projet avant d’agir. |

1. **Établir le raccord.** Relever le mode de réception GitHub, la session ciblée, le moyen de corréler son ACK et les limites d’outils. Les trois profils TEL99 courants sont en lecture seule, y compris le profil développeur. Le profil d’édition de la recette doit être autorisé et appliqué uniquement au worktree et aux fichiers réservés. Inventorier les 12 profils, leurs Skills et leur mémoire individuellement avec `python -B -m scripts.agents.intelligence.cli roles`. Utiliser le catalogue existant pour distinguer les profils déclarés des sessions observées. [Catalogue de rôles et Skills](AGENT_CAPABILITY_PLANNING.md)
2. **Démarrer une seule fois après l’autorisation et le diagnostic.** La commande `START -Campaign` existante exécute la recette texte, avec des PR d’artefacts. Le démarrage de la recette code reste `BLOCKED_NATIVE_RUNTIME` jusqu’à la qualification du raccord. Une fois qualifié, le même lancement borné doit recevoir A et B automatiquement et permettre de suivre `STATUS`, les reçus et les brouillons. [Commandes de la recette texte](KILO_GITHUB_WINDOWS.md#recette-sur-deux-issues-distinctes)
3. **Exiger le commit et la preuve avant B.** Le vérificateur reprend le SHA exact dans un worktree séparé en lecture seule. Comparer parent, diff, fichiers et empreintes au mandat. Rejouer les tests épinglés et enregistrer leur nombre, leurs codes de retour et l’empreinte des logs. Un test vide, sauté, rouge ou invérifiable bloque le résultat. Enregistrer le brouillon A et le reçu A confirmé avant le lancement de B. Le contrôleur porte les droits GitHub de publication et les workers reçoivent uniquement les droits qui leur sont attribués.
4. **Prouver la reprise.** Sur un état neuf de recette, déclencher `STOP` avec les mêmes paramètres d’état que le lancement et attendre `STOPPED`. Archiver explicitement le marqueur après décision de reprendre. `ACK` durable sans lancement peut reprendre. `RUNNING` incertain requiert une réconciliation. `WORKER_EXITED` reprend à la vérification. Un POST ambigu se rapproche en lecture avec les identifiants du contrat. Comparer les compteurs de workers, ACK, EVIDENCE, RESULT et PR avant et après. Reprendre B avec la mémoire vérifiée de A et un contrôle d’isolation dans un autre projet synthétique.
5. **Consigner les preuves.** Publier sur #123 et #94 le SHA du lanceur, les deux URLs d’issue, les IDs de session et d’ACK, les commits, les tests, les deux PR brouillon, les compteurs d’interruption/reprise, la provenance de la mémoire et les coûts. Évaluer chaque gate séparément. La préparation et les tests hors ligne ne donnent aucun PASS de recette live. [Critères G0–G7](AUTONOMIE_ZERO_COPIER_COLLER/CRITERES_DE_FIN.md)

## Audit différentiel de la préparation

| Point | État et contrôle |
| --- | --- |
| A · Tests et état | `FIXED` sur `main` pour le test historique destructeur. La suite du lanceur utilise des répertoires temporaires. Audit des worktrees du PC `WINDOWS_PENDING`. |
| B · Faux PASS | `FIXED` pour le retour succès prématuré du lanceur GitHub. La chaîne texte vérifie les octets et les contrôles indépendants. SHA du vrai développement et recette native `WINDOWS_PENDING`. |
| C · STOP | `FIXED` pour l’ACK durable avant le worker et les gardes de lancement/publication. Effet sur les descendants d’un futur worker outillé `WINDOWS_PENDING`. |
| D · Reprise, ACK, doublons | `TESTED` hors ligne sur le même registre et les appels GitHub simulés. Les POST ambigus restent en attente de rapprochement. La concurrence entre plusieurs machines et la recette avec GitHub réel restent `WINDOWS_PENDING`. |
| E · Hermes C | `FIXED` en admission et dans le worker de texte. La recette historique C reste `REJECTED`. |
| F · Quotas | `FIXED` pour l’arrêt de session sur limite GitHub et la garde de quota Hermes. Modèles, coût et quota des comptes `PROVIDER_PENDING`. |
| G · Délégation | `WINDOWS_PENDING` pour les sessions natives, la délégation, les deux vrais diffs et les deux brouillons de développement. |
| H · Permissions | `FIXED` pour les contrôles d’accord et d’identité ajoutés au transport. Les permissions effectives des comptes et la preuve de révocation du jeton #88 restent `BLOCKED`. |

Les jobs [Agents integration regression](../../.github/workflows/agents-integration-regression.yml) exercent l’autonomie hors ligne, le lanceur sous Windows et les régressions du site TEL99 sous Linux.
