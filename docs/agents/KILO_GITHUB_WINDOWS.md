# Reprise Kilo sur Windows

Cette branche ajoute la réception GitHub au moteur de la PR #124 et réutilise l’admission GitHub de la PR #126. Elle traite des missions texte synthétiques avec le fournisseur natif `kilo-auto/free` et les rôles `tel99-analyst`, `tel99-dev` et `tel99-verifier`. La réponse du fournisseur est traitée comme des données. Le vérificateur compare les octets exacts de l’artefact au SHA-256 approuvé dans un processus distinct.

## Démarrer, lire l’état et arrêter

Depuis un worktree Windows distinct au SHA de la PR brouillon, avec PowerShell 7, Python 3.12 et le profil GitHub CLI du propriétaire déjà configuré sur github.com. Préparer la file décrite plus bas, puis remplir les trois valeurs d’après cette file.

~~~powershell
.\start-agents.ps1 -Action START -GitHubIssue $Issue -MandateComment $MandateId -MandateSha256 $MandateSha -Seconds 300
~~~

Dans une autre console du même worktree, avec le même numéro d’issue et le même `-State` si ce paramètre a été utilisé au démarrage :

~~~powershell
.\start-agents.ps1 -Action STATUS -GitHubIssue $Issue
.\start-agents.ps1 -Action STOP -GitHubIssue $Issue
~~~

`START` sonde toutes les dix secondes entre les traitements, pendant 1 à 3 600 secondes. Utiliser `-Once` pour un seul passage. `STOP_REQUESTED` signale la demande, `STOPPED` la fin observée de la session. Le prochain lancement explicite requiert d’archiver le fichier `stop.request` après confirmation de l’arrêt. Les appels GitHub ont un délai maximal de huit secondes chacun. La vérification déjà engagée peut prendre jusqu’à quinze secondes. Un HTTP 429 du fournisseur arrête la session sans repli. STATUS indique un quota inconnu si le fournisseur ne l'atteste pas.

Utiliser **un seul répertoire d’état durable par file**, par défaut `.tel99-automation-state/kilo-github-<issue>`. Le CAS et le verrou couvrent les processus qui partagent ce répertoire sur la même machine. Conserver et sauvegarder cet état après l’arrêt, y compris les claims, reçus, artefacts et résultats du vérificateur. Après un POST au résultat incertain, le programme relit GitHub. Si le reçu reste introuvable, `PENDING_RECONCILIATION` demande une revue humaine du reçu et de l’état local. Une reprise à partir de `RUNNING` donne `AWAITING_HUMAN` et conserve le claim. À partir de `WORKER_EXITED`, elle reprend la vérification du résultat sauvegardé.

## Préparer une file de recette autorisée

1. Le propriétaire choisit une **nouvelle issue ouverte dédiée** dans ce dépôt et y applique un label existant. Il publie un commentaire ne contenant que le bloc ci-dessous. Il fixe une courte échéance UTC. Les anciennes files, les issues de coordination et les missions historiques restent exclues de la recette.
2. Le propriétaire ou Kilo lit l’identifiant du commentaire et calcule le SHA-256 de son champ GitHub `body` exact. L’identité GitHub vérifiée est le compte propriétaire épinglé. Un commentaire édité, un label absent ou un mandat expiré ferme l’admission.
3. Le propriétaire approuve deux nouvelles missions synthétiques dans la même issue, chacune dans un commentaire distinct. Choisir deux identifiants inédits et mettre l’identifiant de A dans `dependencies` de B. Après cet accord initial, le worker local traite A puis B à partir de GitHub. Le programme de reprise ne publie aucune approbation.

~~~text
```kilo-mandate/v1
{"repo":"khalidd692/telcoin-trading-intelligence99","issue":ISSUE_NUMBER,"label":"EXISTING_LABEL","expires_at":"YYYY-MM-DDTHH:MM:SSZ"}
```
~~~

~~~powershell
$MandateSha = python -c 'import hashlib,json,subprocess,sys; row=json.loads(subprocess.check_output(["gh","api","--hostname","github.com","repos/khalidd692/telcoin-trading-intelligence99/issues/comments/"+sys.argv[1]],encoding="utf-8")); print(hashlib.sha256(row["body"].encode("utf-8")).hexdigest())' $MandateId
~~~

