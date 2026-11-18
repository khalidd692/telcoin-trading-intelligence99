# Vérifier un résultat de mission cloud

Dans l’issue approuvée, déclarer le fichier livré et un contrôle par critère.
Limiter la section aux lignes de déclaration. Un critère en prose sans
contrôle associé reste à vérifier manuellement. Les intitulés des jobs
doivent être distincts.

```text
### Critères d’acceptation
- acceptance-artifact: reports/kraken.txt
- check [report-format]: valider le format et le contenu du rapport
```

La configuration `authorized_verifiers` identifie les comptes GitHub habilités
à publier une preuve. Sa valeur par défaut est vide. Le vérificateur doit être
indépendant de la production du résultat. L’auteur de l’issue et son approbateur
sont écartés de la liste pour cette mission.

Le vérificateur contrôle le workflow, le checkout exact et le résultat des
jobs. Il publie ensuite un commentaire GitHub autonome, non modifié, sur
l’issue de la mission. La ligne commence par `tel99-evidence:v1 ` suivie d’un JSON
contenant les champs suivants.

| Champ | Valeur |
|---|---|
| `conversation_id` | Identifiant de la conversation dans le journal |
| `mission_digest` | Empreinte `sha256:…` du mandat approuvé |
| `sha` | SHA Git complet du commit vérifié |
| `artifact` | Chemin exact du fichier déclaré dans l’issue |
| `artifact_sha256` | SHA‑256 des octets du fichier, 64 caractères hexadécimaux |
| `run_id`, `run_attempt` | Entiers correspondant à l’exécution GitHub Actions |
| `jobs` | Objet associant chaque ID de critère au nom exact de son job GitHub |

L’exécution GitHub Actions doit être de type `push` ou `workflow_dispatch`
sur la branche de travail. Le vérificateur confirme que les jobs correspondent
aux critères et que le workflow et les tests sont indépendants du producteur.
Dans `trusted_verification_workflows`, associer l’identifiant de chaque
workflow indépendant à l’empreinte SHA‑256 de sa définition approuvée.
Le moteur relit le SHA de la branche, le fichier GitHub et cette définition
au même SHA, puis les conclusions de la tentative courante. Après une
relance du workflow, établir une preuve pour la nouvelle tentative.
Le jeton GitHub utilisé en lecture doit pouvoir consulter l’issue, le
contenu du dépôt et les exécutions Actions. Le fichier doit être non vide et faire
au plus 256 Kio. Le rapport conserve le SHA, l’empreinte et les identifiants
du commentaire, de l’exécution et des jobs. Les commandes de l’issue servent
de description des critères.

Une preuve absente, une vérification indisponible ou un workflow en cours
laisse la mission en `NEEDS_HUMAN` lorsque les rôles ont terminé. Une discordance
ou un contrôle rouge donne `REJECTED`. L’orchestrateur conserve la conversation
terminée pour une vérification ultérieure. Une mission déjà lancée avant la
conservation de l’empreinte approuvée nécessite une vérification manuelle.