Exemple de fichier de préparation pour A. L’objectif et le texte attendu sont synthétiques. Sauvegarder le JSON sans BOM dans un fichier de travail privé. Pour B, changer l’identifiant, le rôle, le texte attendu, l’empreinte et la dépendance avant de calculer la nouvelle empreinte.

~~~json
{
  "id": "kilo-windows-a",
  "project": "synthetic",
  "owner": "kilo",
  "priority": "P0",
  "dependencies": [],
  "specialist": "tel99-analyst",
  "synthetic_data": true,
  "objective": "Réponds exactement OK, sans aucun autre caractère.",
  "expected_sha256": "565339bc4d33d72817b583024112eb7f5cdf3e5eef0252d6ec1b9c9a94e12bb3"
}
~~~

~~~powershell
python -c 'import json,sys; from scripts.agents.automation.autonomy_runtime import fingerprint; print(fingerprint(json.load(open(sys.argv[1], encoding="utf-8"))))' .\mission-a.json
~~~

Dans chaque bloc d’approbation, remplacer `{...}` par le JSON intégral de la mission, et renseigner l’empreinte, l’identifiant numérique et l’échéance. Le hash lie l’accord au contenu et l’API GitHub fournit l’identité de l’auteur.

~~~text
```kilo-mission/v1
{"mission":{...},"approval":{"approver":"khalidd692","mandate_comment_id":MANDATE_COMMENT_ID,"mission_sha256":"MISSION_FINGERPRINT","expires_at":"YYYY-MM-DDTHH:MM:SSZ"}}
```
~~~

## Vérifier et rendre la main

~~~powershell
python -B -m unittest -v tests.test_kilo_github_handoff tests.test_autonomy_runtime tests.test_kilo_executor tests.test_kilo_process_control tests.test_agent_state_cas tests.test_hermes_relay
pwsh -NoProfile -File .\tests\test_start_agents.ps1
~~~

- Démarrer une fois et observer deux chaînes sur l’issue de recette. Pour chaque mission, vérifier l’ACK `NOT_STARTED`, la preuve `EVIDENCE`, puis `RESULT` qui référence cette preuve. Comparer les identifiants du mandat et de l’accord, l’empreinte du contrat et celle de l’artefact. Vérifier `cost_usd="0"`, les empreintes de catalogue et réponse, le rôle et les contrôles du vérificateur.
- Arrêter et vérifier la transition visible dans STATUS. Redémarrer sur le même état et vérifier l’absence de nouveaux appels ou commentaires pour A et B. Les régressions ci-dessus couvrent aussi la perte d’ACK et d’EVIDENCE, l’expiration, la concurrence, le crash et le refus d’un artefact incorrect.
- Publier sur #123 les liens des reçus A/B, le SHA exact, la version Windows, les résultats et les blocages. Si GitHub CLI, la passerelle gratuite, le quota ou un accord frais manque, indiquer le blocage et conserver les preuves disponibles.

## État des dépendances

| Tâche | État de la reprise |
| --- | --- |
| Z-02 | Pont synthétique testé hors ligne, `WAITING_FOR_KILO_WINDOWS` pour la recette authentifiée. Les preuves S-04 et S-06 complètes restent des dépendances du backlog. |
| Z-01 | CLI native déjà présente dans la pile. `WAITING_S05` pour la recette d’un programme et de tests avec une preuve métier externe. |
| Z-05 | Reprise locale testée. Continuité pendant l’arrêt du PC `WAITING_Z02_Z04`, avec exécuteur cloud indépendant à démontrer. |
| P-03 | `WAITING_Z01_I02` pour l’isolation de deux projets réels. Hermès garde la responsabilité I-02. |
| F-01 | `WAITING_Z01_Z04_I01_I02`. Les artefacts synthétiques constituent une recette plus étroite que le livrable final. |
| F-03 | Guide de reprise disponible. Livraison finale `WAITING_F01_F02_I03_P02_P03`. |

Le périmètre de recette correspond au fournisseur natif texte de #124. L’intégration aux sessions de l’Agent Manager, un CAS multi-machine, l’attestation de l’artefact Windows sur GitHub et la preuve métier S-05 restent à vérifier.
